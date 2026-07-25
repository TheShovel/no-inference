// test_parser.c — Parser tests

#include "cos/core.h"
#include "cos/allocator.h"
#include "cos/arena.h"
#include "cos/string_intern.h"
#include "cos/string_view.h"
#include "cos/parser.h"
#include "cos/semantic.h"
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

static void test_parser_basic(void) {
    printf("[Parser Basic]\n");

    cos_allocator_t* backing = cos_sys_allocator();
    cos_string_table_t* table = cos_string_table_create(backing);

    cos_parser_config_t config;
    config.string_table = table;
    config.allocator    = backing;
    config.scratch      = NULL;

    cos_parser_t* parser = cos_parser_create(&config);
    TEST("parser created", parser != NULL);

    // Parse a simple sentence
    cos_semantic_graph_t* graph = NULL;
    cos_status_t status = cos_parser_parse(parser, cos_sv_cstr("I want pizza"), &graph);
    TEST("parse OK", status == COS_OK);
    TEST("graph created", graph != NULL);

    if (graph) {
        // Verify root exists
        cos_graph_node_id_t root = cos_semantic_root(graph);
        TEST("has root", root != COS_NODE_ID_NULL);
        cos_semantic_destroy(graph);
    }

    cos_parser_destroy(parser);
    cos_string_table_destroy(table);
}

int main(void) {
    printf("═══ Parser Tests ═══\n\n");
    test_parser_basic();

    printf("\nResults: %d passed, %d failed\n", tests_passed, tests_failed);
    return tests_failed > 0 ? 1 : 0;
}
