// conversation.c — Conversation Engine Implementation
//
// Design: Coordinates the full conversation pipeline:
//   Input → Parser → Planner → Reasoning → Language → Generator → Output
//
// Each turn stores structured facts in conversation memory.
// Long-term memory persists; per-turn memory is reset each turn.
//
// Memory: Per-conversation state is an arena for the current turn.
// Conversation memory is stored as facts in a knowledge base.


#include "cos/conversation.h"
#include "cos/parser.h"
#include "cos/planner.h"
#include "cos/reasoning.h"
#include "cos/knowledge.h"
#include "cos/language.h"
#include "cos/generator.h"
#include "cos/semantic.h"
#include <string.h>
#include "cos/allocator.h"
#include "cos/string_intern.h"
#include <stdalign.h>

#ifdef __cplusplus
extern "C" {
#endif

// ── Conversation ─────────────────────────────────────────────────────────
struct cos_conversation_s {
    cos_allocator_t*     alloc;
    cos_allocator_t*     scratch;       // Per-turn arena (reset each turn)
    cos_string_table_t*  string_table;
    cos_knowledge_base_t* knowledge;     // Long-term memory
    cos_knowledge_base_t* working_memory; // Turn-specific memory

    // Subsystems
    cos_parser_t*        parser;
    cos_planner_t*       planner;
    cos_reasoning_t*     reasoner;
    cos_language_t*      language;
    cos_generator_t*     generator;

    // Turn history
    cos_turn_t*          turns;
    size_t               turn_count;
    size_t               turn_capacity;

    // Response buffer (reused across turns)
    char*                response_buffer;
    size_t               response_buffer_size;

    // Metadata
    cos_timestamp_t      start_time;
    size_t               total_memory;
};

// ── Lifecycle ────────────────────────────────────────────────────────────

cos_conversation_t* cos_conversation_create(const cos_conversation_config_t* config) {
    if (!config) return NULL;

    cos_conversation_t* conv = (cos_conversation_t*)
        config->allocator->alloc(config->allocator, sizeof(cos_conversation_t), alignof(cos_conversation_t));
    if (!conv) return NULL;

    conv->alloc     = config->allocator;
    conv->scratch   = config->scratch_arena ? config->scratch_arena : config->allocator;
    conv->string_table  = config->string_table;
    conv->knowledge     = config->knowledge;
    conv->working_memory = config->working_memory ? config->working_memory : config->knowledge;

    // Initialize subsystems
    cos_parser_config_t parser_config;
    parser_config.string_table = config->string_table;
    parser_config.allocator    = config->allocator;
    parser_config.scratch      = conv->scratch;
    conv->parser = cos_parser_create(&parser_config);

    conv->planner = cos_planner_create(config->allocator);

    cos_reasoning_config_t reason_config;
    reason_config.allocator = config->allocator;
    reason_config.scratch   = conv->scratch;
    reason_config.knowledge = config->knowledge;
    conv->reasoner = cos_reasoning_create(&reason_config);

    cos_language_config_t lang_config;
    lang_config.allocator     = config->allocator;
    lang_config.scratch       = conv->scratch;
    lang_config.string_table  = config->string_table;
    lang_config.default_style = COS_STYLE_CASUAL;
    lang_config.templates_path = NULL;
    conv->language = cos_language_create(&lang_config);

    cos_generator_config_t gen_config;
    gen_config.allocator    = config->allocator;
    gen_config.scratch      = conv->scratch;
    gen_config.string_table = config->string_table;
    conv->generator = cos_generator_create(&gen_config);

    // Turn history
    conv->turn_capacity = 64;
    conv->turns = (cos_turn_t*)config->allocator->alloc(config->allocator,
        conv->turn_capacity * sizeof(cos_turn_t), alignof(cos_turn_t));
    conv->turn_count = 0;

    // Response buffer
    conv->response_buffer_size = 4096;
    conv->response_buffer = (char*)config->allocator->alloc(config->allocator,
        conv->response_buffer_size, alignof(char));

    conv->start_time    = cos_timestamp_now();
    conv->total_memory  = sizeof(cos_conversation_t) +
                          conv->turn_capacity * sizeof(cos_turn_t) +
                          conv->response_buffer_size;

    return conv;
}

void cos_conversation_destroy(cos_conversation_t* conv) {
    if (!conv) return;

    // Clean up plan steps in each turn
    for (size_t i = 0; i < conv->turn_count; i++) {
        cos_turn_t* turn = &conv->turns[i];
        if (turn->plan.steps) {
            cos_plan_destroy(conv->planner, &turn->plan);
        }
        if (turn->semantics) {
            cos_semantic_destroy(turn->semantics);
        }
    }

    if (conv->parser)    cos_parser_destroy(conv->parser);
    if (conv->planner)   cos_planner_destroy(conv->planner);
    if (conv->reasoner)  cos_reasoning_destroy(conv->reasoner);
    if (conv->generator) cos_generator_destroy(conv->generator);
    if (conv->language)  cos_language_destroy(conv->language);

    if (conv->turns) conv->alloc->free(conv->alloc, conv->turns,
        conv->turn_capacity * sizeof(cos_turn_t));
    if (conv->response_buffer) conv->alloc->free(conv->alloc, conv->response_buffer,
        conv->response_buffer_size);

    conv->alloc->free(conv->alloc, conv, sizeof(cos_conversation_t));
}

// ── Turn Processing ──────────────────────────────────────────────────────

cos_status_t cos_conversation_process(cos_conversation_t* conv,
                                       cos_string_view_t input,
                                       const char** out_response,
                                       size_t* out_response_length) {
    if (!conv || !out_response || !out_response_length) return COS_ERROR_NULL;

    cos_timestamp_t turn_start = cos_timestamp_now();

    // Ensure capacity for new turn
    if (conv->turn_count >= conv->turn_capacity) {
        size_t new_cap = conv->turn_capacity * 2;
        cos_turn_t* new_turns = (cos_turn_t*)conv->alloc->realloc(conv->alloc,
            conv->turns, conv->turn_capacity * sizeof(cos_turn_t),
            new_cap * sizeof(cos_turn_t), alignof(cos_turn_t));
        if (!new_turns) return COS_ERROR_NOMEM;
        conv->turns = new_turns;
        conv->turn_capacity = new_cap;
    }

    cos_turn_t* turn = &conv->turns[conv->turn_count];
    memset(turn, 0, sizeof(cos_turn_t));
    turn->input     = input;
    turn->timestamp = turn_start;

    cos_status_t status;

    // ── Stage 1: Parse ──────────────────────────────────────────────────
    status = cos_parser_parse(conv->parser, input, &turn->semantics);
    if (status != COS_OK) {
        // Fall back to a simple acknowledgment
        const char* fallback = "I received your message.";
        size_t flen = strlen(fallback);
        memcpy(conv->response_buffer, fallback, flen);
        conv->response_buffer[flen] = '\0';
        *out_response        = conv->response_buffer;
        *out_response_length = flen;
        turn->response        = conv->response_buffer;
        turn->response_length = flen;
        turn->processing_time_ms = (float)(cos_timestamp_now() - turn_start);
        conv->turn_count++;
        return COS_OK;
    }

    // ── Stage 2: Plan ───────────────────────────────────────────────────
    cos_plan_init(&turn->plan);
    status = cos_planner_plan(conv->planner, turn->semantics, &turn->plan);
    if (status != COS_OK) {
        // Fallback
        const char* fallback = "I'm not sure how to respond.";
        size_t flen = strlen(fallback);
        memcpy(conv->response_buffer, fallback, flen);
        conv->response_buffer[flen] = '\0';
        *out_response        = conv->response_buffer;
        *out_response_length = flen;
        turn->response        = conv->response_buffer;
        turn->response_length = flen;
        turn->processing_time_ms = (float)(cos_timestamp_now() - turn_start);
        conv->turn_count++;
        return COS_OK;
    }

    // -- Stage 3: Execute Plan -----------------------------------------------
    // Track query results to pass to the generator
    cos_query_result_t query_result = {NULL, 0, 0};

    // Clear any stale context facts from previous turns
    cos_generator_set_context(conv->generator, NULL, 0);

    for (size_t i = 0; i < turn->plan.step_count; i++) {
        cos_plan_step_t* step = &turn->plan.steps[i];

        switch (step->type) {
            case COS_STEP_ANALYZE:
                break;

            case COS_STEP_KNOWLEDGE_QUERY: {
                // Query knowledge base for facts matching entities in this turn.
                if (turn->semantics && conv->working_memory) {
                    cos_graph_node_id_t entities[32];
                    size_t n = cos_semantic_find_type(turn->semantics,
                        COS_SEMANTIC_ENTITY, entities, 32);

                    // First, try query with NO filter to check if ANY facts exist
                    cos_query_t q;
                    memset(&q, 0, sizeof(q));
                    q.max_results = 8;
                    cos_knowledge_query(conv->working_memory, &q, &query_result, conv->scratch);

                    // If no unfiltered results, try per-entity queries
                    if (query_result.count == 0) {
                        for (size_t ei = 0; ei < n; ei++) {
                            cos_semantic_node_t en;
                            if (cos_semantic_get_node(turn->semantics, entities[ei], &en) != COS_OK)
                                continue;
                            if (en.text == COS_STRING_ID_NULL) continue;

                            memset(&q, 0, sizeof(q));
                            q.max_results = 8;
                            // Try all filter positions
                            q.subject = en.text;
                            cos_knowledge_query(conv->working_memory, &q, &query_result, conv->scratch);
                            if (query_result.count > 0) break;

                            memset(&q, 0, sizeof(q));
                            q.max_results = 8;
                            q.object = en.text;
                            cos_knowledge_query(conv->working_memory, &q, &query_result, conv->scratch);
                            if (query_result.count > 0) break;
                        }
                    }
                }
                break;
            }

            case COS_STEP_MEMORY_STORE:
                // Store facts from this turn's parsed semantics
                if (turn->semantics && conv->working_memory) {
                    cos_knowledge_store_graph(conv->working_memory, turn->semantics);
                }
                break;

            case COS_STEP_REASON:
                cos_reasoning_reason(conv->reasoner, turn->semantics, &turn->reason_result);
                break;

            case COS_STEP_GENERATE: {
                // Pass any query results to the generator as context
                if (query_result.count > 0) {
                    cos_generator_set_context(conv->generator,
                        query_result.facts, query_result.count);
                }

                cos_semantic_graph_t* gen_graph = turn->reason_result.result_graph;
                if (!gen_graph) gen_graph = turn->semantics;

                size_t written = 0;
                cos_generator_generate(conv->generator, gen_graph,
                                        conv->response_buffer,
                                        conv->response_buffer_size,
                                        &written);
                turn->response        = conv->response_buffer;
                turn->response_length = written;
                break;
            }

            default:
                break;
        }
    }

    // If no response was generated, provide a default
    if (!turn->response || turn->response_length == 0) {
        const char* default_msg = "I processed your request.";
        size_t dlen = strlen(default_msg);
        memcpy(conv->response_buffer, default_msg, dlen + 1);
        turn->response        = conv->response_buffer;
        turn->response_length = dlen;
    }

    turn->processing_time_ms = (float)(cos_timestamp_now() - turn_start);
    conv->turn_count++;

    *out_response        = turn->response;
    *out_response_length = turn->response_length;

    return COS_OK;
}

// ── Memory ───────────────────────────────────────────────────────────────

cos_status_t cos_conversation_remember(cos_conversation_t* conv, const cos_fact_t* fact) {
    if (!conv || !fact) return COS_ERROR_NULL;
    return cos_knowledge_store(conv->working_memory, fact);
}

cos_status_t cos_conversation_recall(const cos_conversation_t* conv,
                                      const cos_query_t* query,
                                      cos_query_result_t* out_result,
                                      cos_allocator_t* scratch) {
    if (!conv || !query || !out_result) return COS_ERROR_NULL;
    return cos_knowledge_query(conv->working_memory, query, out_result, scratch);
}

// ── Introspection ────────────────────────────────────────────────────────

size_t cos_conversation_turn_count(const cos_conversation_t* conv) {
    return conv ? conv->turn_count : 0;
}

const cos_turn_t* cos_conversation_get_turn(const cos_conversation_t* conv, size_t index) {
    if (!conv || index >= conv->turn_count) return NULL;
    return &conv->turns[index];
}

cos_timestamp_t cos_conversation_start_time(const cos_conversation_t* conv) {
    return conv ? conv->start_time : 0;
}

size_t cos_conversation_memory_used(const cos_conversation_t* conv) {
    return conv ? conv->total_memory : 0;
}

#ifdef __cplusplus
}
#endif
