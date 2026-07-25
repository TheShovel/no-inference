// generator.h — Text Generator
//
// Design: The final stage of the language pipeline.
// Takes a sentence plan and grammar-annotated structure and produces
// the final output text.
//
// The generator handles:
//   - Word ordering
//   - Inflection (pluralization, conjugation)
//   - Contractions
//   - Punctuation
//   - Capitalization
//
// All output is written to a caller-provided buffer.
// No dynamic allocations during generation.

#ifndef COS_GENERATOR_H
#define COS_GENERATOR_H

#include "cos/core.h"
#include "cos/semantic.h"
#include "cos/string_intern.h"
#include "cos/knowledge.h"
#include "cos/allocator.h"
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

// ── Inflection Rules ─────────────────────────────────────────────────────
typedef uint32_t cos_inflection_t;

enum {
    COS_INFLECT_NONE       = 0,
    COS_INFLECT_PLURAL     = 1,
    COS_INFLECT_PAST_TENSE = 2,
    COS_INFLECT_PRESENT    = 3,
    COS_INFLECT_FUTURE     = 4,
    COS_INFLECT_GERUND     = 5,
    COS_INFLECT_COMPARATIVE= 6,
    COS_INFLECT_SUPERLATIVE= 7,
    COS_INFLECT_POSSESSIVE = 8,
};

// ── Opaque Generator ─────────────────────────────────────────────────────
typedef struct cos_generator_s cos_generator_t;

typedef struct cos_generator_config_s {
    cos_allocator_t*    allocator;
    cos_allocator_t*    scratch;
    cos_string_table_t* string_table;   // Needed to resolve interned string IDs
} cos_generator_config_t;

// ── Lifecycle ────────────────────────────────────────────────────────────
cos_generator_t* cos_generator_create(const cos_generator_config_t* config);
void             cos_generator_destroy(cos_generator_t* gen);

// ── Generation ───────────────────────────────────────────────────────────
// Generate text from a semantic graph directly.
cos_status_t cos_generator_generate(cos_generator_t* gen,
                                     const cos_semantic_graph_t* meaning,
                                     char* out_buffer,
                                     size_t buffer_size,
                                     size_t* out_written);

// -- Context: provide remembered facts for response generation -------------
// The generator can hold a context of facts retrieved from memory.
// These facts influence how responses are generated (e.g., "You said you like X").
cos_status_t cos_generator_set_context(cos_generator_t* gen, const cos_fact_t* facts, size_t fact_count);

// ── Lower-level API ──────────────────────────────────────────────────────
cos_status_t cos_generator_apply_inflection(cos_generator_t* gen,
                                             cos_string_id_t word,
                                             cos_inflection_t inflection,
                                             char* out_buffer,
                                             size_t buffer_size,
                                             size_t* out_written);

#ifdef __cplusplus
}
#endif

#endif // COS_GENERATOR_H
