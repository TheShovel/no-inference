// reasoning.h — Symbolic Reasoning Engine
//
// Design: Modular symbolic reasoning system. Each reasoning module
// is independent and operates on semantic graphs.
//
// Modules:
//   - Logic: deduction, abduction, syllogism
//   - Math: arithmetic, comparison, units
//   - Temporal: time expressions, ordering, duration
//   - Comparison: equality, similarity, difference
//   - Constraints: constraint satisfaction, feasibility
//   - Decision: decision trees, rule evaluation
//   - Graph: graph traversal, path finding
//
// Memory: Per-reasoning-session arena for scratch work.
// Results are structured facts, not text.

#ifndef COS_REASONING_H
#define COS_REASONING_H

#include "cos/core.h"
#include "cos/semantic.h"
#include "cos/knowledge.h"
#include "cos/allocator.h"
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

// ── Reasoning Module Types ───────────────────────────────────────────────
typedef uint32_t cos_reasoning_module_t;

enum {
    COS_REASON_LOGIC        = 0,
    COS_REASON_MATH         = 1,
    COS_REASON_TEMPORAL     = 2,
    COS_REASON_COMPARISON   = 3,
    COS_REASON_CONSTRAINTS  = 4,
    COS_REASON_DECISION     = 5,
    COS_REASON_GRAPH        = 6,
    COS_REASON_COUNT        = 7,
};

// ── Reasoning Result ─────────────────────────────────────────────────────
typedef struct cos_reason_result_s {
    cos_semantic_graph_t* result_graph;  // Resulting semantic graph
    float                 confidence;    // Confidence in result (0.0–1.0)
    cos_string_id_t       explanation;   // Explanation of reasoning chain
    uint32_t              steps_taken;   // Number of reasoning steps
    uint32_t              flags;         // Result flags
} cos_reason_result_t;

// ── Opaque Reasoning Engine ──────────────────────────────────────────────
typedef struct cos_reasoning_s cos_reasoning_t;

typedef struct cos_reasoning_config_s {
    cos_allocator_t*      allocator;
    cos_allocator_t*      scratch;     // Arena for per-operation scratch
    cos_knowledge_base_t* knowledge;   // Optional knowledge base access
} cos_reasoning_config_t;

// ── Lifecycle ────────────────────────────────────────────────────────────
cos_reasoning_t* cos_reasoning_create(const cos_reasoning_config_t* config);
void             cos_reasoning_destroy(cos_reasoning_t* re);

// ── Core Reasoning ───────────────────────────────────────────────────────
// Run reasoning on a semantic graph. Module selection is automatic
// based on graph content, or explicit via `modules` bitmask.
cos_status_t cos_reasoning_reason(cos_reasoning_t* re,
                                   const cos_semantic_graph_t* input,
                                   cos_reason_result_t* out_result);

// Run reasoning with specific modules only.
cos_status_t cos_reasoning_reason_with(cos_reasoning_t* re,
                                       const cos_semantic_graph_t* input,
                                       uint32_t module_mask,
                                       cos_reason_result_t* out_result);

// ── Module Introspection ─────────────────────────────────────────────────
const char* cos_reasoning_module_name(cos_reasoning_module_t module);
bool        cos_reasoning_module_available(const cos_reasoning_t* re, cos_reasoning_module_t module);

#ifdef __cplusplus
}
#endif

#endif // COS_REASONING_H
