// semantic.c — Semantic Graph Layer Implementation
//
// Design: Thin layer over the generic graph engine that adds
// semantic node types, roles, and helper functions.
// The underlying graph provides traversal, diffing, and serialization.

#include "cos/core.h"
#include "cos/graph.h"
#include "cos/semantic.h"
#include "cos/string_intern.h"
#include "cos/allocator.h"
#include <string.h>
#include <stdalign.h>

// ── Semantic Graph Structure ─────────────────────────────────────────────
struct cos_semantic_graph_s {
    cos_graph_t*         graph;
    cos_allocator_t*     alloc;
    cos_graph_node_id_t  root_id;
};

// ── Lifecycle ────────────────────────────────────────────────────────────

cos_semantic_graph_t* cos_semantic_create(cos_allocator_t* alloc) {
    if (!alloc) alloc = cos_sys_allocator();

    cos_semantic_graph_t* sg = (cos_semantic_graph_t*)
        alloc->alloc(alloc, sizeof(cos_semantic_graph_t), alignof(cos_semantic_graph_t));
    if (!sg) return NULL;

    sg->graph = cos_graph_create(COS_GRAPH_DIRECTED, alloc);
    if (!sg->graph) {
        alloc->free(alloc, sg, sizeof(cos_semantic_graph_t));
        return NULL;
    }

    sg->alloc   = alloc;
    sg->root_id = COS_NODE_ID_NULL;

    // Create root node
    cos_semantic_node_t root_node;
    memset(&root_node, 0, sizeof(root_node));
    root_node.type = COS_SEMANTIC_ROOT;
    root_node.confidence = 1.0f;

    cos_graph_node_id_t root = cos_graph_add_node(sg->graph, &root_node, sizeof(root_node));
    if (root == COS_NODE_ID_NULL) {
        cos_graph_destroy(sg->graph);
        alloc->free(alloc, sg, sizeof(cos_semantic_graph_t));
        return NULL;
    }
    sg->root_id = root;

    return sg;
}

void cos_semantic_destroy(cos_semantic_graph_t* sg) {
    if (!sg) return;
    if (sg->graph) cos_graph_destroy(sg->graph);
    sg->alloc->free(sg->alloc, sg, sizeof(cos_semantic_graph_t));
}

// ── Node Operations ──────────────────────────────────────────────────────

cos_graph_node_id_t cos_semantic_add_node(cos_semantic_graph_t* sg,
                                           cos_semantic_type_t type,
                                           cos_string_id_t text,
                                           cos_string_id_t lemma,
                                           float confidence) {
    if (!sg) return COS_NODE_ID_NULL;

    cos_semantic_node_t sem_node;
    sem_node.type       = type;
    sem_node.text       = text;
    sem_node.lemma      = lemma;
    sem_node.confidence = confidence;
    sem_node.flags      = 0;

    cos_graph_node_id_t nid = cos_graph_add_node(sg->graph, &sem_node, sizeof(sem_node));
    return nid;
}

cos_status_t cos_semantic_get_node(const cos_semantic_graph_t* sg,
                                    cos_graph_node_id_t id,
                                    cos_semantic_node_t* out_node) {
    if (!sg || !out_node) return COS_ERROR_NULL;

    void* data;
    size_t size;
    cos_status_t status = cos_graph_get_node_data(sg->graph, id, &data, &size);
    if (status != COS_OK) return status;
    if (size != sizeof(cos_semantic_node_t)) return COS_ERROR_TYPE;

    memcpy(out_node, data, sizeof(cos_semantic_node_t));
    return COS_OK;
}

cos_status_t cos_semantic_set_node(cos_semantic_graph_t* sg,
                                    cos_graph_node_id_t id,
                                    const cos_semantic_node_t* node) {
    if (!sg || !node) return COS_ERROR_NULL;
    return cos_graph_set_node_data(sg->graph, id, node, sizeof(cos_semantic_node_t));
}

// ── Edge Operations ──────────────────────────────────────────────────────

