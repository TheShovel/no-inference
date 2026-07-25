// parser.h — Semantic Parser Engine
//
// Design: Converts raw text into a semantic graph.
// The parser is a multi-stage pipeline:
//   1. Tokenizer: splits text into tokens (words, punctuation)
//   2. Tagging: assigns parts of speech and basic roles
//   3. Phrase building: groups tokens into phrases
//   4. Semantic mapping: builds the semantic graph
//
// Each stage is independent and can be replaced.
//
// Memory: Uses arena allocator for per-parse scratch memory.
// The output semantic graph uses the system string table.

#ifndef COS_PARSER_H
#define COS_PARSER_H

#include "cos/core.h"
#include "cos/semantic.h"
#include "cos/string_intern.h"
#include "cos/allocator.h"
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

// ── Token ────────────────────────────────────────────────────────────────
typedef uint32_t cos_pos_tag_t;

enum {
    COS_POS_UNKNOWN    = 0,
    COS_POS_NOUN       = 1,
    COS_POS_VERB       = 2,
    COS_POS_ADJECTIVE  = 3,
    COS_POS_ADVERB     = 4,
    COS_POS_PRONOUN    = 5,
    COS_POS_PREPOSITION= 6,
    COS_POS_CONJUNCTION= 7,
    COS_POS_DETERMINER = 8,
    COS_POS_NUMERAL    = 9,
    COS_POS_PUNCTUATION= 10,
    COS_POS_QUESTION   = 11,
};

typedef struct cos_token_s {
    cos_string_view_t  text;        // The token text (borrowed)
    cos_string_id_t    text_id;     // Interned token
    cos_pos_tag_t      pos;         // Part of speech
    float              confidence;  // Tag confidence
} cos_token_t;

// ── Opaque Parser ────────────────────────────────────────────────────────
typedef struct cos_parser_s cos_parser_t;

// ── Parser Config ────────────────────────────────────────────────────────
typedef struct cos_parser_config_s {
    cos_string_table_t* string_table;   // Shared string table (required)
    cos_allocator_t*    allocator;      // Primary allocator
    cos_allocator_t*    scratch;        // Scratch arena for per-parse use
} cos_parser_config_t;

// ── Lifecycle ────────────────────────────────────────────────────────────
cos_parser_t* cos_parser_create(const cos_parser_config_t* config);
void          cos_parser_destroy(cos_parser_t* parser);

// ── Parsing ──────────────────────────────────────────────────────────────
// Parse a single utterance into a semantic graph.
// The caller owns the returned graph and must destroy it.
cos_status_t cos_parser_parse(cos_parser_t* parser, cos_string_view_t input, cos_semantic_graph_t** out_graph);

// ── Incremental Parsing ──────────────────────────────────────────────────
// Feed partial input. semantic_graph accumulates across calls.
// Call cos_parser_finalize() when input is complete.
cos_status_t cos_parser_feed(cos_parser_t* parser, cos_string_view_t partial, cos_semantic_graph_t* graph);
cos_status_t cos_parser_finalize(cos_parser_t* parser, cos_semantic_graph_t* graph);

// ── Tokenization (exposed for lower-level use) ───────────────────────────
// Tokenize input into an array of tokens.
// Caller must free the returned array using the parser's allocator.
cos_status_t cos_tokenize(cos_parser_t* parser, cos_string_view_t input, cos_token_t** out_tokens, size_t* out_count);

#ifdef __cplusplus
}
#endif

#endif // COS_PARSER_H
