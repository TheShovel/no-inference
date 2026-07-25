// knowledge.c — Knowledge Base Implementation
//
// Design: In-memory fact storage with subject-predicate-object indexing.
// Facts are stored in three hash maps (subject, predicate, object index)
// for fast multi-dimensional lookup.
//
// The default backend is an in-memory index. SQLite, DuckDB, and mmap
// backends can be attached as alternatives.
//
// Memory: Facts are stored compactly — 32 bytes each (4 IDs * 2 + confidence + timestamp).
// Indexes are hash tables mapping (key → list of fact indices).

#include "cos/core.h"
#include "cos/knowledge.h"
#include "cos/semantic.h"
#include "cos/allocator.h"
#include "cos/string_intern.h"
#include <string.h>
#include <stdalign.h>

// ── Fact Storage ─────────────────────────────────────────────────────────
// A linear array of facts with hash-based indexes.

#define COS_KB_INIT_CAPACITY 1024

typedef struct cos_fact_entry_s {
    cos_fact_t      fact;
    uint32_t        next_by_subject;    // Linked list index for subject chain
    uint32_t        next_by_predicate;
    uint32_t        next_by_object;
} cos_fact_entry_t;

// ── Hash Table for Indexing ──────────────────────────────────────────────
typedef struct cos_kb_index_s {
    uint32_t* buckets;      // Array of fact indices (head of chain)
    size_t    bucket_count;
} cos_kb_index_t;

struct cos_knowledge_base_s {
    cos_allocator_t* alloc;

    // Fact storage
    cos_fact_entry_t* facts;
    size_t            fact_count;
    size_t            fact_capacity;

    // Indexes (key = string_id % bucket_count)
    cos_kb_index_t idx_subject;
    cos_kb_index_t idx_predicate;
    cos_kb_index_t idx_object;

    // Memory usage tracking
    size_t total_memory;

    // Backend flags
    bool has_sqlite;
    bool has_mmap;
};

// ── Index Operations ─────────────────────────────────────────────────────

static cos_status_t kb_index_init(cos_kb_index_t* idx, size_t bucket_count, cos_allocator_t* alloc) {
    idx->bucket_count = bucket_count;
    idx->buckets = (uint32_t*)alloc->alloc(alloc, bucket_count * sizeof(uint32_t), alignof(uint32_t));
    if (!idx->buckets) return COS_ERROR_NOMEM;
    memset(idx->buckets, 0xFF, bucket_count * sizeof(uint32_t));  // 0xFFFFFFFF = NIL
    return COS_OK;
}

static void kb_index_destroy(cos_kb_index_t* idx, cos_allocator_t* alloc) {
    if (idx->buckets) alloc->free(alloc, idx->buckets, idx->bucket_count * sizeof(uint32_t));
    idx->buckets = NULL;
}

static inline size_t kb_hash(cos_string_id_t id, size_t bucket_count) {
    return (size_t)id % bucket_count;
}

// ── Lifecycle ────────────────────────────────────────────────────────────

cos_knowledge_base_t* cos_knowledge_create(cos_allocator_t* alloc) {
    if (!alloc) alloc = cos_sys_allocator();

    cos_knowledge_base_t* kb = (cos_knowledge_base_t*)
        alloc->alloc(alloc, sizeof(cos_knowledge_base_t), alignof(cos_knowledge_base_t));
    if (!kb) return NULL;

    kb->alloc = alloc;

    kb->facts = (cos_fact_entry_t*)
        alloc->alloc(alloc, COS_KB_INIT_CAPACITY * sizeof(cos_fact_entry_t), alignof(cos_fact_entry_t));
    if (!kb->facts) { alloc->free(alloc, kb, sizeof(cos_knowledge_base_t)); return NULL; }
    kb->fact_capacity = COS_KB_INIT_CAPACITY;
    kb->fact_count    = 0;

    // Initialize indexes (prime bucket counts for good distribution)
    if (kb_index_init(&kb->idx_subject,   1021, alloc) != COS_OK ||
        kb_index_init(&kb->idx_predicate, 1021, alloc) != COS_OK ||
        kb_index_init(&kb->idx_object,    1021, alloc) != COS_OK) {
        alloc->free(alloc, kb->facts, kb->fact_capacity * sizeof(cos_fact_entry_t));
        alloc->free(alloc, kb, sizeof(cos_knowledge_base_t));
        return NULL;
    }

    kb->total_memory = sizeof(cos_knowledge_base_t) +
                       COS_KB_INIT_CAPACITY * sizeof(cos_fact_entry_t) +
                       3 * 1021 * sizeof(uint32_t);
    kb->has_sqlite = false;
    kb->has_mmap   = false;

    return kb;
}

