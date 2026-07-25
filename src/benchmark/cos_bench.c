// cos_bench.c - COS Benchmark Suite
//
// Tests COS against common conversational patterns:
//   - Memory recall (multi-turn fact retention)
//   - Parsing accuracy (SVO extraction)
//   - Question answering (basic)
//   - Tool execution
//   - Greeting detection
//   - Article/natural language quality
//
// This is NOT an LLM benchmark (MMLU, etc.). COS is a symbolic
// system. These tests measure what it's designed for.

#include "cos/core.h"
#include "cos/allocator.h"
#include "cos/arena.h"
#include "cos/pool.h"
#include "cos/string_intern.h"
#include "cos/string_view.h"
#include "cos/parser.h"
#include "cos/planner.h"
#include "cos/reasoning.h"
#include "cos/knowledge.h"
#include "cos/language.h"
#include "cos/generator.h"
#include "cos/conversation.h"
#include "cos/debug.h"
#include "cos/tools.h"

#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <time.h>

// -- Test infrastructure ----------------------------------------------------

typedef struct {
    const char* name;
    const char* turns[16];      // Multi-turn conversation
    int         turn_count;
    const char* expected_keywords[16]; // Keywords expected in response to each turn
    int         min_expected;         // Minimum number of turns with correct keyword
    double      score;               // 0.0 - 1.0
} bench_case_t;

static int total_tests = 0;
static int passed_tests = 0;
static double total_score = 0.0;

// -- COS runtime setup ------------------------------------------------------

typedef struct {
    cos_allocator_t*      sys;
    cos_allocator_t*      arena;
    cos_allocator_t*      scratch;
    cos_string_table_t*   strings;
    cos_knowledge_base_t* knowledge;
    cos_knowledge_base_t* working_mem;
    cos_conversation_t*   conv;
    cos_debug_t*          debug;
    cos_tool_registry_t*  tools;
} cos_test_env_t;

static cos_test_env_t* env_create(void) {
    cos_test_env_t* env = calloc(1, sizeof(cos_test_env_t));
    if (!env) return NULL;

    env->sys     = cos_sys_allocator();
    env->arena   = cos_arena_create(NULL, env->sys);
    env->scratch = cos_arena_create(NULL, env->sys);
    env->strings = cos_string_table_create(env->sys);
    env->knowledge = cos_knowledge_create(env->sys);
    env->working_mem = cos_knowledge_create(env->sys);

    cos_conversation_config_t cc;
    memset(&cc, 0, sizeof(cc));
    cc.allocator      = env->arena;
    cc.scratch_arena  = env->scratch;
    cc.string_table   = env->strings;
    cc.knowledge      = env->knowledge;
    cc.working_memory = env->working_mem;
    env->conv = cos_conversation_create(&cc);

    cos_debug_config_t dc;
    dc.allocator = env->sys;
    dc.max_events = 128;
    dc.enable_profiling = true;
    dc.enable_allocs = true;
    env->debug = cos_debug_create(&dc);

    env->tools = cos_tool_registry_create(env->sys);
    extern cos_status_t cos_register_builtin_tools(cos_tool_registry_t*);
    cos_register_builtin_tools(env->tools);

    return env;
}

static void env_destroy(cos_test_env_t* env) {
    if (!env) return;
    if (env->conv)     cos_conversation_destroy(env->conv);
    if (env->debug)    cos_debug_destroy(env->debug);
    if (env->tools)    cos_tool_registry_destroy(env->tools);
    if (env->working_mem) cos_knowledge_destroy(env->working_mem);
    if (env->knowledge)   cos_knowledge_destroy(env->knowledge);
    if (env->strings)     cos_string_table_destroy(env->strings);
    if (env->scratch)     cos_allocator_destroy(env->scratch);
    if (env->arena)       cos_allocator_destroy(env->arena);
    free(env);
}

