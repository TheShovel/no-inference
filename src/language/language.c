// language.c — Language Generation Engine Implementation
//
// Design: Converts meaning graphs into natural language text.
// Pipeline:
//   1. Sentence planning: decides what to say and in what order
//   2. Template selection: picks grammar templates for each sentence
//   3. Slot filling: maps semantic nodes to template slots
//   4. Generation: produces final text via the generator
//
// Memory: Templates are loaded at startup and interned.
// Per-generation work uses the scratch arena.

#include "cos/core.h"
#include "cos/language.h"
#include "cos/semantic.h"
#include "cos/allocator.h"
#include "cos/string_intern.h"
#include <string.h>
#include <stdalign.h>

#ifdef __cplusplus
extern "C" {
#endif

// ── Language Engine ──────────────────────────────────────────────────────
struct cos_language_s {
    cos_allocator_t*    alloc;
    cos_allocator_t*    scratch;
    cos_lang_style_t    default_style;
    char*               templates_path;
    size_t              templates_path_len;
};

// ── Built-in Sentence Templates ──────────────────────────────────────────
// Simple templates for common sentence structures.
// These would be loaded from files in production.

typedef struct cos_template_entry_s {
    const char* pattern;       // Template pattern with {slots}
    cos_semantic_type_t trigger_type;  // Which semantic type triggers this template
    cos_lang_style_t   style;
    int                priority;
} cos_template_entry_t;

static const cos_template_entry_t g_templates[] = {
    // Statement templates
    {"{subject} {verb} {object}.",        COS_SEMANTIC_STATEMENT, COS_STYLE_FORMAL,    0},
    {"{subject} {verb} {object}.",        COS_SEMANTIC_STATEMENT, COS_STYLE_CASUAL,    0},
    {"{subject} {verb} {object}.",        COS_SEMANTIC_STATEMENT, COS_STYLE_TECHNICAL, 0},
    {"{subject} {verb} {object}",         COS_SEMANTIC_STATEMENT, COS_STYLE_CONCISE,   0},
    {"{subject} {verb} {object}...",      COS_SEMANTIC_STATEMENT, COS_STYLE_VERBOSE,   0},

    // Greeting templates
    {"Hello! How can I help you?",        COS_SEMANTIC_ROOT,      COS_STYLE_FORMAL,    1},
    {"Hey! What's up?",                   COS_SEMANTIC_ROOT,      COS_STYLE_CASUAL,    1},
    {"Greetings. How may I assist?",      COS_SEMANTIC_ROOT,      COS_STYLE_TECHNICAL, 1},
    {"Hi.",                               COS_SEMANTIC_ROOT,      COS_STYLE_CONCISE,   1},
    {"Hello there! I hope you're having a wonderful day! How can I be of assistance?",
     COS_SEMANTIC_ROOT, COS_STYLE_VERBOSE, 1},

    // Acknowledgment templates
    {"I understand.",                     COS_SEMANTIC_STATEMENT, COS_STYLE_FORMAL,    2},
    {"Got it.",                           COS_SEMANTIC_STATEMENT, COS_STYLE_CASUAL,    2},
    {"Acknowledged.",                     COS_SEMANTIC_STATEMENT, COS_STYLE_TECHNICAL, 2},
    {"OK.",                               COS_SEMANTIC_STATEMENT, COS_STYLE_CONCISE,   2},
    {"I have received and understood your message completely.",
     COS_SEMANTIC_STATEMENT, COS_STYLE_VERBOSE, 2},
};

// ── Lifecycle ────────────────────────────────────────────────────────────

cos_language_t* cos_language_create(const cos_language_config_t* config) {
    if (!config) return NULL;

    cos_language_t* lang = (cos_language_t*)
        config->allocator->alloc(config->allocator, sizeof(cos_language_t), alignof(cos_language_t));
    if (!lang) return NULL;

    lang->alloc     = config->allocator;
    lang->scratch   = config->scratch ? config->scratch : config->allocator;
    lang->default_style = config->default_style;

    if (config->templates_path) {
        lang->templates_path_len = strlen(config->templates_path);
        lang->templates_path = (char*)lang->alloc->alloc(lang->alloc,
            lang->templates_path_len + 1, alignof(char));
        if (lang->templates_path) {
            memcpy(lang->templates_path, config->templates_path, lang->templates_path_len + 1);
        }
    } else {
        lang->templates_path = NULL;
        lang->templates_path_len = 0;
    }

    return lang;
}

void cos_language_destroy(cos_language_t* lang) {
    if (!lang) return;
    if (lang->templates_path) lang->alloc->free(lang->alloc, lang->templates_path, lang->templates_path_len + 1);
    lang->alloc->free(lang->alloc, lang, sizeof(cos_language_t));
}

// ── Sentence Planning ────────────────────────────────────────────────────

cos_status_t cos_language_plan_sentences(cos_language_t* lang,
                                          const cos_semantic_graph_t* graph,
                                          cos_sentence_plan_t** out_plans,
                                          size_t* out_count) {
    (void)lang;
    (void)graph;
    (void)out_plans;
    (void)out_count;
    return COS_ERROR_NOT_IMPL;
}

// ── Generation ───────────────────────────────────────────────────────────

cos_status_t cos_language_generate(cos_language_t* lang,
                                    const cos_semantic_graph_t* graph,
                                    cos_lang_style_t style,
                                    char* out_buffer,
                                    size_t buffer_size,
                                    size_t* out_written) {
    if (!lang || !graph || !out_buffer || !out_written) return COS_ERROR_NULL;

    // Simple generation: extract semantic nodes and build a sentence
    // This is a minimal implementation. A full version would:
    // 1. Plan sentences from the graph
    // 2. Select templates
    // 3. Fill slots
    // 4. Apply grammar rules

    cos_graph_node_id_t nodes[64];
    size_t found;

    // Try to find a statement node
    found = cos_semantic_find_type(graph, COS_SEMANTIC_STATEMENT, nodes, 64);

    cos_graph_node_id_t entities[64];
    size_t entity_count = cos_semantic_find_type(graph, COS_SEMANTIC_ENTITY, entities, 64);

    cos_graph_node_id_t actions[64];
    size_t action_count = cos_semantic_find_type(graph, COS_SEMANTIC_ACTION, actions, 64);

    // Build a simple sentence from entities and actions
    size_t written = 0;

    // Write entity names
    for (size_t i = 0; i < entity_count && written < buffer_size - 1; i++) {
        cos_semantic_node_t node;
        if (cos_semantic_get_node(graph, entities[i], &node) == COS_OK) {
            // Look up the interned string text
            // For now, we don't have access to the string table here
            (void)node;
            // This is a stub — full implementation would access the string table
        }
    }

    // Default response if nothing was generated
    if (written == 0) {
        const char* default_response = "I processed your input.";
        size_t len = strlen(default_response);
        size_t to_copy = len < buffer_size - 1 ? len : buffer_size - 1;
        memcpy(out_buffer, default_response, to_copy);
        written = to_copy;
    }

    out_buffer[written] = '\0';
    *out_written = written;
    return COS_OK;
}

// ── Style Control ────────────────────────────────────────────────────────

cos_status_t cos_language_set_style(cos_language_t* lang, cos_lang_style_t style) {
    if (!lang) return COS_ERROR_NULL;
    lang->default_style = style;
    return COS_OK;
}

cos_lang_style_t cos_language_get_style(const cos_language_t* lang) {
    return lang ? lang->default_style : COS_STYLE_FORMAL;
}

#ifdef __cplusplus
}
#endif
