// template_matcher.h - Template Matching Engine
//
// Loads Q/A template pairs extracted from conversational datasets
// and matches user queries using keyword overlap scoring.

#ifndef COS_TEMPLATE_MATCHER_H
#define COS_TEMPLATE_MATCHER_H

#include "cos/core.h"
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

// -- Single template entry ---------------------------------------------------
typedef struct {
    const char* question;         // The user question
    const char* answer;           // The assistant response
    size_t      q_len;            // Length of question string
    size_t      a_len;            // Length of answer string
    const char* words[32];        // Tokenized question words
    int         word_count;
} template_entry_t;

// -- Opaque database handle --------------------------------------------------
typedef struct cos_template_db_s cos_template_db_t;

// -- Lifecycle ---------------------------------------------------------------
cos_template_db_t* cos_template_db_create(cos_allocator_t* alloc);
void               cos_template_db_destroy(cos_template_db_t* db);

// -- Loading -----------------------------------------------------------------
// Load templates from a file in Q:/A: format.
// Returns number loaded, or -1 on error.
int cos_template_db_load(cos_template_db_t* db, const char* path);

// -- Matching ----------------------------------------------------------------
// Find the best matching template for a query.
// Returns match score (0.0-1.0) and sets out_entry to the best match.
float cos_template_db_match(cos_template_db_t* db, const char* query, size_t qlen,
                              const template_entry_t** out_entry);

// -- Introspection -----------------------------------------------------------
int cos_template_db_count(cos_template_db_t* db);

#ifdef __cplusplus
}
#endif

#endif // COS_TEMPLATE_MATCHER_H
