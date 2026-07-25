// template_matcher.c - Template Matching Engine
//
// Loads Q/A template pairs and matches user queries via word overlap.
// Used by the conversation engine to answer questions from real data.

#include "cos/core.h"
#include "cos/knowledge.h"
#include "cos/template_matcher.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <stdint.h>
#include <stdalign.h>

#define MAX_TEMPLATES 500000
#define MAX_WORDS 32

struct cos_template_db_s {
    template_entry_t templates[MAX_TEMPLATES];
    int count;
    cos_allocator_t* alloc;
};

// -- Word tokenization -------------------------------------------------------

static int tokenize_words(const char* text, size_t len, char** words, int max_words) {
    int count = 0;
    size_t i = 0;
    while (i < len && count < max_words) {
        while (i < len && !isalpha((unsigned char)text[i])) i++;
        if (i >= len) break;
        const char* start = text + i;
        while (i < len && isalpha((unsigned char)text[i])) i++;
        size_t wlen = i - (size_t)(start - text);
        if (wlen > 2) {
            char* word = (char*)cos_sys_allocator()->alloc(cos_sys_allocator(), wlen + 1, 1);
            if (word) {
                for (size_t j = 0; j < wlen; j++)
                    word[j] = (char)tolower((unsigned char)start[j]);
                word[wlen] = '\0';
                words[count++] = word;
            }
        }
    }
    return count;
}

static void free_words(char** words, int count) {
    for (int i = 0; i < count; i++)
        if (words[i]) cos_sys_allocator()->free(cos_sys_allocator(), words[i], strlen(words[i]) + 1);
}

// -- Lifecycle ---------------------------------------------------------------

cos_template_db_t* cos_template_db_create(cos_allocator_t* alloc) {
    if (!alloc) alloc = cos_sys_allocator();
    cos_template_db_t* db = (cos_template_db_t*)
        alloc->alloc(alloc, sizeof(cos_template_db_t), alignof(cos_template_db_t));
    if (db) { memset(db, 0, sizeof(*db)); db->alloc = alloc; }
    return db;
}

void cos_template_db_destroy(cos_template_db_t* db) {
    if (!db) return;
    for (int i = 0; i < db->count; i++) {
        if (db->templates[i].question) db->alloc->free(db->alloc,
            (void*)db->templates[i].question, db->templates[i].q_len);
        if (db->templates[i].answer) db->alloc->free(db->alloc,
            (void*)db->templates[i].answer, db->templates[i].a_len);
        for (int j = 0; j < db->templates[i].word_count; j++)
            if (db->templates[i].words[j])
                cos_sys_allocator()->free(cos_sys_allocator(),
                    db->templates[i].words[j], strlen(db->templates[i].words[j]) + 1);
    }
    db->alloc->free(db->alloc, db, sizeof(cos_template_db_t));
}

// -- Load templates from file ------------------------------------------------

int cos_template_db_load(cos_template_db_t* db, const char* path) {
    FILE* f = fopen(path, "r");
    if (!f) return -1;

    char line[65536];
    char current_q[65536] = {0};
    int loaded = 0;

    while (fgets(line, sizeof(line), f) && db->count < MAX_TEMPLATES) {
        size_t len = strlen(line);
        while (len > 0 && (line[len-1] == '\n' || line[len-1] == '\r')) line[--len] = '\0';

        if (len > 3 && line[0] == 'Q' && line[1] == ':') {
            strncpy(current_q, line + 2, sizeof(current_q)-1);
            char* q = current_q; while (*q == ' ') q++;
            if (q != current_q) memmove(current_q, q, strlen(q)+1);
        } else if (len > 3 && line[0] == 'A' && line[1] == ':' && current_q[0]) {
            char* answer = line + 2; while (*answer == ' ') answer++;

            template_entry_t* t = &db->templates[db->count];
            t->q_len = strlen(current_q) + 1;
            t->a_len = strlen(answer) + 1;
            t->question = (const char*)db->alloc->alloc(db->alloc, t->q_len, 1);
            t->answer   = (const char*)db->alloc->alloc(db->alloc, t->a_len, 1);
            if (t->question) memcpy((char*)t->question, current_q, t->q_len);
            if (t->answer)   memcpy((char*)t->answer, answer, t->a_len);
            t->word_count = tokenize_words(current_q, strlen(current_q),
                                           (char**)t->words, MAX_WORDS);
            db->count++;
            loaded++;
            current_q[0] = '\0';
        }
    }
    fclose(f);
    return loaded;
}

// -- Character trigram extraction -------------------------------------------
// Trigrams capture more semantic signal than individual words.
// "recursion" -> "rec", "ecu", "cur", "urs", "rsi", "sio", "ion"

