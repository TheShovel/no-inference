// temporal.c — Temporal Reasoning Module
//
// Design: Reasons about time expressions, ordering, durations, and intervals.
// Processes time nodes in the semantic graph.
//
// Supported:
//   - Convert relative time expressions to absolute timestamps
//   - Establish temporal ordering (before, after, during, overlapping)
//   - Calculate durations between time points
//
// Memory: Uses scratch arena for temporary work.
// Timestamps are stored in node flags as Unix epoch seconds (uint32)
// or as relative offsets (biased signed encoding).

#include "cos/core.h"
#include "cos/reasoning.h"
#include "cos/semantic.h"
#include "cos/allocator.h"
#include "cos/string_intern.h"
#include <time.h>
#include <stdlib.h>

// ── Timestamp Encoding ────────────────────────────────────────────────────
// Absolute timestamps are stored as uint32 Unix epoch seconds in flags.
// Relative offsets (for "in 2 hours", "3 days ago") use a biased encoding.
// The high bit indicates relative vs absolute.

#define TS_ABSOLUTE_MASK  0x80000000u  // 0 = absolute, 1 = relative
#define TS_VALUE_MASK     0x7FFFFFFFu
#define TS_BIAS           0x40000000u   // Bias for signed relative values

// Unit type codes (matching math.c conventions)
#define UNIT_TIME  5   // s, min, hr

#define TS_FLAG_ABSOLUTE(t)  ((uint32_t)(t) & ~TS_ABSOLUTE_MASK)
#define TS_FLAG_RELATIVE(s)  (TS_ABSOLUTE_MASK | ((uint32_t)((s) + (int32_t)TS_BIAS) & TS_VALUE_MASK))

#define TS_IS_ABSOLUTE(f)    (!((f) & TS_ABSOLUTE_MASK))
#define TS_IS_RELATIVE(f)    ((f) & TS_ABSOLUTE_MASK)

#define TS_GET_ABSOLUTE(f)   ((cos_timestamp_t)((f) & TS_VALUE_MASK))
#define TS_GET_RELATIVE(f)   ((int64_t)(int32_t)(((f) & TS_VALUE_MASK) - TS_BIAS))

// ── Duration / Interval ───────────────────────────────────────────────────
typedef struct {
    cos_graph_node_id_t time_node;
    cos_timestamp_t     ts;    // Resolved absolute timestamp
    bool                has_ts;
} resolved_time_t;

// ── Helpers ───────────────────────────────────────────────────────────────

static inline bool is_rel_node(const cos_semantic_graph_t* sg, cos_graph_node_id_t id) {
    cos_semantic_node_t n;
    return cos_semantic_get_node(sg, id, &n) == COS_OK && n.type == COS_SEMANTIC_RELATION;
}

static cos_timestamp_t now_ts(void) {
    // Use cos_timestamp_now() if available, else fall back to time()
    return cos_timestamp_now();
}

// Resolve a TIME node's flags into an absolute timestamp.
// For relative times, we add the offset to "now".
static cos_timestamp_t resolve_timestamp(uint32_t flags) {
    if (TS_IS_ABSOLUTE(flags)) {
        return TS_GET_ABSOLUTE(flags);
    } else {
        int64_t offset = TS_GET_RELATIVE(flags);
        return now_ts() + offset;
    }
}

// Count TIME nodes connected to other TIME nodes via ROLE_TIME edges,
// and compute ordering relationships between them.
typedef enum { ORDER_BEFORE, ORDER_AFTER, ORDER_SAME, ORDER_DURING, ORDER_UNKNOWN } order_t;

static order_t determine_order(cos_timestamp_t a, cos_timestamp_t b) {
    if (a < b) return ORDER_BEFORE;
    if (a > b) return ORDER_AFTER;
    return ORDER_SAME;
}

// ── Main Module Entry ─────────────────────────────────────────────────────

