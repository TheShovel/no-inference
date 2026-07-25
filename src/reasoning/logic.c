// logic.c — Logic Reasoning Module
//
// Design: Simple deductive reasoning on semantic graphs.
// Supports:
//   - Syllogism: if A→B and B→C then A→C
//   - Modus ponens: if A and A→B then B
//   - Transitive closure of relations
//   - Contradiction detection
//
// Memory: Uses scratch arena for temporary work. Outputs to existing graph.

#include "cos/core.h"
#include "cos/reasoning.h"
#include "cos/semantic.h"
#include "cos/allocator.h"
#include "cos/string_intern.h"
#include <string.h>

// ── Internal helpers ──────────────────────────────────────────────────────

// Maximum number of intermediate relation entries we track
#define MAX_RELS 256
#define MAX_ENTS 128

typedef struct {
    cos_graph_node_id_t subj;  // subject entity node id
    cos_graph_node_id_t obj;   // object entity node id
} isa_pair_t;

// Check if a graph node is a COS_SEMANTIC_RELATION type
static inline bool is_rel_node(const cos_semantic_graph_t* sg, cos_graph_node_id_t id) {
    cos_semantic_node_t n;
    return cos_semantic_get_node(sg, id, &n) == COS_OK && n.type == COS_SEMANTIC_RELATION;
}

// Extract (subject, object) pairs from "be" verb statements.
// Returns the number of pairs found.
static size_t find_isa_pairs(const cos_semantic_graph_t* input,
                             isa_pair_t* pairs, size_t max_pairs) {
    cos_graph_t* g = cos_semantic_get_graph(input);
    if (!g) return 0;

    cos_graph_node_id_t actions[64];
    size_t n_actions = cos_semantic_find_type(input, COS_SEMANTIC_ACTION, actions, 64);

    size_t count = 0;

    for (size_t ai = 0; ai < n_actions && count < max_pairs; ai++) {
        cos_semantic_node_t verb_node;
        if (cos_semantic_get_node(input, actions[ai], &verb_node) != COS_OK)
            continue;

        // We're looking for "be" verbs (is, are, was, were, am, be)
        // For simplicity, check if lemma indicates a form of "be"
        // Since we don't have string comparison on interned IDs directly,
        // we match against known string IDs. Instead, we rely on the
        // graph structure: any ACTION with both a SUBJECT and an OBJECT
        // edge represents a predication we can reason over.
        // (This is more general than just "be" verbs.)

        cos_graph_node_id_t subject = COS_NODE_ID_NULL;
        cos_graph_node_id_t object  = COS_NODE_ID_NULL;

        // Check incoming edges (to find subject via SUBJECT role)
        size_t in_count;
        const cos_graph_edge_t* in_edges = cos_graph_in_edges(g, actions[ai], &in_count);
        if (in_edges) {
            for (size_t i = 0; i < in_count; i++) {
                const cos_graph_edge_t* e = &in_edges[i];
                if (e->to != actions[ai]) continue;
                // e->from should be a RELATION node
                if (!is_rel_node(input, e->from)) continue;

                // The role is encoded in this edge's weight
                cos_semantic_role_t role = (cos_semantic_role_t)((int)e->weight);
                if (role == COS_ROLE_SUBJECT) {
                    // Find the actual subject by looking at incoming edges to the RELATION node
                    size_t r_in_count;
                    const cos_graph_edge_t* r_in = cos_graph_in_edges(g, e->from, &r_in_count);
                    if (r_in) {
                        for (size_t j = 0; j < r_in_count; j++) {
                            if (r_in[j].to == e->from) {
                                subject = r_in[j].from;
                                break;
                            }
                        }
                    }
                }
            }
        }

        // Check outgoing edges (to find object via OBJECT role)
        size_t out_count;
        const cos_graph_edge_t* out_edges = cos_graph_out_edges(g, actions[ai], &out_count);
        if (out_edges) {
            for (size_t i = 0; i < out_count; i++) {
                const cos_graph_edge_t* e = &out_edges[i];
                if (e->from != actions[ai]) continue;
                if (!is_rel_node(input, e->to)) continue;

                size_t r_out_count;
                const cos_graph_edge_t* r_out = cos_graph_out_edges(g, e->to, &r_out_count);
                if (r_out) {
                    for (size_t j = 0; j < r_out_count; j++) {
                        if (r_out[j].from == e->to) {
                            cos_semantic_role_t role = (cos_semantic_role_t)((int)r_out[j].weight);
                            if (role == COS_ROLE_OBJECT) {
                                object = r_out[j].to;
                                break;
                            }
                        }
                    }
                }
            }
        }

        if (subject != COS_NODE_ID_NULL && object != COS_NODE_ID_NULL) {
            pairs[count].subj = subject;
            pairs[count].obj  = object;
            count++;
        }
    }

    return count;
}

