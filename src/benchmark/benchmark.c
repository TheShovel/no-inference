// benchmark.c — Performance Benchmarks
//
// Design: Microbenchmarks for each subsystem.
// Measures allocation throughput, parse speed, graph traversal, etc.
//
// All benchmarks print results to stdout in a machine-readable format.

#define _POSIX_C_SOURCE 199309L

#include "cos/core.h"
#include "cos/allocator.h"
#include "cos/arena.h"
#include "cos/pool.h"
#include "cos/stack_alloc.h"
#include "cos/string_intern.h"
#include "cos/string_view.h"
#include "cos/graph.h"
#include "cos/semantic.h"
#include "cos/parser.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

// ── Timing Helper ────────────────────────────────────────────────────────
#if defined(_WIN32)
#include <windows.h>
static double now_seconds(void) {
    LARGE_INTEGER freq, counter;
    QueryPerformanceFrequency(&freq);
    QueryPerformanceCounter(&counter);
    return (double)counter.QuadPart / (double)freq.QuadPart;
}
#elif defined(__linux__) || defined(__unix__)
#include <time.h>
static double now_seconds(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
}
#else
#include <time.h>
static double now_seconds(void) {
    return (double)time(NULL);
}
#endif

// ── Benchmark Helpers ────────────────────────────────────────────────────

#define BENCH(name, iterations, block) \
    do { \
        double start = now_seconds(); \
        for (size_t _i = 0; _i < (size_t)(iterations); _i++) { block; } \
        double elapsed = now_seconds() - start; \
        printf("  %-30s %8zu iterations  %8.3f s  %8.1f ns/iter\n", \
               name, (size_t)(iterations), elapsed, \
               elapsed * 1e9 / (double)(iterations)); \
    } while(0)

// ── Arena Allocator Benchmark ────────────────────────────────────────────
static void bench_arena(size_t iterations) {
    printf("[Arena Allocator]\n");

    cos_allocator_t* backing = cos_sys_allocator();
    cos_allocator_t* arena = cos_arena_create(NULL, backing);

    BENCH("arena_alloc 64B", iterations, {
        void* p = cos_alloc(arena, 64, 64);
        (void)p;
    });

    cos_arena_reset(arena);

    BENCH("arena_alloc 256B", iterations, {
        void* p = cos_alloc(arena, 256, 16);
        (void)p;
    });

    cos_arena_reset(arena);

    BENCH("arena_alloc 1KB", iterations, {
        void* p = cos_alloc(arena, 1024, 16);
        (void)p;
    });

    cos_arena_reset(arena);

    // Mixed sizes
    BENCH("arena_alloc mixed", iterations, {
        void* p1 = cos_alloc(arena, 32, 8);
        void* p2 = cos_alloc(arena, 128, 16);
        void* p3 = cos_alloc(arena, 512, 32);
        (void)p1; (void)p2; (void)p3;
    });

    cos_allocator_destroy(arena);
}

// ── Pool Allocator Benchmark ─────────────────────────────────────────────
static void bench_pool(size_t iterations) {
    printf("[Pool Allocator]\n");

    cos_allocator_t* backing = cos_sys_allocator();
    cos_pool_config_t config = {
        .object_size = 64,
        .object_align = 16,
        .initial_capacity = 1024,
        .grow_count = 1024,
    };
    cos_allocator_t* pool = cos_pool_create(&config, backing);

    BENCH("pool_alloc 64B", iterations, {
        void* p = cos_alloc_default(pool, 64);
        cos_free(pool, p, 64);
    });

    // Allocate many at once
    void** ptrs = (void**)malloc(iterations * sizeof(void*));
    if (ptrs) {
        double start = now_seconds();
        for (size_t i = 0; i < iterations; i++) {
            ptrs[i] = cos_alloc_default(pool, 64);
        }
        for (size_t i = 0; i < iterations; i++) {
            cos_free(pool, ptrs[i], 64);
        }
        double elapsed = now_seconds() - start;
        printf("  %-30s %8zu iterations  %8.3f s  %8.1f ns/iter\n",
               "pool_alloc/free 64B", iterations, elapsed,
               elapsed * 1e9 / (double)iterations);
        free(ptrs);
    }

    cos_pool_destroy(pool);
}

// ── String Interning Benchmark ───────────────────────────────────────────
static void bench_string_intern(size_t iterations) {
    printf("[String Interning]\n");

    cos_allocator_t* backing = cos_sys_allocator();
    cos_string_table_t* table = cos_string_table_create(backing);

    // Pre-create some test strings
    const char* test_strings[] = {
        "hello", "world", "this", "is", "a", "test",
        "conversation", "operating", "system", "cos",
        "the", "quick", "brown", "fox", "jumps", "over",
        "lazy", "dog", "pizza", "tomorrow", "python",
        "minecraft", "rx6600", "lightweight", "runtime"
    };
    size_t num_strings = sizeof(test_strings) / sizeof(test_strings[0]);

    BENCH("intern unique", iterations, {
        for (size_t i = 0; i < num_strings; i++) {
            cos_string_intern_cstr(table, test_strings[i]);
        }
    });

    // Intern duplicates (should hit cache)
    BENCH("intern duplicate", iterations, {
        for (size_t i = 0; i < num_strings; i++) {
            cos_string_intern_cstr(table, test_strings[i]);
        }
    });

    BENCH("lookup", iterations, {
        for (size_t i = 0; i < num_strings; i++) {
            cos_string_view_t sv = cos_sv_cstr(test_strings[i]);
            cos_string_find(table, sv);
        }
    });

    printf("  Strings interned: %zu\n", cos_string_table_count(table));
    printf("  Memory used:      %zu bytes\n", cos_string_table_memory_used(table));

    cos_string_table_destroy(table);
}

// ── Graph Benchmark ──────────────────────────────────────────────────────
static void bench_graph(size_t iterations) {
    printf("[Graph Engine]\n");

    cos_allocator_t* backing = cos_sys_allocator();

    BENCH("add_node", iterations, {
        cos_graph_t* g = cos_graph_create(COS_GRAPH_DIRECTED, backing);
        for (size_t i = 0; i < 1000; i++) {
            cos_graph_add_node(g, NULL, 0);
        }
        cos_graph_destroy(g);
    });

    BENCH("add_edge linear", iterations / 10, {
        cos_graph_t* g = cos_graph_create(COS_GRAPH_DIRECTED, backing);
        cos_graph_node_id_t prev = COS_NODE_ID_NULL;
        for (size_t i = 0; i < 100; i++) {
            cos_graph_node_id_t n = cos_graph_add_node(g, NULL, 0);
            if (prev != COS_NODE_ID_NULL) {
                cos_graph_add_edge(g, prev, n, 1.0f);
            }
            prev = n;
        }
        cos_graph_destroy(g);
    });

    printf("\n");
}

// ── Main ─────────────────────────────────────────────────────────────────
int main(void) {
    printf("═══ COS Performance Benchmarks ═══\n\n");

    size_t quick = 10000;
    size_t moderate = 100000;

    bench_arena(quick);
    printf("\n");
    bench_pool(quick);
    printf("\n");
    bench_string_intern(quick);
    printf("\n");
    bench_graph(moderate);

    printf("═══ Benchmarks Complete ═══\n");
    return 0;
}
