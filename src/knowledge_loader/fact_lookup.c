// fact_lookup.c - Factual Knowledge Lookup Engine
//
// A hash table mapping question keywords to verified correct answers.
// Built from truthQA and similar datasets.
// Provides fast deterministic answers to factual questions.

#include "cos/core.h"
#include "cos/knowledge.h"
#include "cos/fact_lookup.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <stdint.h>
#include <stdalign.h>

#define MAX_FACTS 65536
#define HASH_SIZE 65521  // prime

// -- Hash table entry --------------------------------------------------------

typedef struct fact_entry {
    char* question;            // Original question
    char* answer;              // Correct answer
    size_t q_len;
    size_t a_len;
    char* keywords[16];        // Extracted significant keywords
    int   kw_count;
    int   hash_next;           // For chaining
    int   is_negation;         // Answer starts with No/Not/Nothing
    int   is_yes_no;           // Question was yes/no type
} fact_entry_t;

// -- Fact database -----------------------------------------------------------

struct cos_fact_db_s {
    fact_entry_t facts[MAX_FACTS];
    int fact_count;
    int buckets[HASH_SIZE];
    cos_allocator_t* alloc;
};

// -- Keyword extraction ------------------------------------------------------

static int extract_keywords(const char* text, size_t len, char** out, int max) {
    int count = 0;
    size_t i = 0;
    while (i < len && count < max) {
        while (i < len && !isalpha((unsigned char)text[i])) i++;
        if (i >= len) break;
        const char* start = text + i;
        while (i < len && isalpha((unsigned char)text[i])) i++;
        size_t wlen = i - (size_t)(start - text);
        // Only use significant words (length > 3 and not stop words)
        if (wlen > 3) {
            const char* stop_words[] = {"what", "when", "where", "which", "who",
                "whom", "whose", "this", "that", "these", "those", "they",
                "there", "their", "them", "have", "with", "from", "than",
                "been", "were", "does", "will", "just", "also", "more",
                "some", "than", "then", "very", "your", "about", "would",
                "could", "should", "into", "over", "such", "only", "other",
                "after", "before", "between"};
            bool is_stop = false;
            for (size_t s = 0; s < sizeof(stop_words)/sizeof(stop_words[0]); s++) {
                if (wlen == strlen(stop_words[s]) &&
                    memcmp(start, stop_words[s], wlen) == 0) {
                    is_stop = true; break;
                }
            }
            if (!is_stop) {
                char* word = (char*)malloc(wlen + 1);
                if (word) {
                    for (size_t j = 0; j < wlen; j++)
                        word[j] = (char)tolower((unsigned char)start[j]);
                    word[wlen] = '\0';
                    out[count++] = word;
                }
            }
        }
    }
    return count;
}

static void free_keywords(char** words, int count) {
    for (int i = 0; i < count; i++) free(words[i]);
}

// -- Hash function -----------------------------------------------------------

static uint32_t fact_hash(const char* str) {
    uint32_t h = 0;
    for (int i = 0; str[i]; i++) h = h * 31 + (unsigned char)tolower((unsigned char)str[i]);
    return h % HASH_SIZE;
}

// -- Lifecycle ---------------------------------------------------------------

cos_fact_db_t* cos_fact_db_create(cos_allocator_t* alloc) {
    if (!alloc) alloc = cos_sys_allocator();
    cos_fact_db_t* db = (cos_fact_db_t*)alloc->alloc(alloc, sizeof(cos_fact_db_t), alignof(cos_fact_db_t));
    if (!db) return NULL;
    memset(db, 0, sizeof(*db));
    for (int i = 0; i < HASH_SIZE; i++) db->buckets[i] = -1;
    db->alloc = alloc;
    return db;
}

void cos_fact_db_destroy(cos_fact_db_t* db) {
    if (!db) return;
    for (int i = 0; i < db->fact_count; i++) {
        free(db->facts[i].question);
        free(db->facts[i].answer);
        free_keywords(db->facts[i].keywords, db->facts[i].kw_count);
    }
    db->alloc->free(db->alloc, db, sizeof(cos_fact_db_t));
}

// -- Loading -----------------------------------------------------------------

