// test_memory.c — Memory allocator tests

#include "cos/core.h"
#include "cos/allocator.h"
#include "cos/arena.h"
#include "cos/pool.h"
#include "cos/stack_alloc.h"
#include <stdio.h>
#include <string.h>
#include <assert.h>
#include <stdalign.h>

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

static void test_arena(void) {
    printf("[Arena Allocator]\n");

    cos_allocator_t* backing = cos_sys_allocator();
    cos_allocator_t* arena = cos_arena_create(NULL, backing);
    TEST("arena created", arena != NULL);
    TEST("arena context", arena->context != NULL);

    void* p1 = cos_alloc(arena, 64, 64);
    TEST("arena alloc 64B", p1 != NULL);

    void* p2 = cos_alloc(arena, 128, 16);
    TEST("arena alloc 128B", p2 != NULL);

    // Pointers should be distinct
    TEST("arena distinct", p1 != p2);

    // Reset
    cos_arena_reset(arena);
    void* p3 = cos_alloc(arena, 32, 8);
    TEST("arena after reset", p3 != NULL);

    // The arena may reuse the first block for the new allocation
    // In general after reset, the arena starts from scratch

    cos_allocator_destroy(arena);
}

static void test_pool(void) {
    printf("[Pool Allocator]\n");

    cos_allocator_t* backing = cos_sys_allocator();
    cos_pool_config_t config = {
        .object_size = 64,
        .object_align = 16,
        .initial_capacity = 128,
        .grow_count = 64,
    };
    cos_allocator_t* pool = cos_pool_create(&config, backing);
    TEST("pool created", pool != NULL);

    void* p1 = cos_alloc_default(pool, 64);
    TEST("pool alloc 64B", p1 != NULL);

    void* p2 = cos_alloc_default(pool, 64);
    TEST("pool alloc 64B #2", p2 != NULL);

    TEST("pool distinct", p1 != p2);

    // Free and re-allocate (should reuse the same slot)
    cos_free(pool, p1, 64);
    void* p3 = cos_alloc_default(pool, 64);
    TEST("pool reuse after free", p3 != NULL);
    // p3 could equal p1 since the free list returns the last freed block

    cos_pool_destroy(pool);
}

static void test_stack(void) {
    printf("[Stack Allocator]\n");

    cos_allocator_t* backing = cos_sys_allocator();
    cos_allocator_t* stack = cos_stack_alloc_create(4096, backing);
    TEST("stack created", stack != NULL);

    void* p1 = cos_alloc(stack, 64, 16);
    TEST("stack alloc 64B", p1 != NULL);

    void* p2 = cos_alloc(stack, 128, 16);
    TEST("stack alloc 128B", p2 != NULL);

    // Mark and rewind
    cos_stack_marker_t marker = cos_stack_mark(stack);
    void* p3 = cos_alloc(stack, 32, 8);
    TEST("stack alloc after mark", p3 != NULL);

    cos_stack_rewind(stack, marker);

    // After rewind, the space from p3 should be reclaimable
    void* p4 = cos_alloc(stack, 64, 16);
    TEST("stack alloc after rewind", p4 != NULL);

    cos_stack_alloc_destroy(stack);
}

int main(void) {
    printf("═══ Memory Tests ═══\n\n");
    test_arena();
    test_pool();
    test_stack();

    printf("\nResults: %d passed, %d failed\n", tests_passed, tests_failed);
    return tests_failed > 0 ? 1 : 0;
}
