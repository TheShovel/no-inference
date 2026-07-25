// reasoning.c — Symbolic Reasoning Engine Implementation
//
// Design: Orchestrates multiple reasoning modules. Each module
// is an independent function operating on a semantic graph.
//
// Modules are selected automatically based on graph content,
// or explicitly specified with a module mask.
//
// Memory: Reasoning uses caller-provided scratch arena.
// Results are semantic sub-graphs (no string generation).

#include "cos/core.h"
#include "cos/reasoning.h"
#include "cos/semantic.h"
#include "cos/knowledge.h"
#include "cos/allocator.h"
#include <string.h>
#include <stdalign.h>

#ifdef __cplusplus
extern "C" {
#endif

// ── Reasoning Engine ─────────────────────────────────────────────────────
struct cos_reasoning_s {
    cos_allocator_t*      alloc;
    cos_allocator_t*      scratch;
    cos_knowledge_base_t* knowledge;
};

// ── Module Function Table ────────────────────────────────────────────────
// Each reasoning module processes a semantic graph and produces results.

typedef cos_status_t (*reasoning_module_fn_t)(cos_reasoning_t* re,
                                                const cos_semantic_graph_t* input,
                                                cos_semantic_graph_t* output,
                                                float* out_confidence,
                                                uint32_t* out_steps);

static const char* g_module_names[COS_REASON_COUNT] = {
    "logic", "math", "temporal", "comparison", "constraints", "decision", "graph"
};

// Module stubs (implementations in separate files)
extern cos_status_t cos_reason_logic(cos_reasoning_t* re,
                                      const cos_semantic_graph_t* input,
                                      cos_semantic_graph_t* output,
                                      float* out_confidence,
                                      uint32_t* out_steps);

extern cos_status_t cos_reason_math(cos_reasoning_t* re,
                                     const cos_semantic_graph_t* input,
                                     cos_semantic_graph_t* output,
                                     float* out_confidence,
                                     uint32_t* out_steps);

extern cos_status_t cos_reason_temporal(cos_reasoning_t* re,
                                         const cos_semantic_graph_t* input,
                                         cos_semantic_graph_t* output,
                                         float* out_confidence,
                                         uint32_t* out_steps);

// ── Lifecycle ────────────────────────────────────────────────────────────

cos_reasoning_t* cos_reasoning_create(const cos_reasoning_config_t* config) {
    if (!config) return NULL;

    cos_reasoning_t* re = (cos_reasoning_t*)
        config->allocator->alloc(config->allocator, sizeof(cos_reasoning_t), alignof(cos_reasoning_t));
    if (!re) return NULL;

    re->alloc     = config->allocator;
    re->scratch   = config->scratch ? config->scratch : config->allocator;
    re->knowledge = config->knowledge;

    return re;
}

void cos_reasoning_destroy(cos_reasoning_t* re) {
    if (!re) return;
    re->alloc->free(re->alloc, re, sizeof(cos_reasoning_t));
}

// ── Auto-select modules based on graph content ───────────────────────────
static uint32_t select_modules(const cos_semantic_graph_t* graph) {
    uint32_t mask = 0;

    cos_graph_node_id_t nodes[64];
    size_t found;

    // Check for math-related nodes
    found = cos_semantic_find_type(graph, COS_SEMANTIC_QUANTITY, nodes, 64);
    if (found > 0) mask |= (uint32_t)(1u << COS_REASON_MATH);

    // Check for temporal nodes
    found = cos_semantic_find_type(graph, COS_SEMANTIC_TIME, nodes, 64);
    if (found > 0) mask |= (uint32_t)(1u << COS_REASON_TEMPORAL);

    // Always include logic and comparison
    mask |= (uint32_t)((1u << COS_REASON_LOGIC) | (1u << COS_REASON_COMPARISON));

    // If no specific modules matched, include all basic ones
    if (mask == 0) {
        mask = (uint32_t)((1u << COS_REASON_LOGIC) | (1u << COS_REASON_COMPARISON) |
                          (1u << COS_REASON_DECISION));
    }

    return mask;
}

// ── Core Reasoning ───────────────────────────────────────────────────────

cos_status_t cos_reasoning_reason(cos_reasoning_t* re,
                                   const cos_semantic_graph_t* input,
                                   cos_reason_result_t* out_result) {
    if (!re || !input || !out_result) return COS_ERROR_NULL;

    uint32_t module_mask = select_modules(input);
    return cos_reasoning_reason_with(re, input, module_mask, out_result);
}

cos_status_t cos_reasoning_reason_with(cos_reasoning_t* re,
                                        const cos_semantic_graph_t* input,
                                        uint32_t module_mask,
                                        cos_reason_result_t* out_result) {
    if (!re || !input || !out_result) return COS_ERROR_NULL;

    memset(out_result, 0, sizeof(cos_reason_result_t));

    // Create output graph
    cos_semantic_graph_t* output = cos_semantic_create(re->alloc);
    if (!output) return COS_ERROR_NOMEM;

    out_result->result_graph = output;
    out_result->confidence   = 1.0f;
    out_result->steps_taken  = 0;

    // Run selected modules in order
    static const cos_reasoning_module_t module_order[] = {
        COS_REASON_LOGIC,
        COS_REASON_MATH,
        COS_REASON_TEMPORAL,
        COS_REASON_COMPARISON,
        COS_REASON_CONSTRAINTS,
        COS_REASON_DECISION,
        COS_REASON_GRAPH,
    };

    for (size_t i = 0; i < 7; i++) {
        cos_reasoning_module_t mod = module_order[i];
        if (!(module_mask & (1u << (uint32_t)mod))) continue;

        float mod_confidence = 0.0f;
        uint32_t mod_steps = 0;
        cos_status_t status = COS_OK;

        switch (mod) {
            case COS_REASON_LOGIC:
                status = cos_reason_logic(re, input, output, &mod_confidence, &mod_steps);
                break;
            case COS_REASON_MATH:
                status = cos_reason_math(re, input, output, &mod_confidence, &mod_steps);
                break;
            case COS_REASON_TEMPORAL:
                status = cos_reason_temporal(re, input, output, &mod_confidence, &mod_steps);
                break;
            default:
                // Other modules not yet implemented
                break;
        }

        if (status == COS_OK) {
            out_result->confidence *= mod_confidence;
            out_result->steps_taken += mod_steps;
        }
    }

    return COS_OK;
}

// ── Introspection ────────────────────────────────────────────────────────

const char* cos_reasoning_module_name(cos_reasoning_module_t module) {
    if (module < COS_REASON_COUNT) return g_module_names[module];
    return "unknown";
}

bool cos_reasoning_module_available(const cos_reasoning_t* re, cos_reasoning_module_t module) {
    (void)re;
    return module < COS_REASON_COUNT;
}

#ifdef __cplusplus
}
#endif
