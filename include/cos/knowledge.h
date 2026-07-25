// knowledge.h — Knowledge Base Interface
//
// Design: Abstract interface for knowledge storage and retrieval.
// Knowledge is NOT stored in neural weights — it comes from databases.
//
// Supported backends (pluggable):
//   - SQLite
//   - DuckDB
//   - Memory-mapped binary files
//   - FlatBuffers
//   - Custom binary databases
//
// The runtime loads only what is needed. Queries return structured facts.
//
// Memory: Facts are returned as semantic sub-graphs allocated from
// caller-provided arena. No hidden allocations.

#ifndef COS_KNOWLEDGE_H
#define COS_KNOWLEDGE_H

#include "cos/core.h"
#include "cos/semantic.h"
#include "cos/allocator.h"
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

// ── Fact ─────────────────────────────────────────────────────────────────
// A single atomic fact: (subject, predicate, object, confidence)
typedef struct cos_fact_s {
    cos_string_id_t subject;
    cos_string_id_t predicate;
    cos_string_id_t object;
    float           confidence;
    cos_timestamp_t timestamp;
} cos_fact_t;

// ── Query ────────────────────────────────────────────────────────────────
typedef struct cos_query_s {
    cos_string_id_t subject;    // 0 = wildcard
    cos_string_id_t predicate;  // 0 = wildcard
    cos_string_id_t object;     // 0 = wildcard
    size_t          max_results;
    bool            include_timestamps;
} cos_query_t;

// ── Query Result ─────────────────────────────────────────────────────────
typedef struct cos_query_result_s {
    cos_fact_t* facts;
    size_t      count;
    size_t      capacity;
} cos_query_result_t;

// ── Opaque Knowledge Base ────────────────────────────────────────────────
typedef struct cos_knowledge_base_s cos_knowledge_base_t;

// ── Lifecycle ────────────────────────────────────────────────────────────
cos_knowledge_base_t* cos_knowledge_create(cos_allocator_t* alloc);
void                  cos_knowledge_destroy(cos_knowledge_base_t* kb);

// ── Storage ──────────────────────────────────────────────────────────────
cos_status_t cos_knowledge_store(cos_knowledge_base_t* kb, const cos_fact_t* fact);
cos_status_t cos_knowledge_store_batch(cos_knowledge_base_t* kb, const cos_fact_t* facts, size_t count);
cos_status_t cos_knowledge_store_graph(cos_knowledge_base_t* kb, const cos_semantic_graph_t* graph);

// ── Retrieval ────────────────────────────────────────────────────────────
cos_status_t cos_knowledge_query(const cos_knowledge_base_t* kb, const cos_query_t* query, cos_query_result_t* out_result, cos_allocator_t* scratch);
cos_status_t cos_knowledge_query_graph(const cos_knowledge_base_t* kb, cos_string_id_t subject, cos_semantic_graph_t* out_graph);

// ── Backend Management ───────────────────────────────────────────────────
cos_status_t cos_knowledge_attach_sqlite(cos_knowledge_base_t* kb, const char* path);
cos_status_t cos_knowledge_attach_mmap(cos_knowledge_base_t* kb, const char* path);

// ── Introspection ────────────────────────────────────────────────────────
size_t cos_knowledge_fact_count(const cos_knowledge_base_t* kb);
size_t cos_knowledge_memory_used(const cos_knowledge_base_t* kb);

#ifdef __cplusplus
}
#endif

#endif // COS_KNOWLEDGE_H
