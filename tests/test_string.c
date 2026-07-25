// test_string.c — String interning tests

#include "cos/core.h"
#include "cos/allocator.h"
#include "cos/string_intern.h"
#include "cos/string_view.h"
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

static void test_string_intern(void) {
    printf("[String Interning]\n");

    cos_allocator_t* backing = cos_sys_allocator();
    cos_string_table_t* table = cos_string_table_create(backing);
    TEST("table created", table != NULL);

    // Intern strings
    cos_string_id_t id1 = cos_string_intern_cstr(table, "hello");
    cos_string_id_t id2 = cos_string_intern_cstr(table, "world");
    cos_string_id_t id3 = cos_string_intern_cstr(table, "hello");  // duplicate

    TEST("unique IDs", id1 != id2);
    TEST("duplicate same ID", id1 == id3);

    // Lookup
    cos_string_view_t sv1 = cos_string_lookup(table, id1);
    TEST("lookup correct", sv1.length == 5 && memcmp(sv1.data, "hello", 5) == 0);

    // Find
    cos_string_id_t found = cos_string_find(table, cos_sv_cstr("hello"));
    TEST("find exists", found == id1);

    cos_string_id_t not_found = cos_string_find(table, cos_sv_cstr("nonexistent"));
    TEST("find missing", not_found == COS_STRING_ID_NULL);

    // Intern empty string
    cos_string_id_t empty = cos_string_intern(table, cos_sv("", 0));
    TEST("empty string", empty == COS_STRING_ID_NULL);

    // Stats
    TEST("count", cos_string_table_count(table) >= 2);
    TEST("memory > 0", cos_string_table_memory_used(table) > 0);

    cos_string_table_destroy(table);
}

int main(void) {
    printf("═══ String Tests ═══\n\n");
    test_string_intern();

    printf("\nResults: %d passed, %d failed\n", tests_passed, tests_failed);
    return tests_failed > 0 ? 1 : 0;
}