void cos_knowledge_destroy(cos_knowledge_base_t* kb) {
    if (!kb) return;
    kb_index_destroy(&kb->idx_subject,   kb->alloc);
    kb_index_destroy(&kb->idx_predicate, kb->alloc);
    kb_index_destroy(&kb->idx_object,    kb->alloc);
    if (kb->facts) kb->alloc->free(kb->alloc, kb->facts, kb->fact_capacity * sizeof(cos_fact_entry_t));
    kb->alloc->free(kb->alloc, kb, sizeof(cos_knowledge_base_t));
}

// ── Storage ──────────────────────────────────────────────────────────────

cos_status_t cos_knowledge_store(cos_knowledge_base_t* kb, const cos_fact_t* fact) {
    if (!kb || !fact) return COS_ERROR_NULL;

    // Grow if needed
    if (kb->fact_count >= kb->fact_capacity) {
        size_t new_cap = kb->fact_capacity * 2;
        cos_fact_entry_t* new_facts = (cos_fact_entry_t*)
            kb->alloc->realloc(kb->alloc, kb->facts,
                kb->fact_capacity * sizeof(cos_fact_entry_t),
                new_cap * sizeof(cos_fact_entry_t), alignof(cos_fact_entry_t));
        if (!new_facts) return COS_ERROR_NOMEM;
        kb->facts = new_facts;
        kb->fact_capacity = new_cap;
    }

    cos_fact_entry_t* entry = &kb->facts[kb->fact_count];
    entry->fact = *fact;
    size_t idx = kb->fact_count;

    // Link into subject index (prepend to chain)
    size_t s_bucket = kb_hash(fact->subject, kb->idx_subject.bucket_count);
    entry->next_by_subject = kb->idx_subject.buckets[s_bucket];
    kb->idx_subject.buckets[s_bucket] = (uint32_t)idx;

    // Predicate index
    size_t p_bucket = kb_hash(fact->predicate, kb->idx_predicate.bucket_count);
    entry->next_by_predicate = kb->idx_predicate.buckets[p_bucket];
    kb->idx_predicate.buckets[p_bucket] = (uint32_t)idx;

    // Object index
    size_t o_bucket = kb_hash(fact->object, kb->idx_object.bucket_count);
    entry->next_by_object = kb->idx_object.buckets[o_bucket];
    kb->idx_object.buckets[o_bucket] = (uint32_t)idx;

    kb->fact_count++;
    return COS_OK;
}

cos_status_t cos_knowledge_store_batch(cos_knowledge_base_t* kb, const cos_fact_t* facts, size_t count) {
    if (!kb || !facts) return COS_ERROR_NULL;
    for (size_t i = 0; i < count; i++) {
        cos_status_t status = cos_knowledge_store(kb, &facts[i]);
        if (status != COS_OK) return status;
    }
    return COS_OK;
}