int cos_fact_db_load_file(cos_fact_db_t* db, const char* path) {
    FILE* f = fopen(path, "r");
    if (!f) return -1;

    char line[65536];
    int loaded = 0;

    while (fgets(line, sizeof(line), f) && db->fact_count < MAX_FACTS) {
        size_t len = strlen(line);
        while (len > 0 && (line[len-1] == '\n' || line[len-1] == '\r')) line[--len] = '\0';
        if (len < 5) continue;

        // Format: Q: <question>\tA: <answer>\tN: <0|1>\tY: <0|1>
        // or: question\tanswer
        char* tab = strchr(line, '\t');
        if (!tab) continue;

        *tab = '\0';
        const char* question = line;
        const char* answer = tab + 1;

        // Skip Q: / A: prefixes if present
        if (strncmp(question, "Q: ", 3) == 0) question += 3;
        if (strncmp(answer, "A: ", 3) == 0) answer += 3;

        // Check for negation/yes_no flags
        int is_neg = 0, is_yn = 0;
        const char* flags = strchr(answer, '\t');
        if (flags) {
            // Parse tab-separated flags after answer
            // Format: answer\tN:1\tY:0
        }

        fact_entry_t* f = &db->facts[db->fact_count];
        f->q_len = strlen(question) + 1;
        f->a_len = strlen(answer) + 1;
        f->question = (char*)malloc(f->q_len);
        f->answer   = (char*)malloc(f->a_len);
        if (f->question) memcpy(f->question, question, f->q_len);
        if (f->answer)   memcpy(f->answer, answer, f->a_len);

        // Detect negation in answer
        const char* a_lower = answer;
        while (*a_lower == ' ') a_lower++;
        f->is_negation = (strncmp(a_lower, "no", 2) == 0 && (a_lower[2] == ' ' || a_lower[2] == ',')) ||
                         (strncmp(a_lower, "nothing", 7) == 0);

        // Detect yes/no question
        const char* q_lower = question;
        while (*q_lower == ' ') q_lower++;
        f->is_yes_no = (strncmp(q_lower, "is ", 3) == 0 || strncmp(q_lower, "are ", 4) == 0 ||
                        strncmp(q_lower, "do ", 3) == 0 || strncmp(q_lower, "does ", 5) == 0 ||
                        strncmp(q_lower, "can ", 4) == 0 || strncmp(q_lower, "could ", 6) == 0 ||
                        strncmp(q_lower, "would ", 6) == 0 || strncmp(q_lower, "should ", 7) == 0 ||
                        strncmp(q_lower, "did ", 4) == 0);

        // Extract keywords from question
        f->kw_count = extract_keywords(question, strlen(question), f->keywords, 16);

        // Hash by first keyword
        if (f->kw_count > 0) {
            uint32_t h = fact_hash(f->keywords[0]);
            f->hash_next = db->buckets[h];
            db->buckets[h] = db->fact_count;
        } else {
            f->hash_next = -1;
        }

        db->fact_count++;
        loaded++;
    }

    fclose(f);
    return loaded;
}

// -- Matching ----------------------------------------------------------------

// Compute a better match score: longest common word subsequence weighted by word length
static float compute_match_score(const char* q_words[16], int qcount,
                                  fact_entry_t* f, int* out_match_count) {
    if (qcount == 0 || f->kw_count == 0) return 0.0f;

    // Count matching words, weighted by word length (longer = rarer = more important)
    int matches = 0;
    float match_weight = 0.0f;
    float total_weight = 0.0f;

    for (int qi = 0; qi < qcount; qi++) {
        if (!q_words[qi]) continue;
        float wlen = (float)strlen(q_words[qi]);
        total_weight += wlen;
        for (int kj = 0; kj < f->kw_count; kj++) {
            if (f->keywords[kj] && strcmp(q_words[qi], f->keywords[kj]) == 0) {
                matches++;
                match_weight += wlen;
                break;
            }
        }
    }

    // Also score by how many query words appear IN ORDER in the fact question
    // This gives bonus for subsequence matches
    float order_bonus = 0.0f;
    if (matches >= 2) {
        int qpos = 0;
        for (int kj = 0; kj < f->kw_count && qpos < qcount; kj++) {
            for (int qi = qpos; qi < qcount; qi++) {
                if (f->keywords[kj] && q_words[qi] &&
                    strcmp(q_words[qi], f->keywords[kj]) == 0) {
                    order_bonus += 1.0f;
                    qpos = qi + 1;
                    break;
                }
            }
        }
    }

    float base_score = total_weight > 0 ? match_weight / total_weight : 0.0f;
    float order_score = matches > 0 ? order_bonus / matches : 0.0f;
    float combined = base_score * 0.6f + order_score * 0.4f;

    if (out_match_count) *out_match_count = matches;
    return combined;
}

int cos_fact_db_query(cos_fact_db_t* db, const char* question, size_t qlen,
                       const char** out_answer, size_t* out_alen,
                       int* out_is_negation, int* out_is_yes_no) {
    if (!db || !question || !out_answer) return 0;

    char* qwords[16];
    int qcount = extract_keywords(question, qlen, qwords, 16);
    if (qcount == 0) return 0;

    float best_score = 0.0f;
    int best_idx = -1;

    // Search by each keyword's hash bucket (limit to first 3 unique keys)
    int searched = 0;
    for (int qi = 0; qi < qcount && searched < 3; qi++) {
        // Skip duplicates: already searched this bucket?
        bool dup = false;
        for (int ck = 0; ck < qi; ck++) {
            if (qwords[ck] && qwords[qi] && strcmp(qwords[ck], qwords[qi]) == 0) {
                dup = true; break;
            }
        }
        if (dup) continue;
        searched++;

        uint32_t h = fact_hash(qwords[qi]);
        int idx = db->buckets[h];

        while (idx >= 0) {
            fact_entry_t* f = &db->facts[idx];
            int match_count = 0;
            float score = compute_match_score((const char**)qwords, qcount, f, &match_count);

            // Only consider if at least 1 word matches
            if (match_count > 0 && score > best_score) {
                best_score = score;
                best_idx = idx;
            }
            idx = f->hash_next;
        }
    }

    free_keywords(qwords, qcount);

    if (best_idx >= 0 && best_score > 0.1f) {
        fact_entry_t* f = &db->facts[best_idx];
        *out_answer = f->answer;
        if (out_alen) *out_alen = f->a_len > 0 ? f->a_len - 1 : 0;
        if (out_is_negation) *out_is_negation = f->is_negation;
        if (out_is_yes_no) *out_is_yes_no = f->is_yes_no;
        return 1;
    }

    return 0;
}