// Check if a relation between subj and obj already exists in the output graph
static bool has_relation(cos_semantic_graph_t* output,
                         cos_graph_node_id_t subj,
                         cos_graph_node_id_t obj) {
    cos_graph_t* g = cos_semantic_get_graph(output);
    if (!g) return false;

    size_t out_count;
    const cos_graph_edge_t* edges = cos_graph_out_edges(g, subj, &out_count);
    if (!edges) return false;

    for (size_t i = 0; i < out_count; i++) {
        if (edges[i].from != subj) continue;
        if (!is_rel_node(output, edges[i].to)) continue;

        size_t r_out_count;
        const cos_graph_edge_t* r_out = cos_graph_out_edges(g, edges[i].to, &r_out_count);
        if (!r_out) continue;

        for (size_t j = 0; j < r_out_count; j++) {
            if (r_out[j].from == edges[i].to && r_out[j].to == obj) {
                return true;
            }
        }
    }
    return false;
}

// ── Main Module Entry ─────────────────────────────────────────────────────

cos_status_t cos_reason_logic(cos_reasoning_t* re,
                               const cos_semantic_graph_t* input,
                               cos_semantic_graph_t* output,
                               float* out_confidence,
                               uint32_t* out_steps) {
    if (!re || !input || !output) return COS_ERROR_NULL;

    uint32_t steps = 0;

    isa_pair_t pairs[MAX_RELS];
    size_t n_pairs = find_isa_pairs(input, pairs, MAX_RELS);

    // ── Syllogism & Transitive Closure ─────────────────────────────────
    // Build an adjacency list for is-a relations and compute transitive closure
    // We use Floyd-Warshall-like approach on the small set of entities

    // First, collect all unique entity IDs from the pairs
    cos_graph_node_id_t entities[MAX_ENTS];
    size_t n_entities = 0;

    for (size_t i = 0; i < n_pairs; i++) {
        bool has_subj = false, has_obj = false;
        for (size_t j = 0; j < n_entities; j++) {
            if (entities[j] == pairs[i].subj) has_subj = true;
            if (entities[j] == pairs[i].obj)  has_obj = true;
        }
        if (!has_subj && n_entities < MAX_ENTS) entities[n_entities++] = pairs[i].subj;
        if (!has_obj   && n_entities < MAX_ENTS) entities[n_entities++] = pairs[i].obj;
    }

    // Build adjacency matrix (as simple reachability)
    bool reachable[MAX_ENTS][MAX_ENTS];
    memset(reachable, 0, sizeof(reachable));

    for (size_t i = 0; i < n_pairs; i++) {
        size_t si = n_entities, oi = n_entities;
        for (size_t j = 0; j < n_entities; j++) {
            if (entities[j] == pairs[i].subj) si = j;
            if (entities[j] == pairs[i].obj)  oi = j;
        }
        if (si < n_entities && oi < n_entities) {
            reachable[si][oi] = true;
        }
    }

    // Transitive closure (Floyd-Warshall)
    for (size_t k = 0; k < n_entities; k++) {
        for (size_t i = 0; i < n_entities; i++) {
            for (size_t j = 0; j < n_entities; j++) {
                if (reachable[i][k] && reachable[k][j] && !reachable[i][j]) {
                    reachable[i][j] = true;
                }
            }
        }
    }

    // Add deduced transitive relations to output graph
    for (size_t i = 0; i < n_entities; i++) {
        for (size_t j = 0; j < n_entities; j++) {
            if (i == j) continue;
            if (!reachable[i][j]) continue;

            // Check if this was an original pair or newly deduced
            bool was_original = false;
            for (size_t p = 0; p < n_pairs; p++) {
                if (pairs[p].subj == entities[i] && pairs[p].obj == entities[j]) {
                    was_original = true;
                    break;
                }
            }

            if (!was_original && !has_relation(output, entities[i], entities[j])) {
                cos_semantic_add_edge(output, entities[i], entities[j],
                                      COS_ROLE_ATTRIBUTE, 0.9f);
                steps++;
            }
        }
    }

    // ── Contradiction Detection ───────────────────────────────────────
    // Look for pairs where A→B and A→C where B and C are different but
    // semantically incompatible (same entity ID used for different things)
    // Simple check: if A "is" B and A "is" C and B != C, that's contradictory
    // for single-valued attributes.
    uint32_t contradictions = 0;
    for (size_t i = 0; i < n_pairs; i++) {
        for (size_t j = i + 1; j < n_pairs; j++) {
            if (pairs[i].subj == pairs[j].subj && pairs[i].obj != pairs[j].obj) {
                // Mark contradiction by adding a conflicting edge with low confidence
                cos_semantic_add_edge(output, pairs[i].subj, pairs[j].obj,
                                      COS_ROLE_QUALIFIER, 0.0f);
                contradictions++;
                steps++;
            }
        }
    }

    // ── Modus Ponens ──────────────────────────────────────────────────
    // Look for statement nodes that assert a truth, combined with
    // conditional (if-then) structures. For each ACTION node with
    // roles CAUSE or CONDITION, check if the antecedent is asserted.
    cos_graph_t* g = cos_semantic_get_graph(input);
    if (g) {
        cos_graph_node_id_t statements[64];
        size_t n_statements = cos_semantic_find_type(input, COS_SEMANTIC_STATEMENT, statements, 64);

        for (size_t si = 0; si < n_statements; si++) {
            cos_semantic_node_t sn;
            if (cos_semantic_get_node(input, statements[si], &sn) != COS_OK) continue;

            // If the statement has high confidence, it's asserted as true
            if (sn.confidence > 0.5f) {
                // Check outgoing edges for CONDITION or CAUSE roles
                size_t out_count;
                const cos_graph_edge_t* out_edges = cos_graph_out_edges(g, statements[si], &out_count);
                if (!out_edges) continue;

                for (size_t ei = 0; ei < out_count; ei++) {
                    if (out_edges[ei].from != statements[si]) continue;
                    if (!is_rel_node(input, out_edges[ei].to)) continue;

                    size_t r_out_count;
                    const cos_graph_edge_t* r_out = cos_graph_out_edges(g, out_edges[ei].to, &r_out_count);
                    if (!r_out) continue;

                    for (size_t rj = 0; rj < r_out_count; rj++) {
                        if (r_out[rj].from != out_edges[ei].to) continue;
                        cos_semantic_role_t role = (cos_semantic_role_t)((int)r_out[rj].weight);
                        if (role == COS_ROLE_CONDITION || role == COS_ROLE_CAUSE) {
                            // The target is the deduced consequent
                            cos_graph_node_id_t consequent = r_out[rj].to;
                            cos_semantic_node_t cons_node;
                            if (cos_semantic_get_node(input, consequent, &cons_node) == COS_OK) {
                                // Copy the consequent into the output with higher confidence
                                cos_graph_node_id_t new_id = cos_semantic_add_node(
                                    output, cons_node.type,
                                    cons_node.text, cons_node.lemma,
                                    cons_node.confidence * 0.95f);
                                if (new_id != COS_NODE_ID_NULL) {
                                    cos_semantic_add_edge(output,
                                        cos_semantic_root(output), new_id,
                                        COS_ROLE_REFERENCE, 0.8f);
                                    steps++;
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    if (out_confidence) *out_confidence = (contradictions > 0) ? 0.5f : 0.95f;
    if (out_steps)      *out_steps      = steps;

    return COS_OK;
}