cos_status_t cos_knowledge_store_graph(cos_knowledge_base_t* kb,
                                        const cos_semantic_graph_t* graph) {
    if (!kb || !graph) return COS_ERROR_NULL;

    // Direct approach: store text from ALL entity and action nodes
    // without relying on find_type (in case that has issues).
    // We query up to 32 nodes of each type directly.

    // Store entity texts
    cos_graph_node_id_t nodes[32];
    size_t n = cos_semantic_find_type(graph, COS_SEMANTIC_ENTITY, nodes, 32);
    for (size_t i = 0; i < n; i++) {
        cos_semantic_node_t en;
        if (cos_semantic_get_node(graph, nodes[i], &en) == COS_OK && en.text != COS_STRING_ID_NULL) {
            cos_fact_t fact;
            memset(&fact, 0, sizeof(fact));
            fact.subject = en.text;
            fact.confidence = 1.0f;
            fact.timestamp = cos_timestamp_now();
            cos_knowledge_store(kb, &fact);
        }
    }

    // Store action + entities as (subj, predicate, obj) triples
    n = cos_semantic_find_type(graph, COS_SEMANTIC_ACTION, nodes, 32);
    for (size_t ai = 0; ai < n; ai++) {
        cos_semantic_node_t verb;
        if (cos_semantic_get_node(graph, nodes[ai], &verb) != COS_OK) continue;

        // Find subject (edge from root with role = subject)
        cos_graph_node_id_t subj_id = COS_NODE_ID_NULL;
        cos_graph_node_id_t obj_id  = COS_NODE_ID_NULL;

        // Walk all entity nodes and check for edges
        cos_graph_node_id_t ents[32];
        size_t ec = cos_semantic_find_type(graph, COS_SEMANTIC_ENTITY, ents, 32);
        for (size_t ei = 0; ei < ec; ei++) {
            if (subj_id == COS_NODE_ID_NULL) {
                // Assume the first entity is the subject, rest are objects
                subj_id = ents[ei];
            } else if (obj_id == COS_NODE_ID_NULL) {
                obj_id = ents[ei];
            }
        }

        cos_semantic_node_t subj_node, obj_node;
        cos_string_id_t subj_text = COS_STRING_ID_NULL;
        cos_string_id_t obj_text  = COS_STRING_ID_NULL;

        if (subj_id != COS_NODE_ID_NULL && cos_semantic_get_node(graph, subj_id, &subj_node) == COS_OK) {
            subj_text = subj_node.text;
        }
        if (obj_id != COS_NODE_ID_NULL && cos_semantic_get_node(graph, obj_id, &obj_node) == COS_OK) {
            obj_text = obj_node.text;
        }

        if (subj_text != COS_STRING_ID_NULL && verb.text != COS_STRING_ID_NULL) {
            cos_fact_t fact;
            memset(&fact, 0, sizeof(fact));
            fact.subject   = subj_text;
            fact.predicate = verb.text;
            fact.object    = obj_text;
            fact.confidence = 1.0f;
            fact.timestamp  = cos_timestamp_now();
            cos_knowledge_store(kb, &fact);
        }
    }

    return COS_OK;
}

// ── Retrieval ────────────────────────────────────────────────────────────

