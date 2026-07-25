// grammar.h — Grammar Engine
//
// Design: Rule-based grammar engine for English (extensible to other languages).
// Grammar rules are loaded from files at startup and compiled into a compact
// internal representation.
//
// Rules are context-free grammar productions with semantic actions.
// The grammar engine applies rules to sentence plans to produce word sequences.
//
// Memory: Rules stored in compact binary format. Active parse state
// lives in a caller-provided arena.

#ifndef COS_GRAMMAR_H
#define COS_GRAMMAR_H

#include "cos/core.h"
#include "cos/allocator.h"
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

// ── Part of Speech Tags (repeated from parser.h for independence) ────────
// This file can be included standalone without parser.h

// ── Grammar Rule ─────────────────────────────────────────────────────────
typedef struct cos_grammar_rule_s {
    uint32_t        id;
    cos_string_id_t category;       // e.g., "NP", "VP", "S"
    cos_string_id_t production;     // The expansion
    float           weight;         // Rule weight for ambiguity resolution
} cos_grammar_rule_t;

// ── Opaque Grammar Engine ────────────────────────────────────────────────
typedef struct cos_grammar_s cos_grammar_t;

typedef struct cos_grammar_config_s {
    cos_allocator_t* allocator;
    const char*      rules_path;    // Path to grammar rules file
} cos_grammar_config_t;

// ── Lifecycle ────────────────────────────────────────────────────────────
cos_grammar_t* cos_grammar_create(const cos_grammar_config_t* config);
void           cos_grammar_destroy(cos_grammar_t* grammar);

// ── Rule Loading ─────────────────────────────────────────────────────────
cos_status_t cos_grammar_load_file(cos_grammar_t* grammar, const char* path);
cos_status_t cos_grammar_add_rule(cos_grammar_t* grammar, const cos_grammar_rule_t* rule);
size_t       cos_grammar_rule_count(const cos_grammar_t* grammar);

// ── Introspection ────────────────────────────────────────────────────────
size_t cos_grammar_memory_used(const cos_grammar_t* grammar);

#ifdef __cplusplus
}
#endif

#endif // COS_GRAMMAR_H
