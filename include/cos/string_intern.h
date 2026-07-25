// string_intern.h — String Interning System
//
// Design: A hash table mapping string views to unique IDs.
// Each unique string is stored once in a contiguous buffer.
// All subsystems reference strings via cos_string_id_t (uint32_t).
//
// Memory: Strings stored contiguously — excellent cache locality.
// Zero duplicates. IDs are 4 bytes vs 16 bytes for string_view.
//
// Performance: O(1) average lookup/insert. Batch operations for
// bulk loading.

#ifndef COS_STRING_INTERN_H
#define COS_STRING_INTERN_H

#include "cos/core.h"
#include "cos/allocator.h"
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

// ── Opaque Table ─────────────────────────────────────────────────────────
typedef struct cos_string_table_s cos_string_table_t;

// ── Lifecycle ────────────────────────────────────────────────────────────
cos_string_table_t* cos_string_table_create(cos_allocator_t* alloc);
void                cos_string_table_destroy(cos_string_table_t* table);
void                cos_string_table_reset(cos_string_table_t* table);

// ── Core Operations ──────────────────────────────────────────────────────
// Intern a string view. Returns a stable ID. The string is copied into
// the table's internal buffer.
cos_string_id_t     cos_string_intern(cos_string_table_t* table, cos_string_view_t sv);

// Same as above but from a null-terminated C string.
cos_string_id_t     cos_string_intern_cstr(cos_string_table_t* table, const char* cstr);

// Look up an interned string. Returns the string view.
// The pointer is valid for the lifetime of the table.
cos_string_view_t   cos_string_lookup(const cos_string_table_t* table, cos_string_id_t id);

// Look up an existing interned string without inserting.
// Returns COS_STRING_ID_NULL if not found.
cos_string_id_t     cos_string_find(const cos_string_table_t* table, cos_string_view_t sv);

#define COS_STRING_ID_NULL ((cos_string_id_t)0)

// ── Introspection ────────────────────────────────────────────────────────
size_t              cos_string_table_count(const cos_string_table_t* table);
size_t              cos_string_table_memory_used(const cos_string_table_t* table);
size_t              cos_string_table_bytes_saved(const cos_string_table_t* table);

#ifdef __cplusplus
}
#endif

#endif // COS_STRING_INTERN_H