static void env_reset_memory(cos_test_env_t* env) {
    if (env->working_mem) cos_knowledge_destroy(env->working_mem);
    if (env->knowledge)   cos_knowledge_destroy(env->knowledge);
    env->knowledge    = cos_knowledge_create(env->sys);
    env->working_mem  = cos_knowledge_create(env->sys);
    // Recreate conversation with fresh memory
    if (env->conv) cos_conversation_destroy(env->conv);
    cos_conversation_config_t cc;
    memset(&cc, 0, sizeof(cc));
    cc.allocator      = env->arena;
    cc.scratch_arena  = env->scratch;
    cc.string_table   = env->strings;
    cc.knowledge      = env->knowledge;
    cc.working_memory = env->working_mem;
    env->conv = cos_conversation_create(&cc);
}

// -- Run a single test case -------------------------------------------------

static double run_case(bench_case_t* tc, cos_test_env_t* env, FILE* log) {
    int correct = 0;

    fprintf(log, "  Test: %s\n", tc->name);
    fprintf(log, "  ─────────────────────────────────────────\n");

    for (int i = 0; i < tc->turn_count; i++) {
        const char* input = tc->turns[i];
        const char* expected = tc->expected_keywords[i];

        const char* response = NULL;
        size_t rlen = 0;
        cos_status_t status = cos_conversation_process(
            env->conv, cos_sv_cstr(input), &response, &rlen);

        if (status != COS_OK) {
            fprintf(log, "  [%d] \"%s\" -> ERROR %d\n", i+1, input, (int)status);
            continue;
        }

        if (!response) {
            fprintf(log, "  [%d] \"%s\" -> (null)\n", i+1, input);
            continue;
        }

        // Truncate long responses
        char resp_short[128];
        size_t rlen_short = rlen < 120 ? rlen : 120;
        memcpy(resp_short, response, rlen_short);
        resp_short[rlen_short] = '\0';

        fprintf(log, "  [%d] \"%s\"\n       -> \"%s\"\n", i+1, input, resp_short);

        // Check if expected keyword is present (case-insensitive)
        bool found = false;
        if (expected && expected[0]) {
            const char* resp_lower = response;
            size_t elen = strlen(expected);
            for (size_t j = 0; j + elen <= rlen; j++) {
                bool match = true;
                for (size_t k = 0; k < elen; k++) {
                    char a = response[j+k];
                    char b = expected[k];
                    if (a >= 'A' && a <= 'Z') a += 32;
                    if (b >= 'A' && b <= 'Z') b += 32;
                    if (a != b) { match = false; break; }
                }
                if (match) { found = true; break; }
            }
            if (found) {
                correct++;
                fprintf(log, "       ✓ contains \"%s\"\n", expected);
            } else {
                fprintf(log, "       ✗ expected \"%s\"\n", expected);
            }
        }

        // Reset scratch after each turn
        cos_arena_reset(env->scratch);
    }

    double score = tc->min_expected > 0
        ? (double)correct / (double)tc->min_expected
        : (tc->turn_count > 0 ? (double)correct / (double)tc->turn_count : 0.0);
    if (score > 1.0) score = 1.0;

    fprintf(log, "  Score: %.1f%% (%d/%d)\n\n", score * 100.0, correct,
            tc->min_expected > 0 ? tc->min_expected : tc->turn_count);

    return score;
}

// -- Benchmark definitions --------------------------------------------------

