// test_core.c — Core type and utility tests

#include "cos/core.h"
#include "cos/string_view.h"
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

static void test_string_view(void) {
    printf("[String View]\n");

    const char* text = "hello world";
    cos_string_view_t sv = cos_sv_cstr(text);
    TEST("sv from cstr", sv.data == text && sv.length == 11);

    cos_string_view_t empty = cos_sv(NULL, 0);
    TEST("empty sv", cos_sv_empty(empty));

    TEST("sv eq", cos_sv_eq(cos_sv_cstr("abc"), cos_sv_cstr("abc")));
    TEST("sv neq", !cos_sv_eq(cos_sv_cstr("abc"), cos_sv_cstr("def")));

    TEST("sv cmp eq", cos_sv_cmp(cos_sv_cstr("abc"), cos_sv_cstr("abc")) == 0);
    TEST("sv cmp lt", cos_sv_cmp(cos_sv_cstr("abc"), cos_sv_cstr("def")) < 0);
    TEST("sv cmp gt", cos_sv_cmp(cos_sv_cstr("def"), cos_sv_cstr("abc")) > 0);

    // Substring
    cos_string_view_t sub = cos_sv_substr(sv, 0, 5);
    TEST("substr", sub.length == 5 && memcmp(sub.data, "hello", 5) == 0);

    // Trim
    cos_string_view_t spaced = cos_sv_cstr("  hello  ");
    cos_string_view_t trimmed = cos_sv_trim(spaced);
    TEST("trim", trimmed.length == 5 && memcmp(trimmed.data, "hello", 5) == 0);

    // Split
    cos_string_view_t before, after;
    cos_string_view_t csv = cos_sv_cstr("a,b,c");
    bool found = cos_sv_split(csv, ',', &before, &after);
    TEST("split found", found);
    TEST("split before", before.length == 1 && before.data[0] == 'a');
    TEST("split after", after.length == 3 && after.data[0] == 'b');

    // FNV-1a hash
    cos_hash_t h1 = cos_sv_hash(cos_sv_cstr("hello"));
    cos_hash_t h2 = cos_sv_hash(cos_sv_cstr("hello"));
    cos_hash_t h3 = cos_sv_hash(cos_sv_cstr("world"));
    TEST("hash consistent", h1 == h2);
    TEST("hash different", h1 != h3);
}

static void test_status_codes(void) {
    printf("[Status Codes]\n");

    TEST("OK string", strcmp(cos_status_string(COS_OK), "OK") == 0);
    TEST("error string", strcmp(cos_status_string(COS_ERROR_NOMEM), "Out of memory") == 0);
    TEST("not impl string", strcmp(cos_status_string(COS_ERROR_NOT_IMPL), "Not implemented") == 0);
}

int main(void) {
    printf("═══ Core Tests ═══\n\n");
    test_string_view();
    test_status_codes();

    printf("\nResults: %d passed, %d failed\n", tests_passed, tests_failed);
    return tests_failed > 0 ? 1 : 0;
}
