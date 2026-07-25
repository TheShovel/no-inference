// test_conversation.c — Conversation engine tests

#include "cos/core.h"
#include "cos/allocator.h"
#include "cos/arena.h"
#include "cos/string_intern.h"
#include "cos/string_view.h"
#include "cos/knowledge.h"
#include "cos/conversation.h"
#include <stdio.h>
#include <string.h>

static int tests_passed = 0;
static int tests_failed = 0;

#define TEST(name, expr) do { \
    if (!(expr)) { \
        printf("  FAIL: %s\n", name); \
        tests_failed++; \
    } else { \
        printf("  PASS: %s\n", name); \
        tests_passed++; \
    } \
} while(0)

static void test_conversation_basic(void) {
    printf("[Conversation Basic]\n");

    cos_allocator_t* backing = cos_sys_allocator();
    cos_string_table_t* table = cos_string_table_create(backing);
    cos_knowledge_base_t* knowledge = cos_knowledge_create(backing);

    cos_arena_config_t scratch_config = {
        .block_size = 64 * 1024,
    };
    cos_allocator_t* scratch = cos_arena_create(&scratch_config, backing);

    cos_conversation_config_t conv_config;
    memset(&conv_config, 0, sizeof(conv_config));
    conv_config.allocator      = backing;
    conv_config.scratch_arena  = scratch;
    conv_config.string_table   = table;
    conv_config.knowledge      = knowledge;
    conv_config.working_memory = knowledge;

    cos_conversation_t* conv = cos_conversation_create(&conv_config);
    TEST("conversation created", conv != NULL);

    // Process a turn
    const char* response = NULL;
    size_t response_length = 0;
    cos_status_t status = cos_conversation_process(
        conv, cos_sv_cstr("Hello, I like Python"), &response, &response_length);

    TEST("process OK", status == COS_OK);
    TEST("has response", response != NULL && response_length > 0);
    printf("  Response: %s\n", response ? response : "(null)");

    // Process another turn
    status = cos_conversation_process(
        conv, cos_sv_cstr("What is my favorite programming language?"), &response, &response_length);

    TEST("second turn OK", status == COS_OK);
    TEST("turn count", cos_conversation_turn_count(conv) == 2);

    cos_conversation_destroy(conv);
    cos_allocator_destroy(scratch);
    cos_knowledge_destroy(knowledge);
    cos_string_table_destroy(table);
}

int main(void) {
    printf("═══ Conversation Tests ═══\n\n");
    test_conversation_basic();

    printf("\nResults: %d passed, %d failed\n", tests_passed, tests_failed);
    return tests_failed > 0 ? 1 : 0;
}
