// string_view.h — String View Utilities
//
// Design: A string_view is a (pointer, length) pair.
// It owns nothing — it is a borrow. All string operations in COS
// use string views to avoid allocations and copies.
//
// Memory: 16 bytes on 64-bit. No allocations.

#ifndef COS_STRING_VIEW_H
#define COS_STRING_VIEW_H

#include "cos/core.h"
#include <stddef.h>
#include <string.h>

#ifdef __cplusplus
extern "C" {
#endif

// ── Constructors ─────────────────────────────────────────────────────────
static inline cos_string_view_t cos_sv(const char* data, size_t length) {
    cos_string_view_t sv = { data, length };
    return sv;
}

static inline cos_string_view_t cos_sv_cstr(const char* cstr) {
    cos_string_view_t sv = { cstr, cstr ? strlen(cstr) : 0 };
    return sv;
}

static inline cos_string_view_t cos_sv_copy(const cos_string_view_t* sv) {
    return *sv;  // trivially copyable
}

// ── Accessors ───────────────────────────────────────────────────────────
static inline const char* cos_sv_data(const cos_string_view_t sv) { return sv.data; }
static inline size_t      cos_sv_length(const cos_string_view_t sv) { return sv.length; }
static inline bool        cos_sv_empty(const cos_string_view_t sv)  { return sv.length == 0; }

// ── Comparison ──────────────────────────────────────────────────────────
static inline bool cos_sv_eq(cos_string_view_t a, cos_string_view_t b) {
    return a.length == b.length && (a.data == b.data || memcmp(a.data, b.data, a.length) == 0);
}

static inline int cos_sv_cmp(cos_string_view_t a, cos_string_view_t b) {
    size_t min_len = a.length < b.length ? a.length : b.length;
    int cmp = min_len > 0 ? memcmp(a.data, b.data, min_len) : 0;
    if (cmp != 0) return cmp;
    if (a.length < b.length) return -1;
    if (a.length > b.length) return  1;
    return 0;
}

// ── Hashing ─────────────────────────────────────────────────────────────
// FNV-1a hash for string views. Simple, fast, good distribution.
static inline cos_hash_t cos_sv_hash(cos_string_view_t sv) {
    cos_hash_t hash = 14695981039346656037ULL;
    for (size_t i = 0; i < sv.length; i++) {
        hash ^= (unsigned char)sv.data[i];
        hash *= 1099511628211ULL;
    }
    return hash;
}

// ── Substrings / Splitting ──────────────────────────────────────────────
static inline cos_string_view_t cos_sv_substr(cos_string_view_t sv, size_t start, size_t length) {
    if (start > sv.length) start = sv.length;
    if (length > sv.length - start) length = sv.length - start;
    cos_string_view_t result = { sv.data + start, length };
    return result;
}

static inline cos_string_view_t cos_sv_trim_left(cos_string_view_t sv) {
    while (sv.length > 0 && (sv.data[0] == ' ' || sv.data[0] == '\t' || sv.data[0] == '\n' || sv.data[0] == '\r')) {
        sv.data++;
        sv.length--;
    }
    return sv;
}

static inline cos_string_view_t cos_sv_trim_right(cos_string_view_t sv) {
    while (sv.length > 0 && (sv.data[sv.length-1] == ' ' || sv.data[sv.length-1] == '\t' || sv.data[sv.length-1] == '\n' || sv.data[sv.length-1] == '\r')) {
        sv.length--;
    }
    return sv;
}

static inline cos_string_view_t cos_sv_trim(cos_string_view_t sv) {
    return cos_sv_trim_right(cos_sv_trim_left(sv));
}

// Split at first occurrence of `delimiter`.
// Returns the part before delimiter in `before`, part after in `after`.
// Returns true if delimiter was found.
static inline bool cos_sv_split(cos_string_view_t sv, char delimiter, cos_string_view_t* before, cos_string_view_t* after) {
    for (size_t i = 0; i < sv.length; i++) {
        if (sv.data[i] == delimiter) {
            if (before) *before = cos_sv(sv.data, i);
            if (after)  *after  = cos_sv(sv.data + i + 1, sv.length - i - 1);
            return true;
        }
    }
    if (before) *before = sv;
    if (after)  *after  = cos_sv(NULL, 0);
    return false;
}

#ifdef __cplusplus
}
#endif

#endif // COS_STRING_VIEW_H
