// generator.c - Text Generator Implementation
//
// Design: The final output stage. Takes a semantic graph and produces
// natural language text by reading interned strings from semantic nodes,
// selecting response templates, and filling slots.
//
// Language quality features:
//   - Article insertion (a/an) before singular count nouns
//   - Pronoun swapping ("I" -> "you" in responses)
//   - Varied response templates
//   - Pluralisation and tense (basic)
//
// Memory: All output is written to a caller-provided buffer.
// No dynamic allocations during generation.

#include "cos/core.h"
#include "cos/generator.h"
#include "cos/semantic.h"
#include "cos/string_intern.h"
#include "cos/allocator.h"
#include <string.h>
#include <ctype.h>
#include <stdalign.h>

#ifdef __cplusplus
extern "C" {
#endif

// -- Generator context ------------------------------------------------------

struct cos_generator_s {
    cos_allocator_t*    alloc;
    cos_allocator_t*    scratch;
    cos_string_table_t* strings;

    // Context facts from memory query (set by conversation before generation)
    cos_fact_t*         context_facts;
    size_t              context_count;
    size_t              context_capacity;
};

// -- Lifecycle --------------------------------------------------------------

cos_generator_t* cos_generator_create(const cos_generator_config_t* config) {
    if (!config) return NULL;
    cos_generator_t* gen = (cos_generator_t*)
        config->allocator->alloc(config->allocator, sizeof(cos_generator_t), alignof(cos_generator_t));
    if (!gen) return NULL;
    gen->alloc   = config->allocator;
    gen->scratch = config->scratch ? config->scratch : config->allocator;
    gen->strings = config->string_table;
    gen->context_facts    = NULL;
    gen->context_count    = 0;
    gen->context_capacity = 0;
    return gen;
}

void cos_generator_destroy(cos_generator_t* gen) {
    if (!gen) return;
    if (gen->context_facts) gen->alloc->free(gen->alloc, gen->context_facts,
        gen->context_capacity * sizeof(cos_fact_t));
    gen->alloc->free(gen->alloc, gen, sizeof(cos_generator_t));
}

// -- Set context facts ------------------------------------------------------

cos_status_t cos_generator_set_context(cos_generator_t* gen,
                                        const cos_fact_t* facts,
                                        size_t fact_count) {
    if (!gen) return COS_ERROR_NULL;
    if (gen->context_facts) {
        gen->alloc->free(gen->alloc, gen->context_facts,
            gen->context_capacity * sizeof(cos_fact_t));
        gen->context_facts = NULL;
        gen->context_count = 0;
        gen->context_capacity = 0;
    }
    if (facts && fact_count > 0) {
        gen->context_facts = (cos_fact_t*)gen->alloc->alloc(gen->alloc,
            fact_count * sizeof(cos_fact_t), alignof(cos_fact_t));
        if (!gen->context_facts) return COS_ERROR_NOMEM;
        memcpy(gen->context_facts, facts, fact_count * sizeof(cos_fact_t));
        gen->context_count    = fact_count;
        gen->context_capacity = fact_count;
    }
    return COS_OK;
}

// -- Buffer helpers ---------------------------------------------------------

static size_t buf_append(char* buf, size_t buf_size, size_t written,
                          const char* s, size_t len) {
    size_t avail = buf_size > written ? buf_size - written : 0;
    size_t copy  = len < avail ? len : avail;
    if (copy > 0 && buf) memcpy(buf + written, s, copy);
    return written + copy;
}

static size_t buf_append_cstr(char* buf, size_t buf_size, size_t written, const char* s) {
    return buf_append(buf, buf_size, written, s, strlen(s));
}

static size_t buf_append_char(char* buf, size_t buf_size, size_t written, char c) {
    if (written + 1 < buf_size) buf[written] = c;
    return written + 1;
}

static size_t buf_append_node_text(char* buf, size_t buf_size, size_t written,
                                    cos_string_table_t* table, cos_string_id_t id) {
    if (id == COS_STRING_ID_NULL || !table) return written;
    cos_string_view_t sv = cos_string_lookup(table, id);
    if (sv.data && sv.length > 0) {
        return buf_append(buf, buf_size, written, sv.data, sv.length);
    }
    return written;
}

static void capitalise(char* buf, size_t written) {
    if (written > 0 && buf[0]) buf[0] = (char)toupper((unsigned char)buf[0]);
}

// -- Verb normalization: strip 3rd person singular -s when swapping to "you" --
// Write verb text to buffer, removing trailing -s/-es/-ies if present.
static size_t write_verb_base(char* buf, size_t buf_size, size_t written,
                                cos_string_table_t* table, cos_string_id_t id) {
    if (id == COS_STRING_ID_NULL || !table) return written;
    cos_string_view_t sv = cos_string_lookup(table, id);
    if (!sv.data || sv.length == 0) return written;

    size_t len = sv.length;
    const char* data = sv.data;

    // Irregular verbs (never strip the 's')
    const char* irregulars[] = {"is", "was", "has", "does", "goes", "says"};
    for (size_t ir = 0; ir < 6; ir++) {
        size_t ilen = strlen(irregulars[ir]);
        if (len == ilen && memcmp(data, irregulars[ir], ilen) == 0) {
            return buf_append(buf, buf_size, written, data, len);
        }
    }

    // Small lookup for common 3rd person -> base mappings
    if (len == 6 && memcmp(data, "kisses", 6) == 0) return buf_append(buf, buf_size, written, "kiss", 4);
    if (len == 7 && memcmp(data, "watches", 7) == 0) return buf_append(buf, buf_size, written, "watch", 5);
    if (len == 5 && memcmp(data, "boxes", 5) == 0) return buf_append(buf, buf_size, written, "box", 3);
    if (len == 6 && memcmp(data, "buzzes", 6) == 0) return buf_append(buf, buf_size, written, "buzz", 4);
    if (len == 6 && memcmp(data, "misses", 6) == 0) return buf_append(buf, buf_size, written, "miss", 4);
    if (len == 6 && memcmp(data, "passes", 6) == 0) return buf_append(buf, buf_size, written, "pass", 4);
    if (len == 7 && memcmp(data, "pushes", 7) == 0) return buf_append(buf, buf_size, written, "push", 4);
    if (len == 7 && memcmp(data, "teaches", 7) == 0) return buf_append(buf, buf_size, written, "teach", 5);

    // Handle -ies -> -y: "flies" -> "fly", "tries" -> "try"
    if (len > 3 && data[len-3] == 'i' && data[len-2] == 'e' && data[len-1] == 's') {
        char buf2[64];
        size_t blen = len - 3;
        if (blen < sizeof(buf2)) {
            memcpy(buf2, data, blen);
            buf2[blen] = 'y';
            return buf_append(buf, buf_size, written, buf2, blen + 1);
        }
    }

    // General case: remove trailing 's'
    // This handles "likes" -> "like", "uses" -> "use", "runs" -> "run", etc.
    if (len > 1 && data[len-1] == 's') {
        return buf_append(buf, buf_size, written, data, len - 1);
    }

    return buf_append(buf, buf_size, written, data, len);
}

// -- Article insertion helpers ----------------------------------------------
// Simple rule: insert "a" or "an" before singular count nouns that aren't
// preceded by a determiner, pronoun, or possessive.

static bool starts_with_vowel_sound(const char* word, size_t len) {
    if (len == 0) return false;
    char c = (char)tolower((unsigned char)word[0]);
    if (c == 'a' || c == 'e' || c == 'i' || c == 'o' || c == 'u') return true;
    return false;
}

// Check if a word is a pronoun that should be swapped in responses
// Returns true and writes the swapped text
static bool try_swap_pronoun(cos_string_table_t* table, cos_string_id_t id,
                              char* buf, size_t buf_size, size_t* written) {
    if (id == COS_STRING_ID_NULL || !table) return false;
    cos_string_view_t sv = cos_string_lookup(table, id);
    if (sv.length == 0) return false;

    // Map of first-person to second-person
    if (sv.length == 1 && sv.data[0] == 'I') {
        *written = buf_append_cstr(buf, buf_size, *written, "you");
        return true;
    }
    if (sv.length == 2 && memcmp(sv.data, "my", 2) == 0) {
        *written = buf_append_cstr(buf, buf_size, *written, "your");
        return true;
    }
    if (sv.length == 4 && memcmp(sv.data, "mine", 4) == 0) {
        *written = buf_append_cstr(buf, buf_size, *written, "yours");
        return true;
    }
    if ((sv.length == 3 && memcmp(sv.data, "me", 3) == 0) ||
        (sv.length == 3 && memcmp(sv.data, "myself", 6) == 0)) {
        *written = buf_append_cstr(buf, buf_size, *written, "you");
        return true;
    }
    return false;
}

// -- Response template selection --------------------------------------------

static size_t stmt_templates_count = 3;
static const char* stmt_prefixes[] = {
    "you",     // "You like pizza."
    "so you",  // "So you like pizza."
    "you said you", // "You said you like pizza."
};

// -- Generation -------------------------------------------------------------

cos_status_t cos_generator_generate(cos_generator_t* gen,
                                     const cos_semantic_graph_t* meaning,
                                     char* out_buffer,
                                     size_t buffer_size,
                                     size_t* out_written) {
    if (!gen || !meaning || !out_buffer || !out_written) return COS_ERROR_NULL;

    size_t w = 0;
    cos_string_table_t* tbl = gen->strings;

    // Collect nodes from the semantic graph
    cos_graph_node_id_t entities[32];
    cos_graph_node_id_t actions[32];
    cos_graph_node_id_t attributes[32];

    size_t entity_count   = cos_semantic_find_type(meaning, COS_SEMANTIC_ENTITY, entities, 32);
    size_t action_count   = cos_semantic_find_type(meaning, COS_SEMANTIC_ACTION, actions, 32);
    size_t attrib_count   = cos_semantic_find_type(meaning, COS_SEMANTIC_ATTRIBUTE, attributes, 32);

    (void)attrib_count;

    // -- Greeting detection --------------------------------------------------
    bool is_greeting = false;
    const char* greeting_words[] = {"hi", "hello", "hey", "greetings", "yo", "sup",
        "howdy", "good", "morning", "evening", "afternoon", "whats"};
    size_t num_greetings = sizeof(greeting_words) / sizeof(greeting_words[0]);

    for (size_t i = 0; i < entity_count && !is_greeting; i++) {
        cos_semantic_node_t en;
        if (cos_semantic_get_node(meaning, entities[i], &en) == COS_OK && en.text != COS_STRING_ID_NULL) {
            cos_string_view_t sv = cos_string_lookup(tbl, en.text);
            for (size_t g = 0; g < num_greetings; g++) {
                size_t glen = strlen(greeting_words[g]);
                if (sv.length == glen && memcmp(sv.data, greeting_words[g], glen) == 0) {
                    is_greeting = true;
                    break;
                }
            }
        }
    }

    // -- Check if we have context facts (from memory query) -----------------
    if (gen->context_count > 0) {
        // Build response from remembered facts - skip bare entity mentions
        size_t used = 0;
        for (size_t i = 0; i < gen->context_count && used < 3; i++) {
            const cos_fact_t* f = &gen->context_facts[i];
            if (f->predicate == COS_STRING_ID_NULL) continue;
            if (f->object == COS_STRING_ID_NULL) continue;

            if (used == 0) {
                w = buf_append_cstr(out_buffer, buffer_size, w, "you");
            }

            w = buf_append_cstr(out_buffer, buffer_size, w, " ");
            w = buf_append_node_text(out_buffer, buffer_size, w, tbl, f->predicate);
            w = buf_append_cstr(out_buffer, buffer_size, w, " ");

            // Insert article if the object is a singular count noun
            cos_string_view_t obj_sv = cos_string_lookup(tbl, f->object);
            bool needs_article = true;
            // Skip articles for proper names, pronouns, and known uncountable
            const char* no_article_words[] = {"pizza", "music", "water", "food",
                "money", "time", "information", "news", "research", "advice",
                "furniture", "homework", "traffic", "weather", "work",
                "football", "soccer", "tennis", "golf", "baseball",
                "basketball", "hockey", "swimming", "running",
                "programming", "coding", "python", "java", "linux",
                "windows", "apple", "google", "facebook", "twitter"};
            for (size_t na = 0; na < sizeof(no_article_words)/sizeof(no_article_words[0]); na++) {
                size_t len = strlen(no_article_words[na]);
                if (obj_sv.length == len && memcmp(obj_sv.data, no_article_words[na], len) == 0) {
                    needs_article = false;
                    break;
                }
            }
            if (needs_article && obj_sv.length > 0) {
                // Check if word already has an article via a list of words that don't need one
                // (proper nouns, pronouns, etc.)
                if (obj_sv.data[0] == '\'' || obj_sv.data[0] == '$' ||
                    isupper((unsigned char)obj_sv.data[0])) {
                    needs_article = false;
                }
            }
            if (needs_article && obj_sv.length > 0) {
                if (starts_with_vowel_sound(obj_sv.data, obj_sv.length)) {
                    w = buf_append_cstr(out_buffer, buffer_size, w, "an ");
                } else {
                    w = buf_append_cstr(out_buffer, buffer_size, w, "a ");
                }
            }

            w = buf_append_node_text(out_buffer, buffer_size, w, tbl, f->object);

            size_t remaining = 0;
            for (size_t j = i + 1; j < gen->context_count && remaining < 3 - used; j++) {
                const cos_fact_t* f2 = &gen->context_facts[j];
                if (f2->predicate != COS_STRING_ID_NULL && f2->object != COS_STRING_ID_NULL)
                    remaining++;
            }
            if (remaining > 0) {
                w = buf_append_cstr(out_buffer, buffer_size, w, ", and you");
            }
            used++;
        }

        if (used > 0) {
            w = buf_append_char(out_buffer, buffer_size, w, '.');
            goto done;
        }
    }

    // -- Response Selection --------------------------------------------------

    if (is_greeting) {
        // Varied greeting responses
        const char* replies[] = {
            "Hello! How can I help you?",
            "Hi there!",
            "Hey! What's on your mind?",
            "Hello! I'm listening.",
        };
        size_t reply_count = sizeof(replies) / sizeof(replies[0]);
        size_t idx = (entity_count > 0 ? (size_t)entities[0] : 1) % reply_count;
        w = buf_append_cstr(out_buffer, buffer_size, w, replies[idx]);

    } else if (action_count > 0 && entity_count > 0) {
        // Statement with action and entities: build a natural response
        cos_semantic_node_t subj, verb, obj;
        bool have_subj = false, have_verb = false, have_obj = false;

        if (entity_count > 0) {
            have_subj = (cos_semantic_get_node(meaning, entities[0], &subj) == COS_OK);
        }
        if (action_count > 0) {
            have_verb = (cos_semantic_get_node(meaning, actions[0], &verb) == COS_OK);
        }
        if (entity_count > 1) {
            have_obj = (cos_semantic_get_node(meaning, entities[1], &obj) == COS_OK);
        }

        // Build subject: use the subject entity if it's not "I", otherwise "you"
        if (have_subj) {
            cos_string_view_t sv = cos_string_lookup(tbl, subj.text);
            // Check if subject is "I" (should swap to "you")
            if (sv.length == 1 && sv.data[0] == 'I') {
                w = buf_append_cstr(out_buffer, buffer_size, w, "you");
            } else {
                // For other subjects, use them directly with pronoun swap if applicable
                if (!try_swap_pronoun(tbl, subj.text, out_buffer, buffer_size, &w)) {
                    w = buf_append_node_text(out_buffer, buffer_size, w, tbl, subj.text);
                }
            }
        } else {
            w = buf_append_cstr(out_buffer, buffer_size, w, "you");
        }

        // Verb
        if (have_verb) {
            w = buf_append_cstr(out_buffer, buffer_size, w, " ");
            w = write_verb_base(out_buffer, buffer_size, w, tbl, verb.text);
        }

        // Object
        if (have_obj) {
            w = buf_append_cstr(out_buffer, buffer_size, w, " ");
            if (!try_swap_pronoun(tbl, obj.text, out_buffer, buffer_size, &w)) {
                cos_string_view_t ov = cos_string_lookup(tbl, obj.text);
                bool needs_a = true;
                const char* no_art[] = {"pizza", "music", "water", "food", "homework",
                    "money", "information", "news", "research",
                    "football", "soccer", "tennis", "golf", "basketball",
                    "programming", "coding", "python"};
                for (size_t na = 0; na < sizeof(no_art)/sizeof(no_art[0]); na++) {
                    size_t len = strlen(no_art[na]);
                    if (ov.length == len && memcmp(ov.data, no_art[na], len) == 0) {
                        needs_a = false; break;
                    }
                }
                if (needs_a && ov.length > 0 && !isupper((unsigned char)ov.data[0])) {
                    if (starts_with_vowel_sound(ov.data, ov.length))
                        w = buf_append_cstr(out_buffer, buffer_size, w, "an ");
                    else
                        w = buf_append_cstr(out_buffer, buffer_size, w, "a ");
                }
                w = buf_append_node_text(out_buffer, buffer_size, w, tbl, obj.text);
            }
        } else if (attrib_count > 0) {
            w = buf_append_cstr(out_buffer, buffer_size, w, " ");
            cos_semantic_node_t attr;
            if (cos_semantic_get_node(meaning, attributes[0], &attr) == COS_OK) {
                w = buf_append_node_text(out_buffer, buffer_size, w, tbl, attr.text);
            }
        }
        w = buf_append_char(out_buffer, buffer_size, w, '.');

    } else if (entity_count > 0) {
        // Just entity references (no action)
        w = buf_append_cstr(out_buffer, buffer_size, w, "You mentioned ");
        cos_semantic_node_t en;
        for (size_t i = 0; i < entity_count && i < 3; i++) {
            if (cos_semantic_get_node(meaning, entities[i], &en) == COS_OK) {
                if (i > 0) w = buf_append_cstr(out_buffer, buffer_size, w, " and ");
                w = buf_append_node_text(out_buffer, buffer_size, w, tbl, en.text);
            }
        }
        w = buf_append_char(out_buffer, buffer_size, w, '.');

    } else {
        // Fallback responses
        const char* fallbacks[] = {
            "I understand.",
            "Go on.",
            "I'm listening.",
            "Tell me more.",
            "Interesting.",
        };
        size_t idx = (entity_count + action_count) % 5;
        w = buf_append_cstr(out_buffer, buffer_size, w, fallbacks[idx]);
    }

done:
    // Terminate and capitalise
    if (w < buffer_size) out_buffer[w] = '\0';
    else out_buffer[buffer_size - 1] = '\0';
    capitalise(out_buffer, w);
    *out_written = w;
    return COS_OK;
}

// -- Inflection (stub) -------------------------------------------------------

cos_status_t cos_generator_apply_inflection(cos_generator_t* gen,
                                             cos_string_id_t word,
                                             cos_inflection_t inflection,
                                             char* out_buffer,
                                             size_t buffer_size,
                                             size_t* out_written) {
    (void)gen; (void)word; (void)inflection;
    if (!out_buffer || !out_written) return COS_ERROR_NULL;
    if (buffer_size > 0) out_buffer[0] = '\0';
    *out_written = 0;
    return COS_OK;
}

#ifdef __cplusplus
}
#endif
