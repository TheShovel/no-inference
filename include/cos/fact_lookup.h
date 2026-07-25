// fact_lookup.h - Factual Knowledge Lookup Engine
// Hash table mapping question keywords to verified correct answers.

#ifndef COS_FACT_LOOKUP_H
#define COS_FACT_LOOKUP_H

#include "cos/core.h"
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct cos_fact_db_s cos_fact_db_t;

// Lifecycle
cos_fact_db_t* cos_fact_db_create(cos_allocator_t* alloc);
void           cos_fact_db_destroy(cos_fact_db_t* db);

// Load from TSV file: Q: <question>\\tA: <answer>
// Returns number loaded, or -1 on error.
int cos_fact_db_load_file(cos_fact_db_t* db, const char* path);

// Query: find best matching fact for a question.
// Returns match score (0=no match, higher=better), or 0 if not found.
// Sets out_answer to the answer text, and optional flags.
int cos_fact_db_query(cos_fact_db_t* db, const char* question, size_t qlen,
                       const char** out_answer, size_t* out_alen,
                       int* out_is_negation, int* out_is_yes_no);

// Number of facts loaded
int cos_fact_db_count(cos_fact_db_t* db);

#ifdef __cplusplus
}
#endif

#endif // COS_FACT_LOOKUP_H
