// semantic.h — Semantic Graph Layer
//
// Design: A semantic graph built on top of the generic graph engine.
// Nodes represent semantic concepts (entities, actions, relations, attributes).
// Edges represent semantic relationships (subject, object, modifier, etc.).
//
// Memory: Node payloads are pooled for cache efficiency.
// The graph is the single source of truth for all parsed meaning.

#ifndef COS_SEMANTIC_H
#define COS_SEMANTIC_H

#include "cos/core.h"
#include "cos/graph.h"
#include "cos/allocator.h"
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

// ── Semantic Node Types ──────────────────────────────────────────────────
typedef uint32_t cos_semantic_type_t;

enum {
    COS_SEMANTIC_ROOT         = 0,    // Root node of a semantic graph
    COS_SEMANTIC_STATEMENT    = 1,    // A complete statement/utterance
    COS_SEMANTIC_ENTITY       = 2,    // A named entity (person, place, thing)
    COS_SEMANTIC_ACTION       = 3,    // An action/verb
    COS_SEMANTIC_ATTRIBUTE    = 4,    // A property or attribute
    COS_SEMANTIC_MODIFIER     = 5,    // A modifier (adjective, adverb)
    COS_SEMANTIC_RELATION     = 6,    // A relation between concepts
    COS_SEMANTIC_TIME         = 7,    // Temporal expression
    COS_SEMANTIC_QUANTITY     = 8,    // Numeric quantity
    COS_SEMANTIC_QUESTION     = 9,    // Question marker
    COS_SEMANTIC_INTENT       = 10,   // Speaker intent
    COS_SEMANTIC_CONTEXT      = 11,   // Contextual metadata
};

// ── Semantic Roles (edge types) ──────────────────────────────────────────
typedef uint32_t cos_semantic_role_t;

enum {
    COS_ROLE_SUBJECT          = 0,    // Entity performing action
    COS_ROLE_OBJECT           = 1,    // Entity receiving action
    COS_ROLE_VERB             = 2,    // The action
    COS_ROLE_MODIFIER         = 3,    // Modifies a node
    COS_ROLE_TIME             = 4,    // Temporal modifier
    COS_ROLE_PLACE            = 5,    // Spatial modifier
    COS_ROLE_POSSESSION       = 6,    // Possession relationship
    COS_ROLE_ATTRIBUTE        = 7,    // Attribute relationship
    COS_ROLE_CAUSE            = 8,    // Causal relationship
    COS_ROLE_CONJUNCTION      = 9,    // Conjunctive relationship
    COS_ROLE_DISJUNCTION      = 10,   // Disjunctive relationship
    COS_ROLE_CONDITION        = 11,   // Conditional relationship
    COS_ROLE_PURPOSE          = 12,   // Purpose relationship
    COS_ROLE_QUALIFIER        = 13,   // Qualifier relationship
    COS_ROLE_REFERENCE        = 14,   // Coreference link
};

// ── Semantic Node Payload ────────────────────────────────────────────────
typedef struct cos_semantic_node_s {
    cos_semantic_type_t type;        // Type of semantic node
    cos_string_id_t     text;        // Interned original text (if any)
    cos_string_id_t     lemma;       // Interned lemma/base form
    float               confidence;  // Parse confidence 0.0–1.0
    uint32_t            flags;       // Reserved for future use
} cos_semantic_node_t;

// ── Opaque Semantic Graph ────────────────────────────────────────────────
typedef struct cos_semantic_graph_s cos_semantic_graph_t;

// ── Lifecycle ────────────────────────────────────────────────────────────
cos_semantic_graph_t* cos_semantic_create(cos_allocator_t* alloc);
void                  cos_semantic_destroy(cos_semantic_graph_t* sg);

// ── Node Operations ──────────────────────────────────────────────────────
cos_graph_node_id_t   cos_semantic_add_node(cos_semantic_graph_t* sg, cos_semantic_type_t type, cos_string_id_t text, cos_string_id_t lemma, float confidence);
cos_status_t          cos_semantic_get_node(const cos_semantic_graph_t* sg, cos_graph_node_id_t id, cos_semantic_node_t* out_node);
cos_status_t          cos_semantic_set_node(cos_semantic_graph_t* sg, cos_graph_node_id_t id, const cos_semantic_node_t* node);

// ── Edge Operations ──────────────────────────────────────────────────────
cos_graph_edge_id_t   cos_semantic_add_edge(cos_semantic_graph_t* sg, cos_graph_node_id_t from, cos_graph_node_id_t to, cos_semantic_role_t role, float weight);
cos_status_t          cos_semantic_get_role(const cos_semantic_graph_t* sg, cos_graph_edge_id_t edge, cos_semantic_role_t* out_role);

// ── Semantic Queries ─────────────────────────────────────────────────────
// Find nodes of a given type.
size_t                cos_semantic_find_type(const cos_semantic_graph_t* sg, cos_semantic_type_t type, cos_graph_node_id_t* out_nodes, size_t max_nodes);

// Get the root node of the graph.
cos_graph_node_id_t   cos_semantic_root(const cos_semantic_graph_t* sg);

// ── Serialization ────────────────────────────────────────────────────────
cos_status_t          cos_semantic_serialize(const cos_semantic_graph_t* sg, cos_allocator_t* alloc, void** out_data, size_t* out_size);
cos_semantic_graph_t* cos_semantic_deserialize(const void* data, size_t size, cos_allocator_t* alloc);

// ── Introspection ────────────────────────────────────────────────────────
size_t                cos_semantic_memory_used(const cos_semantic_graph_t* sg);

// ── Graph Access ───────────────────────────────────────────────────────────
// Expose the underlying graph engine for traversal and inspection.
cos_graph_t*          cos_semantic_get_graph(const cos_semantic_graph_t* sg);

#ifdef __cplusplus
}
#endif

#endif // COS_SEMANTIC_H