cos_graph_edge_id_t cos_semantic_add_edge(cos_semantic_graph_t* sg,
                                           cos_graph_node_id_t from,
                                           cos_graph_node_id_t to,
                                           cos_semantic_role_t role,
                                           float weight) {
    if (!sg) return COS_EDGE_ID_NULL;

    // Encode role as part of the edge weight + a custom field.
    // We use the weight field and a modified approach.
    // For simplicity, we store role in the weight high bits.
    // A cleaner approach would extend the graph edge structure.
    // For now, we store role as a separate node in the semantic graph data.

    // Actually, let's add the role as an attribute node connected to the edge.
    // Simpler: encode role in a data node between the nodes.
    // Simplest: just use the graph edge with weight = (float)role + 1000.0f to encode role.

    // Clean approach: create a relation node in the graph
    cos_graph_node_id_t rel_node = cos_semantic_add_node(sg, COS_SEMANTIC_RELATION,
                                                          COS_STRING_ID_NULL, COS_STRING_ID_NULL, 1.0f);
    if (rel_node == COS_NODE_ID_NULL) return COS_EDGE_ID_NULL;

    // Edge from subject to relation
    cos_graph_node_id_t e1 = cos_graph_add_edge(sg->graph, from, rel_node, weight);
    // Edge from relation to object
    cos_graph_node_id_t e2 = cos_graph_add_edge(sg->graph, rel_node, to, (float)role);

    (void)e1;
    return e2;  // Return the second edge ID as the "semantic edge"
}

cos_status_t cos_semantic_get_role(const cos_semantic_graph_t* sg,
                                    cos_graph_edge_id_t edge,
                                    cos_semantic_role_t* out_role) {
    if (!sg || !out_role) return COS_ERROR_NULL;

    cos_graph_edge_t e;
    cos_status_t status = cos_graph_get_edge(sg->graph, edge, &e);
    if (status != COS_OK) return status;

    *out_role = (cos_semantic_role_t)((int)e.weight);
    return COS_OK;
}

// ── Semantic Queries ─────────────────────────────────────────────────────

size_t cos_semantic_find_type(const cos_semantic_graph_t* sg,
                               cos_semantic_type_t type,
                               cos_graph_node_id_t* out_nodes,
                               size_t max_nodes) {
    if (!sg || !out_nodes || max_nodes == 0) return 0;

    size_t found = 0;
    size_t node_count = cos_graph_node_count(sg->graph);

    // For simplicity, scan all slots. A production version would maintain type indices.
    // Linear scan is fine for small-to-medium semantic graphs.
    // We iterate node IDs linearly.
    for (cos_graph_node_id_t i = 0; i < (cos_graph_node_id_t)node_count + 64 && found < max_nodes; i++) {
        if (!cos_graph_has_node(sg->graph, i)) continue;

        cos_semantic_node_t sem_node;
        if (cos_semantic_get_node(sg, i, &sem_node) == COS_OK) {
            if (sem_node.type == type) {
                out_nodes[found++] = i;
            }
        }
    }

    return found;
}

cos_graph_node_id_t cos_semantic_root(const cos_semantic_graph_t* sg) {
    return sg ? sg->root_id : COS_NODE_ID_NULL;
}

// ── Serialization ────────────────────────────────────────────────────────

cos_status_t cos_semantic_serialize(const cos_semantic_graph_t* sg,
                                     cos_allocator_t* alloc,
                                     void** out_data,
                                     size_t* out_size) {
    if (!sg || !alloc || !out_data || !out_size) return COS_ERROR_NULL;

    // Simple binary serialization format:
    // [magic:4][version:4][node_count:4][edge_count:4][nodes_data][edges_data]

    size_t node_count = cos_graph_node_count(sg->graph);
    size_t edge_count = cos_graph_edge_count(sg->graph);

    // Rough size estimate (simplified)
    size_t size = 16 + node_count * 24 + edge_count * 24;
    char* buf = (char*)alloc->alloc(alloc, size, alignof(max_align_t));
    if (!buf) return COS_ERROR_NOMEM;

    size_t offset = 0;
    memcpy(buf + offset, "COSG", 4); offset += 4;  // Magic
    memcpy(buf + offset, &(uint32_t){1}, 4);        offset += 4;  // Version

    // Stub for full serialization
    *out_data = buf;
    *out_size = offset;

    return COS_OK;
}

cos_semantic_graph_t* cos_semantic_deserialize(const void* data, size_t size, cos_allocator_t* alloc) {
    (void)data;
    (void)size;
    if (!alloc) alloc = cos_sys_allocator();
    return cos_semantic_create(alloc);  // Stub
}

// ── Introspection ────────────────────────────────────────────────────────

size_t cos_semantic_memory_used(const cos_semantic_graph_t* sg) {
    if (!sg) return 0;
    return sizeof(cos_semantic_graph_t) + cos_graph_memory_used(sg->graph);
}

cos_graph_t* cos_semantic_get_graph(const cos_semantic_graph_t* sg) {
    if (!sg) return NULL;
    return sg->graph;
}
