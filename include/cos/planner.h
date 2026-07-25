// planner.h — Execution Planner
//
// Design: The planner receives a semantic graph and produces an
// execution plan. It does NOT execute anything — it only decides
// WHAT should run and in what order.
//
// The planner inspects the semantic graph to determine:
//   - Is this a question? → knowledge search + reasoning
//   - Is this a command? → tool execution
//   - Is this a statement? → memory storage
//   - Does it need follow-up? → conversation management
//
// Memory: Compact plan representation — contiguous array of steps.
// Plans are stored in a single allocation.

#ifndef COS_PLANNER_H
#define COS_PLANNER_H

#include "cos/core.h"
#include "cos/semantic.h"
#include "cos/allocator.h"
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

// ── Plan Step Types ──────────────────────────────────────────────────────
typedef uint32_t cos_plan_step_type_t;

enum {
    COS_STEP_ANALYZE       = 0,   // Analyze the semantic graph
    COS_STEP_KNOWLEDGE_QUERY = 1, // Query knowledge base
    COS_STEP_MEMORY_QUERY  = 2,   // Query conversation memory
    COS_STEP_MEMORY_STORE  = 3,   // Store in conversation memory
    COS_STEP_REASON        = 4,   // Perform symbolic reasoning
    COS_STEP_TOOL_EXEC     = 5,   // Execute a tool
    COS_STEP_SEARCH        = 6,   // Search external sources
    COS_STEP_GENERATE      = 7,   // Generate language output
    COS_STEP_FOLLOW_UP     = 8,   // Need follow-up question
    COS_STEP_WAIT          = 9,   // Wait for user input
};

// ── Plan Step ────────────────────────────────────────────────────────────
typedef struct cos_plan_step_s {
    cos_plan_step_type_t type;
    cos_string_id_t      target;    // Target subsystem or tool name
    cos_graph_node_id_t  graph_node;// Relevant semantic graph node
    uint32_t             priority;  // Execution priority (0 = highest)
    uint32_t             flags;     // Step-specific flags
} cos_plan_step_t;

// ── Plan ─────────────────────────────────────────────────────────────────
typedef struct cos_plan_s {
    cos_plan_step_t* steps;
    size_t           step_count;
    size_t           step_capacity;
    cos_string_id_t  intent;        // Classified intent
    float            confidence;    // Overall plan confidence
} cos_plan_t;

// ── Opaque Planner ───────────────────────────────────────────────────────
typedef struct cos_planner_s cos_planner_t;

// ── Lifecycle ────────────────────────────────────────────────────────────
cos_planner_t* cos_planner_create(cos_allocator_t* alloc);
void           cos_planner_destroy(cos_planner_t* planner);

// ── Planning ─────────────────────────────────────────────────────────────
// Build a plan from a semantic graph. The caller must call
// cos_plan_destroy() on the returned plan.
cos_status_t cos_planner_plan(cos_planner_t* planner, const cos_semantic_graph_t* graph, cos_plan_t* out_plan);

// ── Plan Management ──────────────────────────────────────────────────────
void          cos_plan_init(cos_plan_t* plan);
void          cos_plan_destroy(cos_planner_t* planner, cos_plan_t* plan);
cos_status_t  cos_plan_add_step(cos_planner_t* planner, cos_plan_t* plan, cos_plan_step_type_t type, cos_string_id_t target, cos_graph_node_id_t graph_node);
cos_status_t  cos_plan_optimize(cos_planner_t* planner, cos_plan_t* plan);  // Reorder/merge steps

// ── Introspection ────────────────────────────────────────────────────────
const char* cos_plan_step_type_name(cos_plan_step_type_t type);

#ifdef __cplusplus
}
#endif

#endif // COS_PLANNER_H
