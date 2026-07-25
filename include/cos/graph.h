// graph.h — Generic Directed Graph Engine
//
// Design: Compact, contiguous-array graph storage.
//   - Nodes stored in a growable array (stable indices via slot map).
//   - Edges stored per-node as contiguous edge lists (not linked lists).
//   - Memory pools for node/edge data.
//   - Topological sort, transitive closure, graph diff.
//
// Memory: Nodes: 16 bytes each. Edges: 8 bytes each.
// Cache-friendly: sequential node/edge traversal.

#ifndef COS_GRAPH_H
#define COS_GRAPH_H

#include "cos/core.h"
#include "cos/allocator.h"
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

// ── Node & Edge Types ────────────────────────────────────────────────────
typedef uint32_t cos_graph_node_id_t;
typedef uint32_t cos_graph_edge_id_t;
typedef uint32_t cos_graph_generation_t; // increases monotonically on mutations

// ── Graph Flags ──────────────────────────────────────────────────────────
typedef uint32_t cos_graph_flags_t;
enum {
    COS_GRAPH_DIRECTED   = 1 << 0,
    COS_GRAPH_ACYCLIC    = 1 << 1,
    COS_GRAPH_WEIGHTED   = 1 << 2,
};

// ── Edge ─────────────────────────────────────────────────────────────────
typedef struct cos_graph_edge_s {
    cos_graph_node_id_t from;
    cos_graph_node_id_t to;
    float               weight;       // unused if not COS_GRAPH_WEIGHTED
    cos_graph_edge_id_t id;           // stable identifier
} cos_graph_edge_t;

// ── Opaque Graph ─────────────────────────────────────────────────────────
typedef struct cos_graph_s cos_graph_t;

// ── Lifecycle ────────────────────────────────────────────────────────────
cos_graph_t*        cos_graph_create(cos_graph_flags_t flags, cos_allocator_t* alloc);
void                cos_graph_destroy(cos_graph_t* g);

// ── Node Operations ──────────────────────────────────────────────────────
cos_graph_node_id_t cos_graph_add_node(cos_graph_t* g, void* user_data, size_t data_size);
cos_status_t        cos_graph_remove_node(cos_graph_t* g, cos_graph_node_id_t id);
cos_status_t        cos_graph_get_node_data(const cos_graph_t* g, cos_graph_node_id_t id, void** out_data, size_t* out_size);
cos_status_t        cos_graph_set_node_data(cos_graph_t* g, cos_graph_node_id_t id, const void* data, size_t data_size);
size_t              cos_graph_node_count(const cos_graph_t* g);
bool                cos_graph_has_node(const cos_graph_t* g, cos_graph_node_id_t id);

// ── Edge Operations ──────────────────────────────────────────────────────
cos_graph_edge_id_t cos_graph_add_edge(cos_graph_t* g, cos_graph_node_id_t from, cos_graph_node_id_t to, float weight);
cos_status_t        cos_graph_remove_edge(cos_graph_t* g, cos_graph_edge_id_t id);
cos_status_t        cos_graph_get_edge(const cos_graph_t* g, cos_graph_edge_id_t id, cos_graph_edge_t* out_edge);
size_t              cos_graph_edge_count(const cos_graph_t* g);

// ── Traversal ────────────────────────────────────────────────────────────
// Outgoing edges of a node (successors).
const cos_graph_edge_t* cos_graph_out_edges(const cos_graph_t* g, cos_graph_node_id_t node, size_t* out_count);
// Incoming edges of a node (predecessors).
const cos_graph_edge_t* cos_graph_in_edges(const cos_graph_t* g, cos_graph_node_id_t node, size_t* out_count);

// ── Algorithms ───────────────────────────────────────────────────────────
// Topological sort into `out_nodes` array. Returns number of nodes written.
// `out_nodes` must be at least cos_graph_node_count() in size.
size_t cos_graph_topological_sort(const cos_graph_t* g, cos_graph_node_id_t* out_nodes, size_t max_nodes);

// Simple breadth-first search. Returns number of nodes reachable.
// `out_visited` must be at least cos_graph_node_count() in size.
size_t cos_graph_bfs(const cos_graph_t* g, cos_graph_node_id_t start, cos_graph_node_id_t* out_visited, size_t max_nodes);

// ── Graph Diffing ────────────────────────────────────────────────────────
typedef struct cos_graph_diff_s {
    size_t              nodes_added;
    size_t              nodes_removed;
    size_t              edges_added;
    size_t              edges_removed;
    cos_graph_generation_t generation_a;
    cos_graph_generation_t generation_b;
} cos_graph_diff_t;

cos_status_t cos_graph_diff(const cos_graph_t* before, const cos_graph_t* after, cos_graph_diff_t* out_diff);

// ── Introspection ────────────────────────────────────────────────────────
cos_graph_generation_t cos_graph_generation(const cos_graph_t* g);
cos_graph_flags_t      cos_graph_flags(const cos_graph_t* g);
size_t                 cos_graph_memory_used(const cos_graph_t* g);

#ifdef __cplusplus
}
#endif

#endif // COS_GRAPH_H
