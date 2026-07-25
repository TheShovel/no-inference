// main.c — COS Main Entry Point
//
// Design: Initializes all subsystems, starts the conversation loop.
// Demonstrates the full pipeline: input → parse → plan → reason → generate.
//
// Memory: Creates a system arena and pool for the runtime.
// All major subsystems are initialized at startup.
//
// Philosophy: Purely symbolic. No neural networks, no LLMs, no transformers.
// Every response is generated through template matching, grammar rules,
// knowledge lookup, and symbolic reasoning.

#include "cos/core.h"
#include "cos/allocator.h"
#include "cos/arena.h"
#include "cos/pool.h"
#include "cos/tools.h"
#include "cos/template_matcher.h"
#include "cos/string_view.h"
#include "cos/parser.h"
#include "cos/planner.h"
#include "cos/reasoning.h"
#include "cos/knowledge.h"
#include "cos/language.h"
#include "cos/conversation.h"
#include "cos/debug.h"
#include "cos/tools.h"
#include "cos/plugins.h"
#include "cos/string_view.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>

// ── Built-in tool registration ───────────────────────────────────────────
extern cos_status_t cos_register_builtin_tools(cos_tool_registry_t* reg);

// ── Global Runtime State ─────────────────────────────────────────────────
typedef struct cos_runtime_s {
    cos_allocator_t*      system_alloc;    // Bootstrap (malloc)
    cos_allocator_t*      runtime_arena;   // Long-lived allocations
    cos_allocator_t*      scratch_arena;   // Per-turn scratch (reset each turn)
    cos_allocator_t*      node_pool;       // Pool for graph/semantic nodes
    cos_string_table_t*   string_table;
    cos_knowledge_base_t* knowledge;
    cos_knowledge_base_t* working_memory;
    cos_conversation_t*   conversation;
    cos_debug_t*          debugger;
    cos_tool_registry_t*  tool_registry;
    cos_plugin_registry_t* plugin_registry;
    cos_template_db_t*     templates;
} cos_runtime_t;

// ── Initialize Runtime ───────────────────────────────────────────────────
static cos_status_t runtime_init(cos_runtime_t* rt) {
    memset(rt, 0, sizeof(cos_runtime_t));

    // Bootstrap allocator
    rt->system_alloc = cos_sys_allocator();

    // Runtime arena (never reset — holds persistent data)
    rt->runtime_arena = cos_arena_create(NULL, rt->system_alloc);
    if (!rt->runtime_arena) return COS_ERROR_NOMEM;

    // Scratch arena (reset per conversation turn)
    cos_arena_config_t scratch_config = {
        .block_size = 64 * 1024,  // 64KB scratch space
    };
    rt->scratch_arena = cos_arena_create(&scratch_config, rt->system_alloc);
    if (!rt->scratch_arena) return COS_ERROR_NOMEM;

    // Node pool (for graph nodes, AST nodes, etc.)
    cos_pool_config_t pool_config = {
        .object_size    = sizeof(cos_semantic_node_t),
        .object_align   = 16,
        .initial_capacity = 4096,
        .grow_count     = 4096,
    };
    rt->node_pool = cos_pool_create(&pool_config, rt->system_alloc);
    if (!rt->node_pool) return COS_ERROR_NOMEM;

    // String table
    rt->string_table = cos_string_table_create(rt->system_alloc);
    if (!rt->string_table) return COS_ERROR_NOMEM;

    // Knowledge bases
    rt->knowledge = cos_knowledge_create(rt->system_alloc);
    if (!rt->knowledge) return COS_ERROR_NOMEM;

    rt->working_memory = cos_knowledge_create(rt->system_alloc);
    if (!rt->working_memory) return COS_ERROR_NOMEM;

    // Conversation engine
    cos_conversation_config_t conv_config;
    memset(&conv_config, 0, sizeof(conv_config));
    conv_config.allocator      = rt->runtime_arena;
    conv_config.scratch_arena  = rt->scratch_arena;
    conv_config.string_table   = rt->string_table;
    conv_config.knowledge      = rt->knowledge;
    conv_config.working_memory = rt->working_memory;

    rt->conversation = cos_conversation_create(&conv_config);
    if (!rt->conversation) return COS_ERROR_NOMEM;

    // Debugger
    cos_debug_config_t debug_config;
    debug_config.allocator      = rt->system_alloc;
    debug_config.max_events     = 4096;
    debug_config.enable_profiling = true;
    debug_config.enable_allocs    = true;
    rt->debugger = cos_debug_create(&debug_config);

    // Tool registry
    rt->tool_registry = cos_tool_registry_create(rt->system_alloc);
    if (rt->tool_registry) {
        cos_register_builtin_tools(rt->tool_registry);
        cos_register_math_tool(rt->tool_registry);
    }

    // Plugin registry
    rt->plugin_registry = cos_plugin_registry_create(rt->system_alloc);

    // Template matcher (load from default path)
    rt->templates = cos_template_db_create(rt->system_alloc);
    int tmpl_count = cos_template_db_load(rt->templates, "cos_templates.txt");
    if (tmpl_count > 0) {
        printf("  Loaded %d response templates\n", tmpl_count);
    }

    return COS_OK;
}

