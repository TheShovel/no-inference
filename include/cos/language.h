// language.h — Language Generation Engine
//
// Design: Separates language from reasoning. The language engine
// takes a meaning graph and produces natural language text.
//
// Pipeline:
//   Meaning Graph → Sentence Plan → Grammar Application → Style → Text
//
// The engine uses grammar rules and templates, not neural generation.
// This makes output deterministic, explainable, and controllable.
//
// Memory: Output is built in a caller-provided buffer.
// Templates and grammar rules are pre-loaded and interned.

#ifndef COS_LANGUAGE_H
#define COS_LANGUAGE_H

#include "cos/core.h"
#include "cos/semantic.h"
#include "cos/string_intern.h"
#include "cos/allocator.h"
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

// ── Style ────────────────────────────────────────────────────────────────
typedef uint32_t cos_lang_style_t;

enum {
    COS_STYLE_FORMAL    = 0,   // Formal, complete sentences
    COS_STYLE_CASUAL    = 1,   // Casual, conversational
    COS_STYLE_TECHNICAL = 2,   // Precise, technical vocabulary
    COS_STYLE_CONCISE   = 3,   // Brief, minimal
    COS_STYLE_VERBOSE   = 4,   // Detailed, explanatory
};

// ── Sentence Plan ────────────────────────────────────────────────────────
typedef struct cos_sentence_plan_s {
    cos_string_id_t  template_id;     // Selected template
    cos_graph_node_id_t* slot_nodes;  // Semantic nodes mapped to slots
    size_t           slot_count;
    cos_lang_style_t style;
    uint32_t         flags;
} cos_sentence_plan_t;

// ── Opaque Language Engine ───────────────────────────────────────────────
typedef struct cos_language_s cos_language_t;

typedef struct cos_language_config_s {
    cos_allocator_t*    allocator;
    cos_allocator_t*    scratch;
    cos_string_table_t* string_table;
    cos_lang_style_t    default_style;
    const char*         templates_path;
} cos_language_config_t;

// ── Lifecycle ────────────────────────────────────────────────────────────
cos_language_t* cos_language_create(const cos_language_config_t* config);
void            cos_language_destroy(cos_language_t* lang);

// ── Generation ───────────────────────────────────────────────────────────
// Generate text from a semantic graph into a buffer.
// Returns the number of characters written (excluding null).
cos_status_t cos_language_generate(cos_language_t* lang,
                                    const cos_semantic_graph_t* graph,
                                    cos_lang_style_t style,
                                    char* out_buffer,
                                    size_t buffer_size,
                                    size_t* out_written);

// ── Sentence Planning (separate from generation) ─────────────────────────
cos_status_t cos_language_plan_sentences(cos_language_t* lang,
                                          const cos_semantic_graph_t* graph,
                                          cos_sentence_plan_t** out_plans,
                                          size_t* out_count);

// ── Style Control ────────────────────────────────────────────────────────
cos_status_t cos_language_set_style(cos_language_t* lang, cos_lang_style_t style);
cos_lang_style_t cos_language_get_style(const cos_language_t* lang);

#ifdef __cplusplus
}
#endif

#endif // COS_LANGUAGE_H
