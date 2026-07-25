// grammar.c — Grammar Engine Implementation
//
// Design: Rule-based context-free grammar engine.
// Rules are loaded from files or added programmatically.
// The engine compiles rules into a compact internal format
// for fast matching and application.
//
// Memory: Rules stored in contiguous arrays. Rule data is interned.

#include "cos/core.h"
#include "cos/grammar.h"
#include "cos/allocator.h"
#include "cos/string_intern.h"
#include <string.h>
#include <stdalign.h>
#include <stdio.h>

#ifdef __cplusplus
extern "C" {
#endif

// ── Rule Storage ─────────────────────────────────────────────────────────
struct cos_grammar_s {
    cos_allocator_t*    alloc;
    cos_grammar_rule_t* rules;
    size_t              rule_count;
    size_t              rule_capacity;
    size_t              total_memory;
};

// ── Lifecycle ────────────────────────────────────────────────────────────

cos_grammar_t* cos_grammar_create(const cos_grammar_config_t* config) {
    if (!config) return NULL;

    cos_grammar_t* grammar = (cos_grammar_t*)
        config->allocator->alloc(config->allocator, sizeof(cos_grammar_t), alignof(cos_grammar_t));
    if (!grammar) return NULL;

    grammar->alloc     = config->allocator;
    grammar->rules     = NULL;
    grammar->rule_count    = 0;
    grammar->rule_capacity = 0;
    grammar->total_memory  = sizeof(cos_grammar_t);

    return grammar;
}

void cos_grammar_destroy(cos_grammar_t* grammar) {
    if (!grammar) return;
    if (grammar->rules) {
        grammar->alloc->free(grammar->alloc, grammar->rules,
            grammar->rule_capacity * sizeof(cos_grammar_rule_t));
    }
    grammar->alloc->free(grammar->alloc, grammar, sizeof(cos_grammar_t));
}

// ── Rule Loading ─────────────────────────────────────────────────────────

cos_status_t cos_grammar_load_file(cos_grammar_t* grammar, const char* path) {
    (void)grammar;
    (void)path;
    // Stub: loads grammar rules from a text file
    return COS_ERROR_NOT_IMPL;
}

cos_status_t cos_grammar_add_rule(cos_grammar_t* grammar, const cos_grammar_rule_t* rule) {
    if (!grammar || !rule) return COS_ERROR_NULL;

    if (grammar->rule_count >= grammar->rule_capacity) {
        size_t new_cap = grammar->rule_capacity > 0 ? grammar->rule_capacity * 2 : 256;
        cos_grammar_rule_t* new_rules = (cos_grammar_rule_t*)
            grammar->alloc->realloc(grammar->alloc, grammar->rules,
                grammar->rule_capacity * sizeof(cos_grammar_rule_t),
                new_cap * sizeof(cos_grammar_rule_t), alignof(cos_grammar_rule_t));
        if (!new_rules) return COS_ERROR_NOMEM;
        grammar->rules = new_rules;
        grammar->rule_capacity = new_cap;
    }

    grammar->rules[grammar->rule_count++] = *rule;
    grammar->total_memory += sizeof(cos_grammar_rule_t);
    return COS_OK;
}

size_t cos_grammar_rule_count(const cos_grammar_t* grammar) {
    return grammar ? grammar->rule_count : 0;
}

// ── Introspection ────────────────────────────────────────────────────────

size_t cos_grammar_memory_used(const cos_grammar_t* grammar) {
    if (!grammar) return 0;
    return grammar->total_memory + (grammar->rule_capacity * sizeof(cos_grammar_rule_t));
}

#ifdef __cplusplus
}
#endif
