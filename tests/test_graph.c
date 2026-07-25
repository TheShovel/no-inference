// test_graph.c — Graph engine tests

#include "cos/core.h"
#include "cos/allocator.h"
#include "cos/graph.h"
#include <stdio.h>
#include <string.h>
#include <assert.h>

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

static void test_graph_basic(void) {
    printf("[Graph Basic]\n");

    cos_allocator_t* backing = cos_sys_allocator();
    cos_graph_t* g = cos_graph_create(COS_GRAPH_DIRECTED, backing);
    TEST("graph created", g != NULL);

    // Add nodes
    cos_graph_node_id_t n1 = cos_graph_add_node(g, NULL, 0);
    cos_graph_node_id_t n2 = cos_graph_add_node(g, NULL, 0);
    cos_graph_node_id_t n3 = cos_graph_add_node(g, NULL, 0);

    TEST("nodes added", n1 != COS_NODE_ID_NULL);
    TEST("count", cos_graph_node_count(g) == 3);
    TEST("has node", cos_graph_has_node(g, n1));
    TEST("!has node", !cos_graph_has_node(g, 999));

    // Add edges
    cos_graph_edge_id_t e1 = cos_graph_add_edge(g, n1, n2, 1.0f);
    cos_graph_add_edge(g, n2, n3, 2.0f);

    TEST("edges added", e1 != COS_EDGE_ID_NULL);

    // Remove node
    cos_status_t s = cos_graph_remove_node(g, n3);
    TEST("remove node", s == COS_OK);
    TEST("!has node after remove", !cos_graph_has_node(g, n3));

    cos_graph_destroy(g);
}

static void test_graph_traversal(void) {
    printf("[Graph Traversal]\n");

    cos_allocator_t* backing = cos_sys_allocator();
    cos_graph_t* g = cos_graph_create(COS_GRAPH_DIRECTED, backing);

    cos_graph_node_id_t nodes[10];
    for (int i = 0; i < 10; i++) {
        nodes[i] = cos_graph_add_node(g, NULL, 0);
    }

    // Linear chain: 0→1→2→...→9
    for (int i = 0; i < 9; i++) {
        cos_graph_add_edge(g, nodes[i], nodes[i+1], 1.0f);
    }

    // BFS from node 0
    cos_graph_node_id_t visited[10];
    size_t count = cos_graph_bfs(g, nodes[0], visited, 10);
    TEST("BFS count", count > 0);

    cos_graph_destroy(g);
}

int main(void) {
    printf("═══ Graph Tests ═══\n\n");
    test_graph_basic();
    test_graph_traversal();

    printf("\nResults: %d passed, %d failed\n", tests_passed, tests_failed);
    return tests_failed > 0 ? 1 : 0;
}
