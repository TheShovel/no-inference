// conversation.h — Conversation Engine
//
// Design: Manages the full conversation lifecycle.
// Coordinates all subsystems: parse → plan → reason → generate.
//
// Stores conversation memory as structured facts (not raw text).
// Each conversation turn produces facts stored in the knowledge base.
//
// Memory: Per-conversation state is minimal — an arena for the
// current turn and a handle to the structured memory store.

#ifndef COS_CONVERSATION_H
#define COS_CONVERSATION_H

#include "cos/core.h"
#include "cos/semantic.h"
#include "cos/planner.h"
#include "cos/reasoning.h"
#include "cos/knowledge.h"
#include "cos/parser.h"
#include "cos/language.h"
#include "cos/allocator.h"
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

// ── Turn Record ──────────────────────────────────────────────────────────
typedef struct cos_turn_s {
    cos_string_view_t      input;           // Raw user input
    cos_semantic_graph_t*  semantics;       // Parsed meaning
    cos_plan_t             plan;            // Execution plan
    cos_reason_result_t    reason_result;   // Reasoning output
    char*                  response;        // Generated response
    size_t                 response_length; // Response length
    cos_timestamp_t        timestamp;       // When the turn occurred
    float                  processing_time_ms;
} cos_turn_t;

// ── Conversation ─────────────────────────────────────────────────────────
typedef struct cos_conversation_s cos_conversation_t;

typedef struct cos_conversation_config_s {
    cos_allocator_t*        allocator;
    cos_allocator_t*        scratch_arena;
    cos_string_table_t*     string_table;
    cos_knowledge_base_t*   knowledge;
    cos_knowledge_base_t*   working_memory;
} cos_conversation_config_t;

// ── Lifecycle ────────────────────────────────────────────────────────────
cos_conversation_t* cos_conversation_create(const cos_conversation_config_t* config);
void                cos_conversation_destroy(cos_conversation_t* conv);

// ── Turn Processing ──────────────────────────────────────────────────────
// Process a single user utterance. Returns the generated response.
// The response pointer is valid until the next call to cos_conversation_process.
cos_status_t cos_conversation_process(cos_conversation_t* conv,
                                       cos_string_view_t input,
                                       const char** out_response,
                                       size_t* out_response_length);

// ── Memory ───────────────────────────────────────────────────────────────
// Store a fact in conversation memory.
cos_status_t cos_conversation_remember(cos_conversation_t* conv, const cos_fact_t* fact);
// Query conversation memory.
cos_status_t cos_conversation_recall(const cos_conversation_t* conv, const cos_query_t* query, cos_query_result_t* out_result, cos_allocator_t* scratch);

// ── Introspection ────────────────────────────────────────────────────────
size_t              cos_conversation_turn_count(const cos_conversation_t* conv);
const cos_turn_t*   cos_conversation_get_turn(const cos_conversation_t* conv, size_t index);
cos_timestamp_t     cos_conversation_start_time(const cos_conversation_t* conv);
size_t              cos_conversation_memory_used(const cos_conversation_t* conv);

#ifdef __cplusplus
}
#endif

#endif // COS_CONVERSATION_H
