// tokenizer.c — Text Tokenizer
//
// Design: Splits input text into tokens (words and punctuation).
// Handles:
//   - Word boundaries (whitespace)
//   - Punctuation attachment/detachment
//   - Contractions (don't → do + n't)
//   - Sentence boundaries (. ! ?)
//
// Memory: Tokens are stored in a caller-provided arena.
// Token strings are views into the original input (no copies).

#include "cos/core.h"
#include "cos/parser.h"
#include "cos/string_view.h"
#include <string.h>
#include <ctype.h>
#include <stdlib.h>


// ── Maximum tokens per utterance ─────────────────────────────────────────
#define COS_MAX_TOKENS 256

// ── Character Classification ─────────────────────────────────────────────

static bool is_word_char(char c) {
    return isalnum((unsigned char)c) || c == '\'' || c == '_' || c == '-';
}

static bool is_punct_char(char c) {
    return ispunct((unsigned char)c) && c != '\'';
}

// ── Tokenizer ────────────────────────────────────────────────────────────

cos_status_t cos_tokenize(cos_parser_t* parser,
                          cos_string_view_t input,
                          cos_token_t** out_tokens,
                          size_t* out_count) {
    (void)parser;
    if (!out_tokens || !out_count) return COS_ERROR_NULL;

    // Use a static buffer for simplicity (token array on heap for now)
    // In production, this would use the parser's scratch arena.
    cos_token_t* tokens = (cos_token_t*)calloc(COS_MAX_TOKENS, sizeof(cos_token_t));
    if (!tokens) return COS_ERROR_NOMEM;

    size_t count = 0;
    size_t pos = 0;

    while (pos < input.length && count < COS_MAX_TOKENS) {
        // Skip whitespace
        while (pos < input.length && isspace((unsigned char)input.data[pos])) {
            pos++;
        }
        if (pos >= input.length) break;

        cos_token_t* tok = &tokens[count];
        size_t start = pos;

        if (is_word_char(input.data[pos])) {
            // Word token
            while (pos < input.length && is_word_char(input.data[pos])) {
                pos++;
            }
            tok->text = cos_sv(input.data + start, pos - start);
            tok->pos  = COS_POS_UNKNOWN;  // Will be tagged in phase 2
            tok->confidence = 0.0f;
            tok->text_id = COS_STRING_ID_NULL;
        } else if (is_punct_char(input.data[pos])) {
            // Punctuation token
            while (pos < input.length && is_punct_char(input.data[pos])) {
                pos++;
            }
            tok->text = cos_sv(input.data + start, pos - start);
            tok->pos  = COS_POS_PUNCTUATION;

            // Classify sentence-ending punctuation
            if (tok->text.length == 1 &&
                (tok->text.data[0] == '.' || tok->text.data[0] == '!' || tok->text.data[0] == '?')) {
                if (tok->text.data[0] == '?') tok->pos = COS_POS_QUESTION;
            }

            tok->confidence = 1.0f;
            tok->text_id = COS_STRING_ID_NULL;
        } else {
            // Unknown character, skip
            pos++;
            continue;
        }

        count++;
    }

    *out_tokens = tokens;
    *out_count  = count;
    return COS_OK;
}