cos_status_t cos_reason_temporal(cos_reasoning_t* re,
                                  const cos_semantic_graph_t* input,
                                  cos_semantic_graph_t* output,
                                  float* out_confidence,
                                  uint32_t* out_steps) {
    if (!re || !input || !output) return COS_ERROR_NULL;

    cos_graph_t* g = cos_semantic_get_graph(input);
    if (!g) return COS_ERROR_NULL;

    uint32_t steps = 0;

    // Step 1: Find all TIME nodes
    cos_graph_node_id_t time_nodes[64];
    size_t n_times = cos_semantic_find_type(input, COS_SEMANTIC_TIME, time_nodes, 64);

    if (n_times == 0) {
        if (out_confidence) *out_confidence = 1.0f;
        if (out_steps)      *out_steps      = 0;
        return COS_OK;
    }

    // Step 2: Resolve each TIME node to an absolute timestamp
    resolved_time_t resolved[64];
    size_t n_resolved = 0;

    for (size_t i = 0; i < n_times && n_resolved < 64; i++) {
        cos_semantic_node_t tn;
        if (cos_semantic_get_node(input, time_nodes[i], &tn) != COS_OK) continue;

        cos_timestamp_t ts = resolve_timestamp(tn.flags);

        // Copy TIME node with resolved timestamp into output graph
        cos_graph_node_id_t new_id = cos_semantic_add_node(
            output, COS_SEMANTIC_TIME, tn.text, tn.lemma, tn.confidence);
        if (new_id != COS_NODE_ID_NULL) {
            // Store the resolved absolute timestamp
            cos_semantic_node_t out_node;
            if (cos_semantic_get_node(output, new_id, &out_node) == COS_OK) {
                out_node.flags = TS_FLAG_ABSOLUTE((uint32_t)ts);
                cos_semantic_set_node(output, new_id, &out_node);
            }
            cos_semantic_add_edge(output, cos_semantic_root(output),
                                  new_id, COS_ROLE_REFERENCE, 0.8f);
        }

        resolved[n_resolved].time_node = time_nodes[i];
        resolved[n_resolved].ts        = ts;
        resolved[n_resolved].has_ts    = true;
        n_resolved++;
        steps++;
    }

    // Step 3: Establish temporal ordering between time nodes
    // For each pair of time nodes connected via the graph structure,
    // add ordering edges to the output.
    for (size_t i = 0; i < n_resolved; i++) {
        for (size_t j = i + 1; j < n_resolved; j++) {
            order_t ord = determine_order(resolved[i].ts, resolved[j].ts);
            if (ord == ORDER_UNKNOWN) continue;

            // Find the corresponding nodes in the output graph
            // (They were added in order, so we can look them up)
            // For simplicity, scan output for matching text/lemma
            cos_graph_node_id_t out_nodes[64];
            size_t n_out = cos_semantic_find_type(output, COS_SEMANTIC_TIME, out_nodes, 64);

            cos_graph_node_id_t out_i = COS_NODE_ID_NULL;
            cos_graph_node_id_t out_j = COS_NODE_ID_NULL;

            for (size_t k = 0; k < n_out; k++) {
                cos_semantic_node_t on;
                if (cos_semantic_get_node(output, out_nodes[k], &on) != COS_OK) continue;
                if (on.text == COS_STRING_ID_NULL) continue;

                // Match by text or lemma
                cos_semantic_node_t in_i, in_j;
                if (cos_semantic_get_node(input, resolved[i].time_node, &in_i) == COS_OK &&
                    (on.text == in_i.text || on.lemma == in_i.lemma)) {
                    out_i = out_nodes[k];
                }
                if (cos_semantic_get_node(input, resolved[j].time_node, &in_j) == COS_OK &&
                    (on.text == in_j.text || on.lemma == in_j.lemma)) {
                    out_j = out_nodes[k];
                }
            }

            if (out_i == COS_NODE_ID_NULL || out_j == COS_NODE_ID_NULL) continue;

            // Add ordering edge
            cos_semantic_role_t order_role;
            switch (ord) {
                case ORDER_BEFORE: order_role = COS_ROLE_CAUSE; break;   // A before B → A causes B
                case ORDER_AFTER:  order_role = COS_ROLE_PURPOSE; break; // A after B → A's purpose follows B
                case ORDER_SAME:   order_role = COS_ROLE_CONJUNCTION; break;
                case ORDER_DURING: order_role = COS_ROLE_MODIFIER; break;
                default: continue;
            }
            cos_semantic_add_edge(output, out_i, out_j, order_role, 0.8f);
            steps++;
        }
    }

    // Step 4: Calculate durations between time points
    // For pairs of time nodes with known ordering, compute the duration
    // and add a QUANTITY node representing the duration.
    for (size_t i = 0; i < n_resolved; i++) {
        for (size_t j = i + 1; j < n_resolved; j++) {
            cos_timestamp_t diff = resolved[j].ts - resolved[i].ts;
            if (diff < 0) diff = -diff;
            if (diff == 0) continue;

            // Encode duration as a QUANTITY node (unit = TIME)
            uint32_t duration_flags = 0;
            duration_flags = (uint32_t)(diff & 0xFFFF) | ((UNIT_TIME << 16) & 0xFFFF0000);

            cos_graph_node_id_t dur_id = cos_semantic_add_node(
                output, COS_SEMANTIC_QUANTITY,
                COS_STRING_ID_NULL, COS_STRING_ID_NULL, 0.9f);
            if (dur_id != COS_NODE_ID_NULL) {
                cos_semantic_node_t dn;
                if (cos_semantic_get_node(output, dur_id, &dn) == COS_OK) {
                    dn.flags = duration_flags;
                    cos_semantic_set_node(output, dur_id, &dn);
                }
                cos_semantic_add_edge(output, cos_semantic_root(output),
                                      dur_id, COS_ROLE_REFERENCE, 0.8f);
                steps++;
            }
        }
    }

    if (out_confidence) *out_confidence = 0.9f;
    if (out_steps)      *out_steps      = steps;

    return COS_OK;
}