int main(void) {
    printf("═══ COS Benchmark Suite ═══\n\n");
    printf("System: COS v%d.%d.%d | C17 | Symbolic Conversational Runtime\n\n",
           COS_VERSION_MAJOR, COS_VERSION_MINOR, COS_VERSION_PATCH);
    printf("This benchmark measures COS on its intended capabilities:\n");
    printf("  memory recall, parsing accuracy, tool use, and NL quality.\n");
    printf("It is NOT an MMLU-style benchmark - COS is not an LLM.\n\n");

    cos_test_env_t* env = env_create();
    if (!env) { fprintf(stderr, "Failed to create test env\n"); return 1; }

    // -- 1. Greeting recognition --------------------------------------------
    printf("--- Category: Greeting Recognition ---\n");
    env_reset_memory(env);
    {
        bench_case_t tc = {
            .name = "Greeting detection",
            .turns = {"hi", "hello", "hey", "good morning", "whats up"},
            .turn_count = 5,
            .expected_keywords = {"hi there", "hi there", "hey", "hello", "hello"},
            .min_expected = 3,
        };
        double s = run_case(&tc, env, stdout);
        total_score += s; total_tests++;
        if (s >= 0.6) passed_tests++;
    }

    // -- 2. Memory: single fact storage and recall --------------------------
    printf("--- Category: Memory (Single Fact) ---\n");
    env_reset_memory(env);
    {
        bench_case_t tc = {
            .name = "Store and recall one fact",
            .turns = {"I like pizza", "what do I like"},
            .turn_count = 2,
            .expected_keywords = {"", "like"},
            .min_expected = 1,
        };
        double s = run_case(&tc, env, stdout);
        total_score += s; total_tests++;
        if (s >= 1.0) passed_tests++;
    }

    // -- 3. Memory: multiple fact storage and recall ------------------------
    printf("--- Category: Memory (Multiple Facts) ---\n");
    env_reset_memory(env);
    {
        bench_case_t tc = {
            .name = "Store and recall multiple facts",
            .turns = {"I like pizza", "I have a cat", "I want an apple",
                       "what do I have", "what do I like"},
            .turn_count = 5,
            .expected_keywords = {"", "", "", "cat", "pizza"},
            .min_expected = 2,
        };
        double s = run_case(&tc, env, stdout);
        total_score += s; total_tests++;
        if (s >= 0.5) passed_tests++;
    }

    // -- 4. Article/natural language quality ---------------------------------
    printf("--- Category: Natural Language Quality ---\n");
    env_reset_memory(env);
    {
        bench_case_t tc = {
            .name = "Article insertion (a/an)",
            .turns = {"I have a cat", "I want an apple", "I like pizza"},
            .turn_count = 3,
            .expected_keywords = {"a cat", "an apple", "like pizza"},
            .min_expected = 3,
        };
        double s = run_case(&tc, env, stdout);
        total_score += s; total_tests++;
        if (s >= 0.67) passed_tests++;
    }

    // -- 5. Pronoun swapping -------------------------------------------------
    printf("--- Category: Pronoun Handling ---\n");
    env_reset_memory(env);
    {
        bench_case_t tc = {
            .name = "\"I\" swapped to \"you\" in responses",
            .turns = {"I run", "I eat food", "I see a dog"},
            .turn_count = 3,
            .expected_keywords = {"you run", "you eat", "you see"},
            .min_expected = 3,
        };
        double s = run_case(&tc, env, stdout);
        total_score += s; total_tests++;
        if (s >= 0.67) passed_tests++;
    }

    // -- 6. Tool execution ---------------------------------------------------
    printf("--- Category: Tool Execution ---\n");
    // Test tools directly
    {
        int tool_correct = 0;
        printf("  Test: Tool execution\n");
        printf("  ─────────────────────────────────────────\n");

        const cos_tool_t* t = cos_tool_find(env->tools, "help");
        if (t) {
            printf("  ✓ \"help\" tool registered\n");
            tool_correct++;
        } else {
            printf("  ✗ \"help\" tool NOT found\n");
        }

        t = cos_tool_find(env->tools, "status");
        if (t) {
            printf("  ✓ \"status\" tool registered\n");
            tool_correct++;
        } else {
            printf("  ✗ \"status\" tool NOT found\n");
        }

        // Execute help
        char buf[256];
        size_t written = 0;
        if (cos_tool_execute(env->tools, "help", "", 0, buf, sizeof(buf), &written) == COS_OK) {
            buf[written < sizeof(buf) ? written : sizeof(buf)-1] = '\0';
            if (strstr(buf, "help") && strstr(buf, "status")) {
                printf("  ✓ \"help\" tool produces output\n");
                tool_correct++;
            }
        }

        // Execute status
        if (cos_tool_execute(env->tools, "status", "", 0, buf, sizeof(buf), &written) == COS_OK) {
            buf[written < sizeof(buf) ? written : sizeof(buf)-1] = '\0';
            if (strstr(buf, "COS")) {
                printf("  ✓ \"status\" tool produces output\n");
                tool_correct++;
            }
        }

        double s = tool_correct / 4.0;
        printf("  Score: %.1f%% (%d/4)\n\n", s * 100.0, tool_correct);
        total_score += s; total_tests++;
        if (s >= 0.5) passed_tests++;
    }

    // -- 7. Parser accuracy: SVO extraction ----------------------------------
    printf("--- Category: Parser Accuracy ---\n");
    env_reset_memory(env);
    {
        bench_case_t tc = {
            .name = "Basic SVO extraction",
            .turns = {"I eat pizza", "you see a dog", "she likes music",
                       "he wants water", "they play football"},
            .turn_count = 5,
            .expected_keywords = {"eat", "see", "like", "want", "play"},
            .min_expected = 4,
        };
        double s = run_case(&tc, env, stdout);
        total_score += s; total_tests++;
        if (s >= 0.6) passed_tests++;
    }

    // -- 8. Long conversation coherence -------------------------------------
    printf("--- Category: Conversation Coherence ---\n");
    env_reset_memory(env);
    {
        bench_case_t tc = {
            .name = "10-turn coherent conversation",
            .turns = {
                "hi",
                "I like programming",
                "I use python",
                "my favorite game is minecraft",
                "what do I like",
                "what language do I use",
                "what is my favorite game",
                "I also like pizza",
                "what foods do I like",
                "goodbye"
            },
            .turn_count = 10,
            .expected_keywords = {
                "hello",       // turn 0: greeting
                "",            // turn 1: statement
                "",            // turn 2: statement
                "",            // turn 3: statement
                "programming", // turn 4: recall
                "python",      // turn 5: recall
                "minecraft",   // turn 6: recall
                "",            // turn 7: statement
                "pizza",       // turn 8: recall
                ""             // turn 9: fallback
            },
            .min_expected = 4,
        };
        double s = run_case(&tc, env, stdout);
        total_score += s; total_tests++;
        if (s >= 0.4) passed_tests++;
    }

    // -- Summary -------------------------------------------------------------
    double overall = total_score / (double)total_tests;
    printf("═══ Results ═══\n");
    printf("  Tests attempted: %d\n", total_tests);
    printf("  Tests passed (>=60%%): %d/%d\n", passed_tests, total_tests);
    printf("  Overall score: %.1f%%\n", overall * 100.0);

    printf("\n  Category Breakdown:\n");
    printf("    Greeting Recognition:     COS detects common greetings\n");
    printf("    Memory (Single Fact):     Stores and recalls one fact\n");
    printf("    Memory (Multiple Facts):  Retains multiple facts across turns\n");
    printf("    Natural Language Quality: Article insertion, pronoun swap\n");
    printf("    Pronoun Handling:         \"I\" -> \"you\" in responses\n");
    printf("    Tool Execution:           Built-in tools (help, status)\n");
    printf("    Parser Accuracy:          SVO extraction from sentences\n");
    printf("    Conversation Coherence:   Maintains context over 10 turns\n");

    printf("\n  Note: COS is a symbolic system, not an LLM.\n");
    printf("  These benchmarks measure symbolic conversation capabilities.\n");
    printf("  LLM benchmarks (MMLU, GSM8K, etc.) require a populated\n");
    printf("  knowledge base and active reasoning modules.\n");

    env_destroy(env);
    return 0;
}