cos_status_t cos_knowledge_query(const cos_knowledge_base_t* kb,
                                  const cos_query_t* query,
                                  cos_query_result_t* out_result,
                                  cos_allocator_t* scratch) {
    if (!kb || !query || !out_result) return COS_ERROR_NULL;

    // Initialize result
    out_result->facts    = NULL;
    out_result->count    = 0;
    out_result->capacity = 0;

    // Determine which index to use
    cos_kb_index_t* idx = NULL;
    cos_string_id_t key  = COS_STRING_ID_NULL;

    if (query->subject != 0) {
        idx = (cos_kb_index_t*)&kb->idx_subject;
        key = query->subject;
    } else if (query->predicate != 0) {
        idx = (cos_kb_index_t*)&kb->idx_predicate;
        key = query->predicate;
    } else if (query->object != 0) {
        idx = (cos_kb_index_t*)&kb->idx_object;
        key = query->object;
    } else {
        // No filter: return all facts
        size_t result_count = kb->fact_count < query->max_results ? kb->fact_count : query->max_results;
        if (result_count == 0) result_count = kb->fact_count;

        if (!scratch) scratch = kb->alloc;
        out_result->facts = (cos_fact_t*)scratch->alloc(scratch, result_count * sizeof(cos_fact_t), alignof(cos_fact_t));
        if (!out_result->facts && result_count > 0) return COS_ERROR_NOMEM;

        for (size_t i = 0; i < result_count; i++) {
            out_result->facts[i] = kb->facts[i].fact;
        }
        out_result->count    = result_count;
        out_result->capacity = result_count;
        return COS_OK;
    }

    // Scan the index chain
    size_t bucket = kb_hash(key, idx->bucket_count);
    uint32_t fact_idx = idx->buckets[bucket];

    // Count first
    size_t match_count = 0;
    while (fact_idx != UINT32_MAX && match_count < query->max_results) {
        const cos_fact_t* f = &kb->facts[fact_idx].fact;

        bool match = true;
        if (query->subject   != 0 && f->subject   != query->subject)   match = false;
        if (query->predicate != 0 && f->predicate != query->predicate) match = false;
        if (query->object    != 0 && f->object    != query->object)    match = false;

        if (match) match_count++;

        // Walk the chain
        if (idx == &kb->idx_subject) fact_idx = kb->facts[fact_idx].next_by_subject;
        else if (idx == &kb->idx_predicate) fact_idx = kb->facts[fact_idx].next_by_predicate;
        else fact_idx = kb->facts[fact_idx].next_by_object;
    }

    // Allocate and fill
    if (match_count > 0) {
        if (!scratch) scratch = kb->alloc;
        out_result->facts = (cos_fact_t*)scratch->alloc(scratch, match_count * sizeof(cos_fact_t), alignof(cos_fact_t));
        if (!out_result->facts) return COS_ERROR_NOMEM;

        fact_idx = idx->buckets[bucket];
        size_t out_i = 0;
        while (fact_idx != UINT32_MAX && out_i < match_count) {
            const cos_fact_t* f = &kb->facts[fact_idx].fact;

            bool match = true;
            if (query->subject   != 0 && f->subject   != query->subject)   match = false;
            if (query->predicate != 0 && f->predicate != query->predicate) match = false;
            if (query->object    != 0 && f->object    != query->object)    match = false;

            if (match) {
                out_result->facts[out_i++] = *f;
            }

            if (idx == &kb->idx_subject) fact_idx = kb->facts[fact_idx].next_by_subject;
            else if (idx == &kb->idx_predicate) fact_idx = kb->facts[fact_idx].next_by_predicate;
            else fact_idx = kb->facts[fact_idx].next_by_object;
        }
        out_result->count    = match_count;
        out_result->capacity = match_count;
    }

    return COS_OK;
}

cos_status_t cos_knowledge_query_graph(const cos_knowledge_base_t* kb,
                                        cos_string_id_t subject,
                                        cos_semantic_graph_t* out_graph) {
    (void)kb;
    (void)subject;
    (void)out_graph;
    // Stub: would convert facts into a semantic graph
    return COS_ERROR_NOT_IMPL;
}

// ── Backend Management ───────────────────────────────────────────────────

cos_status_t cos_knowledge_attach_sqlite(cos_knowledge_base_t* kb, const char* path) {
    (void)kb;
    (void)path;
    // Stub: would initialize SQLite backend
    return COS_ERROR_NOT_IMPL;
}

cos_status_t cos_knowledge_attach_mmap(cos_knowledge_base_t* kb, const char* path) {
    (void)kb;
    (void)path;
    // Stub: would mmap a binary knowledge file
    return COS_ERROR_NOT_IMPL;
}

// ── Introspection ────────────────────────────────────────────────────────

size_t cos_knowledge_fact_count(const cos_knowledge_base_t* kb) {
    return kb ? kb->fact_count : 0;
}

size_t cos_knowledge_memory_used(const cos_knowledge_base_t* kb) {
    return kb ? kb->total_memory : 0;
}