// ── Cleanup Runtime ──────────────────────────────────────────────────────
static void runtime_destroy(cos_runtime_t* rt) {
    if (rt->templates)        cos_template_db_destroy(rt->templates);
    if (rt->plugin_registry)  cos_plugin_registry_destroy(rt->plugin_registry);
    if (rt->tool_registry)    cos_tool_registry_destroy(rt->tool_registry);
    if (rt->debugger)         cos_debug_destroy(rt->debugger);
    if (rt->conversation)     cos_conversation_destroy(rt->conversation);
    if (rt->working_memory)   cos_knowledge_destroy(rt->working_memory);
    if (rt->knowledge)        cos_knowledge_destroy(rt->knowledge);
    if (rt->string_table)     cos_string_table_destroy(rt->string_table);
    if (rt->node_pool)        cos_pool_destroy(rt->node_pool);
    if (rt->scratch_arena)    cos_allocator_destroy(rt->scratch_arena);
    if (rt->runtime_arena)    cos_allocator_destroy(rt->runtime_arena);
    // system_alloc is a singleton -- no need to destroy
}

// ── Interactive REPL ─────────────────────────────────────────────────────
static void run_repl(cos_runtime_t* rt) {
    printf("\n╔══════════════════════════════════════════╗\n");
    printf("║   COS v%d.%d.%d - Conversation OS        ║\n",
           COS_VERSION_MAJOR, COS_VERSION_MINOR, COS_VERSION_PATCH);
    printf("║   Type '/help' for commands, '/quit' to exit ║\n");
    printf("╚══════════════════════════════════════════╝\n\n");

    char buffer[4096];

    while (1) {
        printf("> ");
        fflush(stdout);

        if (!fgets(buffer, sizeof(buffer), stdin)) break;

        // Remove trailing newline
        size_t len = strlen(buffer);
        while (len > 0 && (buffer[len-1] == '\n' || buffer[len-1] == '\r')) {
            buffer[--len] = '\0';
        }

        if (len == 0) continue;

        // Check for commands
        if (buffer[0] == '/') {
            if (strcmp(buffer, "/quit") == 0 || strcmp(buffer, "/exit") == 0) {
                printf("Goodbye!\n");
                break;
            } else if (strcmp(buffer, "/help") == 0) {
                printf("Commands:\n");
                printf("  /help      - Show this help\n");
                printf("  /status    - Show system status\n");
                printf("  /memory    - Show memory usage\n");
                printf("  /debug     - Show debug events\n");
                printf("  /quit      - Exit COS\n");
                printf("  /tools     - List available tools\n");
                continue;
            } else if (strcmp(buffer, "/status") == 0) {
                printf("COS v%d.%d.%d\n", COS_VERSION_MAJOR, COS_VERSION_MINOR, COS_VERSION_PATCH);
                printf("Turns: %zu\n", cos_conversation_turn_count(rt->conversation));
                printf("Strings interned: %zu\n", cos_string_table_count(rt->string_table));
                printf("Knowledge facts: %zu\n", cos_knowledge_fact_count(rt->knowledge));
                printf("Tools registered: %zu\n", cos_tool_count(rt->tool_registry));
                continue;
            } else if (strcmp(buffer, "/memory") == 0) {
                printf("String table:    %zu bytes\n", cos_string_table_memory_used(rt->string_table));
                printf("Conversation:    %zu bytes\n", cos_conversation_memory_used(rt->conversation));
                printf("Knowledge base:  %zu bytes\n", cos_knowledge_memory_used(rt->knowledge));
                continue;
            } else if (strcmp(buffer, "/debug") == 0) {
                printf("Debug events: %zu\n", cos_debug_event_count(rt->debugger));
                cos_debug_print_events(rt->debugger, stdout, 20);
                continue;
            } else if (strcmp(buffer, "/tools") == 0) {
                size_t count = cos_tool_count(rt->tool_registry);
                printf("Registered tools (%zu):\n", count);
                for (size_t i = 0; i < count; i++) {
                    const cos_tool_t* tool = cos_tool_get(rt->tool_registry, i);
                    if (tool) {
                        printf("  - %s: %s\n", tool->name, tool->description);
                    }
                }
                continue;
            } else {
                printf("Unknown command: %s\n", buffer);
                continue;
            }
        }

        // Process input through the symbolic pipeline
        bool handled = false;

        // 1. Check if input matches a registered tool name (single word = tool call)
        const cos_tool_t* tool = cos_tool_find(rt->tool_registry, buffer);
        if (tool) {
            char tool_buf[4096];
            size_t tool_written = 0;
            if (cos_tool_execute(rt->tool_registry, buffer, "", 0,
                                  tool_buf, sizeof(tool_buf), &tool_written) == COS_OK) {
                tool_buf[tool_written < sizeof(tool_buf) ? tool_written : sizeof(tool_buf)-1] = '\0';
                printf("%s", tool_buf);
                if (tool_written > 0 && tool_buf[tool_written-1] != '\n') printf("\n");
                handled = true;
            }
        }

        // 2. Try math tool for arithmetic expressions (before template matching)
        if (!handled) {
            bool has_math = false;
            for (size_t i = 0; i < len && !has_math; i++) {
                if (buffer[i] == '+' || buffer[i] == '-' || buffer[i] == '*' ||
                    buffer[i] == '/' || buffer[i] == '^') {
                    has_math = true;
                }
            }
            if (has_math) {
                char math_buf[4096];
                size_t math_written = 0;
                const cos_tool_t* math_tool = cos_tool_find(rt->tool_registry, "math");
                if (math_tool) {
                    math_tool->execute(math_tool, buffer, len,
                        math_buf, sizeof(math_buf), &math_written);
                    math_buf[math_written < sizeof(math_buf) ? math_written : sizeof(math_buf)-1] = '\0';
                    printf("%s\n", math_buf);
                    handled = true;
                }
            }
        }

        // 3. Try template matching for questions
        if (!handled && rt->templates) {
            bool is_question = false;
            const char* qwords[] = {"what", "why", "how", "when", "where", "who", "whom",
                "whose", "which", "explain", "describe", "define", "tell me",
                "what is", "what are", "what does", "what do", "how does",
                "how do", "why is", "why does", "why do", "can you",
                "could you", "would you", "do you", "does"};
            char buf_lower[256];
            size_t bl = len < 255 ? len : 255;
            for (size_t i = 0; i < bl; i++) buf_lower[i] = (char)tolower((unsigned char)buffer[i]);
            buf_lower[bl] = '\0';

            for (size_t q = 0; q < sizeof(qwords)/sizeof(qwords[0]) && !is_question; q++) {
                if (strstr(buf_lower, qwords[q])) is_question = true;
            }

            if (is_question) {
                const template_entry_t* tmpl = NULL;
                float score = cos_template_db_match(rt->templates, buffer, len, &tmpl);
                if (score > 0.20f && tmpl) {
                    printf("%s\n", tmpl->answer);
                    handled = true;
                }
            }
        }

        // 4. Process through conversation system
        if (!handled) {
            cos_string_view_t input = cos_sv(buffer, len);
            const char* out_response = NULL;
            size_t out_length = 0;

            cos_status_t status = cos_conversation_process(
                rt->conversation, input, &out_response, &out_length);

            if (status == COS_OK && out_response && out_length > 3) {
                printf("%.*s\n", (int)out_length, out_response);
                handled = true;
            }
        }

        // 5. Final fallback
        if (!handled) {
            printf("I understand your request. Could you provide more details?\n");
        }

        // Log to debugger
        cos_debug_log_fmt(rt->debugger, COS_DEBUG_PARSE, "main",
                          "Turn processed");

        // Reset scratch arena for next turn
        cos_arena_reset(rt->scratch_arena);
    }
}

// ── Main ─────────────────────────────────────────────────────────────────
int main(int argc, char** argv) {
    (void)argc;
    (void)argv;

    cos_runtime_t runtime;
    cos_status_t status = runtime_init(&runtime);

    if (status != COS_OK) {
        fprintf(stderr, "Failed to initialize COS runtime: %d\n", (int)status);
        return 1;
    }

    run_repl(&runtime);

    runtime_destroy(&runtime);
    return 0;
}
