// planner.c — Execution Planner Implementation
//
// Design: The planner inspects a semantic graph and produces an ordered
// list of execution steps. It does NOT execute anything — it only decides
// what should happen.
//
// Decision tree:
//   Is there a question word? → Knowledge query + Reasoning
//   Is there an action verb with confidence? → Tool execution or memory store
//   Is there a statement? → Memory store (maybe + reasoning)
//   Is there ambiguity? → Follow-up question
//
// Memory: Plans are simple arrays of steps. No per-step allocations.

#include "cos/core.h"
#include "cos/planner.h"
#include "cos/semantic.h"
#include "cos/string_intern.h"
#include "cos/allocator.h"
#include <string.h>
#include <stdalign.h>

#ifdef __cplusplus
extern "C" {
#endif

// ── Planner Context ──────────────────────────────────────────────────────
struct cos_planner_s {
    cos_allocator_t* alloc;
};

// ── Intent Classification ────────────────────────────────────────────────
// Determines the user's intent from the semantic graph.
// Returns a string ID for the intent name.

static cos_string_id_t classify_intent(cos_planner_t* planner,
                                        const cos_semantic_graph_t* graph) {
    (void)planner;

    cos_graph_node_id_t nodes[64];
    size_t found;

    // Check for question words
    found = cos_semantic_find_type(graph, COS_SEMANTIC_QUESTION, nodes, 64);
    if (found > 0) {
        return 1;  // question
    }

    // Check for action
    found = cos_semantic_find_type(graph, COS_SEMANTIC_ACTION, nodes, 64);
    if (found > 0) {
        // Check if there are also entities (subjects/objects).
        // If action + entities present: likely a statement ("I like pizza")
        // If action alone: likely a command/imperative ("search", "run")
        cos_graph_node_id_t ents[32];
        size_t ec = cos_semantic_find_type(graph, COS_SEMANTIC_ENTITY, ents, 32);
        if (ec > 0) {
            return 3;  // statement (has subjects/objects)
        }
        return 2;  // command (imperative, no clear subject)
    }

    // Default: statement
    return 3;  // statement
}

// ── Lifecycle ────────────────────────────────────────────────────────────

cos_planner_t* cos_planner_create(cos_allocator_t* alloc) {
    if (!alloc) alloc = cos_sys_allocator();

    cos_planner_t* planner = (cos_planner_t*)
        alloc->alloc(alloc, sizeof(cos_planner_t), alignof(cos_planner_t));
    if (!planner) return NULL;

    planner->alloc = alloc;
    return planner;
}

void cos_planner_destroy(cos_planner_t* planner) {
    if (!planner) return;
    planner->alloc->free(planner->alloc, planner, sizeof(cos_planner_t));
}

// ── Planning ─────────────────────────────────────────────────────────────

cos_status_t cos_planner_plan(cos_planner_t* planner,
                               const cos_semantic_graph_t* graph,
                               cos_plan_t* out_plan) {
    if (!planner || !graph || !out_plan) return COS_ERROR_NULL;

    cos_plan_init(out_plan);
    out_plan->intent = classify_intent(planner, graph);
    out_plan->confidence = 0.8f;

    // Build steps based on intent
    if (out_plan->intent == 1) {
        // Question: analyze → knowledge query → reason → generate
        cos_plan_add_step(planner, out_plan, COS_STEP_ANALYZE,
                          COS_STRING_ID_NULL, cos_semantic_root(graph));
        cos_plan_add_step(planner, out_plan, COS_STEP_KNOWLEDGE_QUERY,
                          COS_STRING_ID_NULL, cos_semantic_root(graph));
        cos_plan_add_step(planner, out_plan, COS_STEP_REASON,
                          COS_STRING_ID_NULL, cos_semantic_root(graph));
        cos_plan_add_step(planner, out_plan, COS_STEP_GENERATE,
                          COS_STRING_ID_NULL, cos_semantic_root(graph));

    } else if (out_plan->intent == 2) {
        // Command: analyze → knowledge query → reason → tool → generate
        cos_plan_add_step(planner, out_plan, COS_STEP_ANALYZE,
                          COS_STRING_ID_NULL, cos_semantic_root(graph));
        cos_plan_add_step(planner, out_plan, COS_STEP_MEMORY_QUERY,
                          COS_STRING_ID_NULL, cos_semantic_root(graph));
        cos_plan_add_step(planner, out_plan, COS_STEP_TOOL_EXEC,
                          COS_STRING_ID_NULL, cos_semantic_root(graph));
        cos_plan_add_step(planner, out_plan, COS_STEP_GENERATE,
                          COS_STRING_ID_NULL, cos_semantic_root(graph));

    } else {
        // Statement: analyze → memory store → generate
        cos_plan_add_step(planner, out_plan, COS_STEP_ANALYZE,
                          COS_STRING_ID_NULL, cos_semantic_root(graph));
        cos_plan_add_step(planner, out_plan, COS_STEP_MEMORY_STORE,
                          COS_STRING_ID_NULL, cos_semantic_root(graph));
        cos_plan_add_step(planner, out_plan, COS_STEP_GENERATE,
                          COS_STRING_ID_NULL, cos_semantic_root(graph));
    }

    return COS_OK;
}

// ── Plan Management ──────────────────────────────────────────────────────

void cos_plan_init(cos_plan_t* plan) {
    if (!plan) return;
    plan->steps        = NULL;
    plan->step_count   = 0;
    plan->step_capacity= 0;
    plan->intent       = COS_STRING_ID_NULL;
    plan->confidence   = 0.0f;
}

void cos_plan_destroy(cos_planner_t* planner, cos_plan_t* plan) {
    if (!planner || !plan) return;
    if (plan->steps) {
        planner->alloc->free(planner->alloc, plan->steps,
            plan->step_capacity * sizeof(cos_plan_step_t));
    }
    plan->steps      = NULL;
    plan->step_count = 0;
    plan->step_capacity = 0;
}

cos_status_t cos_plan_add_step(cos_planner_t* planner,
                                cos_plan_t* plan,
                                cos_plan_step_type_t type,
                                cos_string_id_t target,
                                cos_graph_node_id_t graph_node) {
    if (!planner || !plan) return COS_ERROR_NULL;

    if (plan->step_count >= plan->step_capacity) {
        size_t new_cap = plan->step_capacity > 0 ? plan->step_capacity * 2 : 8;
        cos_plan_step_t* new_steps = (cos_plan_step_t*)
            planner->alloc->realloc(planner->alloc, plan->steps,
                plan->step_capacity * sizeof(cos_plan_step_t),
                new_cap * sizeof(cos_plan_step_t), alignof(cos_plan_step_t));
        if (!new_steps) return COS_ERROR_NOMEM;
        plan->steps = new_steps;
        plan->step_capacity = new_cap;
    }

    cos_plan_step_t* step = &plan->steps[plan->step_count++];
    step->type      = type;
    step->target    = target;
    step->graph_node = graph_node;
    step->priority  = (uint32_t)plan->step_count;
    step->flags     = 0;

    return COS_OK;
}

cos_status_t cos_plan_optimize(cos_planner_t* planner, cos_plan_t* plan) {
    (void)planner;
    (void)plan;
    // Stub: would merge adjacent compatible steps, reorder for efficiency
    return COS_OK;
}

// ── Introspection ────────────────────────────────────────────────────────

const char* cos_plan_step_type_name(cos_plan_step_type_t type) {
    switch (type) {
        case COS_STEP_ANALYZE:         return "analyze";
        case COS_STEP_KNOWLEDGE_QUERY: return "knowledge_query";
        case COS_STEP_MEMORY_QUERY:    return "memory_query";
        case COS_STEP_MEMORY_STORE:    return "memory_store";
        case COS_STEP_REASON:          return "reason";
        case COS_STEP_TOOL_EXEC:       return "tool_exec";
        case COS_STEP_SEARCH:          return "search";
        case COS_STEP_GENERATE:        return "generate";
        case COS_STEP_FOLLOW_UP:       return "follow_up";
        case COS_STEP_WAIT:            return "wait";
        default:                       return "unknown";
    }
}

#ifdef __cplusplus
}
#endif