#define MAX_TRIGRAMS 256

typedef struct {
    uint32_t hash;
} trigram_t;

static int extract_trigrams(const char* text, size_t len, trigram_t* trigrams, int max) {
    int count = 0;
    // Only use letters and digits, lowercase
    char clean[256];
    size_t clen = 0;
    for (size_t i = 0; i < len && clen < 250; i++) {
        if (isalnum((unsigned char)text[i]))
            clean[clen++] = (char)tolower((unsigned char)text[i]);
        else
            clean[clen++] = ' ';
    }

    for (size_t i = 0; i + 2 < clen && count < max; i++) {
        if (clean[i] == ' ' || clean[i+1] == ' ' || clean[i+2] == ' ') continue;
        // Simple hash: pack 3 bytes into a uint32
        trigram_t tg;
        tg.hash = ((uint32_t)(unsigned char)clean[i] << 16) |
                  ((uint32_t)(unsigned char)clean[i+1] << 8) |
                  ((uint32_t)(unsigned char)clean[i+2]);
        // Deduplicate within this extraction
        bool dup = false;
        for (int j = 0; j < count; j++) {
            if (trigrams[j].hash == tg.hash) { dup = true; break; }
        }
        if (!dup) trigrams[count++] = tg;
    }
    return count;
}

// -- Simple word rarity score (no pre-computation needed) --------------------
// Longer words are rarer and more distinctive.
// "recursion" (9 chars) gets more weight than "what" (4 chars).

static float word_rarity(const char* w) {
    size_t len = strlen(w);
    if (len <= 2) return 0.3f;
    if (len <= 3) return 0.5f;
    if (len <= 4) return 0.7f;
    if (len <= 6) return 0.9f;
    return 1.0f;  // longer words are more distinctive
}

// -- Matching -----------------------------------------------------------------
// Uses a hybrid score: trigram overlap (60%) + word Jaccard (30%) + length bonus (10%)

float cos_template_db_match(cos_template_db_t* db, const char* query, size_t qlen,
                              const template_entry_t** out_entry) {
    char* qwords[MAX_WORDS];
    int qcount = tokenize_words(query, qlen, qwords, MAX_WORDS);
    if (qcount == 0) return 0.0f;

    // Extract trigrams from query
    trigram_t qtrigs[MAX_TRIGRAMS];
    int qtcount = extract_trigrams(query, qlen, qtrigs, MAX_TRIGRAMS);

    // Early exit: for large template sets, skip if trigrams are empty
    if (qtcount == 0) { free_words(qwords, qcount); return 0.0f; }

    float best_score = 0.0f;
    const template_entry_t* best = NULL;
    int search_count = db->count < 5000 ? db->count : 5000; // search top 5K for speed
    if (search_count > db->count) search_count = db->count;

    for (int i = 0; i < search_count; i++) {
        template_entry_t* t = &db->templates[i];
        if (t->word_count == 0) continue;

        // -- Quick pre-filter: require at least some trigram overlap --
        // Extract trigrams from template question and count matches
        trigram_t ttrigs[MAX_TRIGRAMS];
        int ttcount = extract_trigrams(t->question, t->q_len, ttrigs, MAX_TRIGRAMS);

        int trig_matches = 0;
        for (int qi = 0; qi < qtcount && qi < 20; qi++) {
            for (int ti = 0; ti < ttcount && ti < 20; ti++) {
                if (qtrigs[qi].hash == ttrigs[ti].hash) {
                    trig_matches++;
                    break;
                }
            }
        }

        // Skip templates with very little trigram overlap
        int min_trig = qtcount < 5 ? 1 : 2;
        if (trig_matches < min_trig) continue;

        float trig_union = (float)(qtcount + ttcount - trig_matches);
        float trig_score = trig_union > 0 ? (float)trig_matches / trig_union : 0.0f;

        // -- Word overlap score (with rarity weighting) --
        float word_score = 0.0f;
        float total_weight = 0.0f;
        for (int qi = 0; qi < qcount; qi++) {
            if (!qwords[qi]) continue;
            float weight = word_rarity(qwords[qi]);
            total_weight += weight;
            for (int tj = 0; tj < t->word_count; tj++) {
                if (t->words[tj] && strcmp(qwords[qi], t->words[tj]) == 0) {
                    word_score += weight;
                    break;
                }
            }
        }
        word_score = total_weight > 0 ? word_score / total_weight : 0.0f;

        // -- Combined score (trigram dominates) --
        float score = trig_score * 0.70f + word_score * 0.30f;

        if (score > best_score) { best_score = score; best = t; }
    }

    free_words(qwords, qcount);
    if (out_entry) *out_entry = best;
    return best_score;
}
