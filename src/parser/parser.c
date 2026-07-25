// parser.c — Semantic Parser Engine Implementation
//
// Design: Multi-stage pipeline that converts raw text to semantic graphs.
// Stages:
//   1. Tokenizer: word and punctuation splitting
//   2. POS tagging: rule-based part-of-speech assignment
//   3. Phrase building: groups tokens into phrases (NP, VP, etc.)
//   4. Semantic mapping: builds the semantic graph from phrase structure
//
// Each stage uses the scratch arena for temporary allocations.

#include "cos/core.h"
#include "cos/parser.h"
#include "cos/semantic.h"
#include "cos/string_intern.h"
#include "cos/allocator.h"
#include <string.h>
#include <ctype.h>
#include <stdlib.h>
#include <stdalign.h>

#ifdef __cplusplus
extern "C" {
#endif

// ── Parser Context ───────────────────────────────────────────────────────
struct cos_parser_s {
    cos_string_table_t* string_table;
    cos_allocator_t*    allocator;
    cos_allocator_t*    scratch;

    // Simple rule-based lexicon (built-in small dictionary)
    struct {
        const char* word;
        cos_pos_tag_t tag;
    } *lexicon;
    size_t lexicon_count;
    size_t lexicon_capacity;
};

// ── Built-in lexicon entries ─────────────────────────────────────────────
// Minimal lexicon for core English words. A production system would load
// a full dictionary from file.
static const struct {
    const char* word;
    cos_pos_tag_t tag;
} g_builtin_lexicon[] = {
    // Pronouns
    {"i",       COS_POS_PRONOUN},
    {"you",     COS_POS_PRONOUN},
    {"he",      COS_POS_PRONOUN},
    {"she",     COS_POS_PRONOUN},
    {"it",      COS_POS_PRONOUN},
    {"we",      COS_POS_PRONOUN},
    {"they",    COS_POS_PRONOUN},
    {"me",      COS_POS_PRONOUN},
    {"him",     COS_POS_PRONOUN},
    {"her",     COS_POS_PRONOUN},
    {"us",      COS_POS_PRONOUN},
    {"them",    COS_POS_PRONOUN},
    {"my",      COS_POS_PRONOUN},
    {"your",    COS_POS_PRONOUN},
    {"his",     COS_POS_PRONOUN},
    {"its",     COS_POS_PRONOUN},
    {"our",     COS_POS_PRONOUN},
    {"their",   COS_POS_PRONOUN},
    // Determiners
    {"the",     COS_POS_DETERMINER},
    {"a",       COS_POS_DETERMINER},
    {"an",      COS_POS_DETERMINER},
    {"this",    COS_POS_DETERMINER},
    {"that",    COS_POS_DETERMINER},
    {"these",   COS_POS_DETERMINER},
    {"those",   COS_POS_DETERMINER},
    {"some",    COS_POS_DETERMINER},
    {"any",     COS_POS_DETERMINER},
    {"every",   COS_POS_DETERMINER},
    {"no",      COS_POS_DETERMINER},
    // Common verbs
    {"is",      COS_POS_VERB},
    {"am",      COS_POS_VERB},
    {"are",     COS_POS_VERB},
    {"was",     COS_POS_VERB},
    {"were",    COS_POS_VERB},
    {"be",      COS_POS_VERB},
    {"been",    COS_POS_VERB},
    {"being",   COS_POS_VERB},
    {"have",    COS_POS_VERB},
    {"has",     COS_POS_VERB},
    {"had",     COS_POS_VERB},
    {"do",      COS_POS_VERB},
    {"does",    COS_POS_VERB},
    {"did",     COS_POS_VERB},
    {"will",    COS_POS_VERB},
    {"would",   COS_POS_VERB},
    {"can",     COS_POS_VERB},
    {"could",   COS_POS_VERB},
    {"shall",   COS_POS_VERB},
    {"should",  COS_POS_VERB},
    {"may",     COS_POS_VERB},
    {"might",   COS_POS_VERB},
    {"must",    COS_POS_VERB},
    {"want",    COS_POS_VERB},
    {"like",    COS_POS_VERB},
    {"know",    COS_POS_VERB},
    {"think",   COS_POS_VERB},
    {"say",     COS_POS_VERB},
    {"go",      COS_POS_VERB},
    {"get",     COS_POS_VERB},
    {"make",    COS_POS_VERB},
    {"take",    COS_POS_VERB},
    {"come",    COS_POS_VERB},
    {"see",     COS_POS_VERB},
    {"use",     COS_POS_VERB},
    {"find",    COS_POS_VERB},
    {"tell",    COS_POS_VERB},
    {"ask",     COS_POS_VERB},
    {"work",    COS_POS_VERB},
    {"seem",    COS_POS_VERB},
    {"feel",    COS_POS_VERB},
    {"try",     COS_POS_VERB},
    {"leave",   COS_POS_VERB},
    {"call",    COS_POS_VERB},
    {"eat",     COS_POS_VERB},
    {"run",     COS_POS_VERB},
    {"play",    COS_POS_VERB},
    {"read",    COS_POS_VERB},
    {"write",   COS_POS_VERB},
    {"code",    COS_POS_VERB},
    {"love",    COS_POS_VERB},
    {"hate",    COS_POS_VERB},
    {"need",    COS_POS_VERB},
    {"buy",     COS_POS_VERB},
    {"sell",    COS_POS_VERB},
    {"watch",   COS_POS_VERB},
    {"show",    COS_POS_VERB},
    {"bring",   COS_POS_VERB},
    {"keep",    COS_POS_VERB},
    {"put",     COS_POS_VERB},
    {"set",     COS_POS_VERB},
    {"let",     COS_POS_VERB},
    {"begin",   COS_POS_VERB},
    {"move",    COS_POS_VERB},
    {"live",    COS_POS_VERB},
    {"stay",    COS_POS_VERB},
    {"wait",    COS_POS_VERB},
    {"open",    COS_POS_VERB},
    {"close",   COS_POS_VERB},
    {"start",   COS_POS_VERB},
    {"stop",    COS_POS_VERB},
    {"help",    COS_POS_VERB},
    {"talk",    COS_POS_VERB},
    {"walk",    COS_POS_VERB},
    {"sit",     COS_POS_VERB},
    {"stand",   COS_POS_VERB},
    {"learn",   COS_POS_VERB},
    {"teach",   COS_POS_VERB},
    {"remember",COS_POS_VERB},
    {"forget",  COS_POS_VERB},
    {"follow",  COS_POS_VERB},
    {"lead",    COS_POS_VERB},
    {"hold",    COS_POS_VERB},
    {"turn",    COS_POS_VERB},
    {"cut",     COS_POS_VERB},
    {"draw",    COS_POS_VERB},
    {"sing",    COS_POS_VERB},
    {"swim",    COS_POS_VERB},
    {"drive",   COS_POS_VERB},
    {"fly",     COS_POS_VERB},
    {"grow",    COS_POS_VERB},
    {"send",    COS_POS_VERB},
    {"receive", COS_POS_VERB},
    {"build",   COS_POS_VERB},
    {"break",   COS_POS_VERB},
    {"choose",  COS_POS_VERB},
    {"sleep",   COS_POS_VERB},
    {"dream",   COS_POS_VERB},
    {"believe", COS_POS_VERB},
    {"expect",  COS_POS_VERB},
    {"hope",    COS_POS_VERB},
    {"wish",    COS_POS_VERB},
    {"mean",    COS_POS_VERB},
    {"agree",   COS_POS_VERB},
    {"allow",   COS_POS_VERB},
    {"accept",  COS_POS_VERB},
    {"refuse",  COS_POS_VERB},
    {"offer",   COS_POS_VERB},
    {"appear",  COS_POS_VERB},
    {"happen",  COS_POS_VERB},
    {"continue",COS_POS_VERB},
    {"change",  COS_POS_VERB},
    {"become",  COS_POS_VERB},
    {"belong",  COS_POS_VERB},
    {"consist", COS_POS_VERB},
    {"contain", COS_POS_VERB},
    {"include", COS_POS_VERB},
    {"support", COS_POS_VERB},
    {"provide", COS_POS_VERB},
    {"produce", COS_POS_VERB},
    {"create",  COS_POS_VERB},
    {"destroy", COS_POS_VERB},
    {"push",    COS_POS_VERB},
    {"pull",    COS_POS_VERB},
    {"carry",   COS_POS_VERB},
    {"catch",   COS_POS_VERB},
    {"throw",   COS_POS_VERB},
    {"drop",    COS_POS_VERB},
    {"fill",    COS_POS_VERB},
    {"cover",   COS_POS_VERB},
    {"miss",    COS_POS_VERB},
    {"finish",  COS_POS_VERB},
    {"enjoy",   COS_POS_VERB},
    {"hate",    COS_POS_VERB},
    {"prefer",  COS_POS_VERB},
    {"practice",COS_POS_VERB},
    {"prepare", COS_POS_VERB},
    {"pretend", COS_POS_VERB},
    {"promise", COS_POS_VERB},
    {"protect", COS_POS_VERB},
    {"prove",   COS_POS_VERB},
    {"raise",   COS_POS_VERB},
    {"reach",   COS_POS_VERB},
    {"realize", COS_POS_VERB},
    {"remain",  COS_POS_VERB},
    {"replace", COS_POS_VERB},
    {"report",  COS_POS_VERB},
    {"require", COS_POS_VERB},
    {"respect", COS_POS_VERB},
    {"result",  COS_POS_VERB},
    {"return",  COS_POS_VERB},
    {"suggest", COS_POS_VERB},
    {"suppose", COS_POS_VERB},
    // Common 3rd person singular verb forms
    {"likes",   COS_POS_VERB},
    {"runs",    COS_POS_VERB},
    {"plays",   COS_POS_VERB},
    {"eats",    COS_POS_VERB},
    {"uses",    COS_POS_VERB},
    {"needs",   COS_POS_VERB},
    {"wants",   COS_POS_VERB},
    {"makes",   COS_POS_VERB},
    {"takes",   COS_POS_VERB},
    {"comes",   COS_POS_VERB},
    {"goes",    COS_POS_VERB},
    {"does",    COS_POS_VERB},
    {"has",     COS_POS_VERB},
    {"says",    COS_POS_VERB},
    {"gets",    COS_POS_VERB},
    {"knows",   COS_POS_VERB},
    {"thinks",  COS_POS_VERB},
    {"sees",    COS_POS_VERB},
    {"works",   COS_POS_VERB},
    {"calls",   COS_POS_VERB},
    {"tells",   COS_POS_VERB},
    {"asks",    COS_POS_VERB},
    {"tries",   COS_POS_VERB},
    {"leaves",  COS_POS_VERB},
    {"feels",   COS_POS_VERB},
    {"seems",   COS_POS_VERB},
    {"loves",   COS_POS_VERB},
    {"hates",   COS_POS_VERB},
    {"reads",   COS_POS_VERB},
    {"writes",  COS_POS_VERB},
    {"buys",    COS_POS_VERB},
    {"sells",   COS_POS_VERB},
    {"watches", COS_POS_VERB},
    {"brings",  COS_POS_VERB},
    {"keeps",   COS_POS_VERB},
    {"puts",    COS_POS_VERB},
    {"starts",  COS_POS_VERB},
    {"stops",   COS_POS_VERB},
    {"helps",   COS_POS_VERB},
    {"talks",   COS_POS_VERB},
    {"walks",   COS_POS_VERB},
    {"learns",  COS_POS_VERB},
    {"teaches", COS_POS_VERB},
    {"follows", COS_POS_VERB},
    {"holds",   COS_POS_VERB},
    {"turns",   COS_POS_VERB},
    {"sends",   COS_POS_VERB},
    {"builds",  COS_POS_VERB},
    {"breaks",  COS_POS_VERB},
    {"sleeps",  COS_POS_VERB},
    {"dreams",  COS_POS_VERB},
    {"believes",COS_POS_VERB},
    {"changes", COS_POS_VERB},
    {"creates", COS_POS_VERB},
    {"finishes",COS_POS_VERB},
    {"enjoys",  COS_POS_VERB},
    {"prefers", COS_POS_VERB},
    // Common prepositions
    {"in",      COS_POS_PREPOSITION},
    {"on",      COS_POS_PREPOSITION},
    {"at",      COS_POS_PREPOSITION},
    {"to",      COS_POS_PREPOSITION},
    {"for",     COS_POS_PREPOSITION},
    {"with",    COS_POS_PREPOSITION},
    {"by",      COS_POS_PREPOSITION},
    {"from",    COS_POS_PREPOSITION},
    {"of",      COS_POS_PREPOSITION},
    {"about",   COS_POS_PREPOSITION},
    {"into",    COS_POS_PREPOSITION},
    {"through", COS_POS_PREPOSITION},
    {"during",  COS_POS_PREPOSITION},
    {"before",  COS_POS_PREPOSITION},
    {"after",   COS_POS_PREPOSITION},
    {"above",   COS_POS_PREPOSITION},
    {"below",   COS_POS_PREPOSITION},
    {"between", COS_POS_PREPOSITION},
    {"under",   COS_POS_PREPOSITION},
    // Common conjunctions
    {"and",     COS_POS_CONJUNCTION},
    {"or",      COS_POS_CONJUNCTION},
    {"but",     COS_POS_CONJUNCTION},
    {"if",      COS_POS_CONJUNCTION},
    {"because", COS_POS_CONJUNCTION},
    {"when",    COS_POS_CONJUNCTION},
    {"while",   COS_POS_CONJUNCTION},
    {"although",COS_POS_CONJUNCTION},
    {"since",   COS_POS_CONJUNCTION},
    {"unless",  COS_POS_CONJUNCTION},
    {"so",      COS_POS_CONJUNCTION},
    // Question words
    {"what",    COS_POS_QUESTION},
    {"where",   COS_POS_QUESTION},
    {"when",    COS_POS_QUESTION},
    {"why",     COS_POS_QUESTION},
    {"who",     COS_POS_QUESTION},
    {"whom",    COS_POS_QUESTION},
    {"whose",   COS_POS_QUESTION},
    {"which",   COS_POS_QUESTION},
    {"how",     COS_POS_QUESTION},
    // Common adjectives
    {"good",    COS_POS_ADJECTIVE},
    {"bad",     COS_POS_ADJECTIVE},
    {"new",     COS_POS_ADJECTIVE},
    {"first",   COS_POS_ADJECTIVE},
    {"last",    COS_POS_ADJECTIVE},
    {"long",    COS_POS_ADJECTIVE},
    {"great",   COS_POS_ADJECTIVE},
    {"little",  COS_POS_ADJECTIVE},
    {"own",     COS_POS_ADJECTIVE},
    {"other",   COS_POS_ADJECTIVE},
    {"old",     COS_POS_ADJECTIVE},
    {"right",   COS_POS_ADJECTIVE},
    {"high",    COS_POS_ADJECTIVE},
    {"small",   COS_POS_ADJECTIVE},
    {"large",   COS_POS_ADJECTIVE},
    {"next",    COS_POS_ADJECTIVE},
    {"early",   COS_POS_ADJECTIVE},
    {"young",   COS_POS_ADJECTIVE},
    {"important", COS_POS_ADJECTIVE},
    {"possible",COS_POS_ADJECTIVE},
    // Common adverbs
    {"not",     COS_POS_ADVERB},
    {"also",    COS_POS_ADVERB},
    {"very",    COS_POS_ADVERB},
    {"often",   COS_POS_ADVERB},
    {"always",  COS_POS_ADVERB},
    {"never",   COS_POS_ADVERB},
    {"here",    COS_POS_ADVERB},
    {"there",   COS_POS_ADVERB},
    {"now",     COS_POS_ADVERB},
    {"then",    COS_POS_ADVERB},
    {"just",    COS_POS_ADVERB},
    {"only",    COS_POS_ADVERB},
    {"really",  COS_POS_ADVERB},
    {"well",    COS_POS_ADVERB},
    {"even",    COS_POS_ADVERB},
    {"still",   COS_POS_ADVERB},
    {"already", COS_POS_ADVERB},
    // Numerals
    {"one",     COS_POS_NUMERAL},
    {"two",     COS_POS_NUMERAL},
    {"three",   COS_POS_NUMERAL},
    {"four",    COS_POS_NUMERAL},
    {"five",    COS_POS_NUMERAL},
    {"ten",     COS_POS_NUMERAL},
    {"hundred", COS_POS_NUMERAL},
    {"thousand",COS_POS_NUMERAL},
};

// ── Part-of-Speech Tagging ───────────────────────────────────────────────
static cos_pos_tag_t tag_word(cos_string_view_t word, const cos_parser_t* parser) {
    // Lexicon lookup
    for (size_t i = 0; i < parser->lexicon_count; i++) {
        size_t len = strlen(parser->lexicon[i].word);
        if (word.length == len && memcmp(word.data, parser->lexicon[i].word, len) == 0) {
            return parser->lexicon[i].tag;
        }
    }

    // Heuristics for unknown words
    if (word.length > 0) {
        char first = (char)tolower((unsigned char)word.data[0]);
        char last  = (char)tolower((unsigned char)word.data[word.length - 1]);

        // Capitalized word → likely proper noun
        if (isupper((unsigned char)word.data[0]) && word.length > 1) {
            return COS_POS_NOUN;
        }

        // Ends in -ing → could be gerund (noun) or present participle (verb)
        // Common -ing words that are typically nouns/gerunds
        if (word.length > 4 && memcmp(word.data + word.length - 3, "ing", 3) == 0) {
            // Check list of common -ing nouns/gerunds
            const char* ing_nouns[] = {"programming", "coding", "gaming", "swimming",
                "running", "walking", "shopping", "dancing", "singing",
                "reading", "writing", "drawing", "painting", "cooking",
                "baking", "fishing", "hunting", "camping", "climbing",
                "skiing", "boxing", "wrestling", "shooting", "bowling",
                "golfing", "sailing", "diving", "surfing", "skating",
                "cycling", "jogging", "hiking", "riding", "meeting",
                "morning", "evening", "building", "ceiling", "flooring",
                "marketing", "advertising", "accounting", "engineering",
                "manufacturing", "processing", "training", "learning",
                "reasoning", "feeling", "meaning", "being", "thing",
                "everything", "something", "nothing", "understanding"};
            size_t ncount = sizeof(ing_nouns) / sizeof(ing_nouns[0]);
            for (size_t i = 0; i < ncount; i++) {
                size_t ilen = strlen(ing_nouns[i]);
                if (word.length == ilen && memcmp(word.data, ing_nouns[i], ilen) == 0) {
                    return COS_POS_NOUN;
                }
            }
            // Not in the noun list → keep as verb
            return COS_POS_VERB;
        }

        // Ends in -ed → past tense
        if (word.length > 3 && memcmp(word.data + word.length - 2, "ed", 2) == 0) {
            return COS_POS_VERB;
        }

        // Ends in -ly → adverb
        if (word.length > 2 && memcmp(word.data + word.length - 2, "ly", 2) == 0) {
            return COS_POS_ADVERB;
        }

        // Ends in -s → plural noun or 3rd person verb
        if (last == 's') {
            return COS_POS_NOUN;
        }

        // Numeric
        if (isdigit((unsigned char)first)) {
            return COS_POS_NUMERAL;
        }
    }

    // Default: noun
    return COS_POS_NOUN;
}

// ── Basic Semantic Graph Builder ─────────────────────────────────────────
// Builds a simple subject-verb-object semantic graph from tagged tokens.
// This is a simplified parser — a production version would use a proper
// grammar-driven parser.

static cos_status_t build_semantic_graph(cos_parser_t* parser,
                                          cos_token_t* tokens,
                                          size_t token_count,
                                          cos_semantic_graph_t* graph,
                                          cos_allocator_t* scratch) {
    (void)scratch;

    // Find main verb and surrounding structure
    cos_graph_node_id_t subject_node = COS_NODE_ID_NULL;
    cos_graph_node_id_t verb_node    = COS_NODE_ID_NULL;
    cos_graph_node_id_t object_node  = COS_NODE_ID_NULL;

    // Stage 1: Find the verb, then subject before it, object after it
    size_t verb_idx = token_count;  // Beyond end if not found

    for (size_t i = 0; i < token_count; i++) {
        if (tokens[i].pos == COS_POS_VERB) {
            verb_idx = i;
            break;
        }
    }

    // Create verb node
    if (verb_idx < token_count) {
        cos_string_id_t text_id = cos_string_intern(parser->string_table, tokens[verb_idx].text);
        verb_node = cos_semantic_add_node(graph, COS_SEMANTIC_ACTION, text_id, text_id, 0.9f);
    }

    // Collect subject (words before verb)
    if (verb_idx > 0) {
        // Find the main subject noun (rightmost noun before verb)
        for (size_t i = verb_idx; i > 0; i--) {
            size_t idx = i - 1;
            cos_pos_tag_t tag = tokens[idx].pos;

            // Skip determiners and prepositions
            if (tag == COS_POS_DETERMINER || tag == COS_POS_PREPOSITION ||
                tag == COS_POS_CONJUNCTION || tag == COS_POS_PUNCTUATION ||
                tag == COS_POS_QUESTION) {
                continue;
            }

            // Take the last noun/pronoun as the primary subject
            if (tag == COS_POS_NOUN || tag == COS_POS_PRONOUN) {
                if (subject_node == COS_NODE_ID_NULL) {
                    cos_string_id_t text_id = cos_string_intern(parser->string_table, tokens[idx].text);
                    subject_node = cos_semantic_add_node(graph, COS_SEMANTIC_ENTITY, text_id, text_id, 0.8f);
                }
            }
        }
    }

    // Collect object (words after verb)
    if (verb_idx < token_count) {
        for (size_t i = verb_idx + 1; i < token_count; i++) {
            cos_pos_tag_t tag = tokens[i].pos;
            if (tag == COS_POS_DETERMINER || tag == COS_POS_PREPOSITION) continue;
            if (tag == COS_POS_PUNCTUATION) break;

            if (tag == COS_POS_NOUN || tag == COS_POS_PRONOUN || tag == COS_POS_ADJECTIVE) {
                if (object_node == COS_NODE_ID_NULL) {
                    cos_string_id_t text_id = cos_string_intern(parser->string_table, tokens[i].text);
                    cos_semantic_type_t obj_type = (tag == COS_POS_ADJECTIVE) ? COS_SEMANTIC_ATTRIBUTE : COS_SEMANTIC_ENTITY;
                    object_node = cos_semantic_add_node(graph, obj_type, text_id, text_id, 0.7f);
                }
            }
        }
    }

    // Check for question words - if found, add a QUESTION type node
    for (size_t i = 0; i < token_count; i++) {
        if (tokens[i].pos == COS_POS_QUESTION) {
            cos_string_id_t qid = cos_string_intern(parser->string_table, tokens[i].text);
            cos_graph_node_id_t qnode = cos_semantic_add_node(graph, COS_SEMANTIC_QUESTION,
                qid, qid, 0.9f);
            if (qnode != COS_NODE_ID_NULL) {
                cos_graph_node_id_t root = cos_semantic_root(graph);
                cos_semantic_add_edge(graph, root, qnode, COS_ROLE_REFERENCE, 0.7f);
            }
            break;
        }
    }

    // Connect nodes
    cos_graph_node_id_t root = cos_semantic_root(graph);

    if (subject_node != COS_NODE_ID_NULL && verb_node != COS_NODE_ID_NULL) {
        cos_semantic_add_edge(graph, subject_node, verb_node, COS_ROLE_SUBJECT, 1.0f);
    }

    if (verb_node != COS_NODE_ID_NULL && object_node != COS_NODE_ID_NULL) {
        cos_semantic_add_edge(graph, verb_node, object_node, COS_ROLE_OBJECT, 1.0f);
    }

    // Link root to main nodes
    if (subject_node != COS_NODE_ID_NULL) {
        cos_semantic_add_edge(graph, root, subject_node, COS_ROLE_REFERENCE, 0.5f);
    } else if (verb_node != COS_NODE_ID_NULL) {
        cos_semantic_add_edge(graph, root, verb_node, COS_ROLE_REFERENCE, 0.5f);
    }

    if (object_node != COS_NODE_ID_NULL) {
        cos_semantic_add_edge(graph, root, object_node, COS_ROLE_REFERENCE, 0.3f);
    }

    return COS_OK;
}

// ── Parser Lifecycle ─────────────────────────────────────────────────────

cos_parser_t* cos_parser_create(const cos_parser_config_t* config) {
    if (!config || !config->string_table) return NULL;

    cos_parser_t* parser = (cos_parser_t*)
        config->allocator->alloc(config->allocator, sizeof(cos_parser_t), alignof(cos_parser_t));
    if (!parser) return NULL;

    parser->string_table = config->string_table;
    parser->allocator    = config->allocator ? config->allocator : cos_sys_allocator();
    parser->scratch      = config->scratch;

    // Initialize lexicon from built-in data
    size_t builtin_count = sizeof(g_builtin_lexicon) / sizeof(g_builtin_lexicon[0]);
    parser->lexicon_capacity = builtin_count + 64;
    parser->lexicon = (void*)parser->allocator->alloc(parser->allocator,
        parser->lexicon_capacity * sizeof(parser->lexicon[0]), alignof(max_align_t));
    if (!parser->lexicon) {
        parser->allocator->free(parser->allocator, parser, sizeof(cos_parser_t));
        return NULL;
    }

    parser->lexicon_count = builtin_count;
    for (size_t i = 0; i < builtin_count; i++) {
        parser->lexicon[i].word = g_builtin_lexicon[i].word;
        parser->lexicon[i].tag  = g_builtin_lexicon[i].tag;
    }

    return parser;
}

void cos_parser_destroy(cos_parser_t* parser) {
    if (!parser) return;
    if (parser->lexicon) {
        parser->allocator->free(parser->allocator, parser->lexicon,
            parser->lexicon_capacity * sizeof(parser->lexicon[0]));
    }
    parser->allocator->free(parser->allocator, parser, sizeof(cos_parser_t));
}

// ── Parsing ──────────────────────────────────────────────────────────────

cos_status_t cos_parser_parse(cos_parser_t* parser,
                               cos_string_view_t input,
                               cos_semantic_graph_t** out_graph) {
    if (!parser || !out_graph) return COS_ERROR_NULL;

    // Create output graph
    cos_allocator_t* alloc = parser->allocator;
    *out_graph = cos_semantic_create(alloc);
    if (!*out_graph) return COS_ERROR_NOMEM;

    // Stage 1: Tokenize
    cos_token_t* tokens = NULL;
    size_t token_count = 0;
    cos_status_t status = cos_tokenize(parser, input, &tokens, &token_count);
    if (status != COS_OK) {
        cos_semantic_destroy(*out_graph);
        *out_graph = NULL;
        return status;
    }

    // Stage 2: POS tag each token
    for (size_t i = 0; i < token_count; i++) {
        tokens[i].pos        = tag_word(tokens[i].text, parser);
        tokens[i].text_id    = cos_string_intern(parser->string_table, tokens[i].text);
        tokens[i].confidence = (tokens[i].pos != COS_POS_UNKNOWN) ? 0.8f : 0.3f;
    }

    // Stage 3-4: Build semantic graph
    cos_allocator_t* scratch = parser->scratch ? parser->scratch : alloc;
    status = build_semantic_graph(parser, tokens, token_count, *out_graph, scratch);

    free(tokens);  // Tokenizer currently uses malloc — will migrate to arena
    return status;
}

// ── Incremental Parsing ──────────────────────────────────────────────────

cos_status_t cos_parser_feed(cos_parser_t* parser,
                              cos_string_view_t partial,
                              cos_semantic_graph_t* graph) {
    (void)parser;
    (void)partial;
    (void)graph;
    // Stub for incremental parsing
    return COS_ERROR_NOT_IMPL;
}

cos_status_t cos_parser_finalize(cos_parser_t* parser,
                                  cos_semantic_graph_t* graph) {
    (void)parser;
    (void)graph;
    return COS_OK;
}

#ifdef __cplusplus
}
#endif
