// string_intern.c — String Interning Table
//
// Design: Open-addressing hash table with linear probing.
// Keys are FNV-1a hashes of string views. Values are string IDs.
// Strings are stored contiguously in a growing buffer.
//
// Memory: Strings are packed sequentially — zero fragmentation.
// Hash table load factor targets ~60% for fast lookups.
// Each interned string costs: 4 bytes (hash slot) + length + 1 (null).
// No per-string heap allocations.

#include "cos/core.h"
#include "cos/allocator.h"
#include "cos/string_intern.h"
#include "cos/string_view.h"
#include <stdlib.h>
#include <string.h>
#include <stdalign.h>

// ── Initial Sizing ───────────────────────────────────────────────────────
#define COS_STRING_TABLE_INIT_CAPACITY  256    // Initial hash table slots
#define COS_STRING_BUF_INIT_SIZE       4096    // Initial string storage (4KB)
#define COS_STRING_GROW_FACTOR            2    // Double on resize
#define COS_STRING_MAX_LOAD_PERCENT      70    // Resize when >70% full

// ── Hash Table Slot ──────────────────────────────────────────────────────
// A value of 0 means empty slot (ID 0 is reserved as NULL).
typedef struct {
    cos_hash_t      hash;
    cos_string_id_t id;         // 1-based, 0 = empty
    uint32_t        offset;     // Offset into string buffer
    uint32_t        length;     // String length
} cos_string_slot_t;

// ── Table Context ────────────────────────────────────────────────────────
struct cos_string_table_s {
    cos_allocator_t*    alloc;
    cos_string_slot_t*  slots;
    size_t              capacity;       // Hash table slot count
    size_t              count;          // Number of interned strings

    char*               buffer;         // Contiguous string storage
    size_t              buffer_size;    // Allocated buffer size
    size_t              buffer_used;    // Used bytes in buffer

    size_t              total_requests; // Stats
    size_t              dedup_hits;     // Stats
};

// ── Resize hash table ────────────────────────────────────────────────────
static cos_status_t string_table_resize(cos_string_table_t* table, size_t new_capacity) {
    cos_string_slot_t* new_slots = (cos_string_slot_t*)
        table->alloc->alloc(table->alloc, new_capacity * sizeof(cos_string_slot_t), alignof(cos_string_slot_t));
    if (!new_slots) return COS_ERROR_NOMEM;

    memset(new_slots, 0, new_capacity * sizeof(cos_string_slot_t));

    // Rehash existing entries
    for (size_t i = 0; i < table->capacity; i++) {
        if (table->slots[i].id != 0) {
            cos_hash_t hash = table->slots[i].hash;
            size_t idx = (size_t)(hash % new_capacity);
            while (new_slots[idx].id != 0) {
                idx = (idx + 1) % new_capacity;
            }
            new_slots[idx] = table->slots[i];
        }
    }

    table->alloc->free(table->alloc, table->slots, table->capacity * sizeof(cos_string_slot_t));
    table->slots = new_slots;
    table->capacity = new_capacity;
    return COS_OK;
}

// ── Grow string buffer ───────────────────────────────────────────────────
static cos_status_t string_buffer_grow(cos_string_table_t* table, size_t needed) {
    size_t new_size = table->buffer_size > 0 ? table->buffer_size * 2 : COS_STRING_BUF_INIT_SIZE;
    while (new_size < table->buffer_used + needed) {
        new_size *= 2;
    }

    char* new_buf = (char*)
        table->alloc->alloc(table->alloc, new_size, alignof(char));
    if (!new_buf) return COS_ERROR_NOMEM;

    if (table->buffer) {
        memcpy(new_buf, table->buffer, table->buffer_used);
        table->alloc->free(table->alloc, table->buffer, table->buffer_size);
    }
    table->buffer = new_buf;
    table->buffer_size = new_size;
    return COS_OK;
}

// ── Lifecycle ────────────────────────────────────────────────────────────

cos_string_table_t* cos_string_table_create(cos_allocator_t* alloc) {
    if (!alloc) alloc = cos_sys_allocator();

    cos_string_table_t* table = (cos_string_table_t*)
        alloc->alloc(alloc, sizeof(cos_string_table_t), alignof(cos_string_table_t));
    if (!table) return NULL;

    table->alloc    = alloc;
    table->slots    = NULL;
    table->capacity = 0;
    table->count    = 0;
    table->buffer   = NULL;
    table->buffer_size   = 0;
    table->buffer_used   = 0;

    // Reserve initial slot
    // ID 0 = NULL string
    table->total_requests = 0;
    table->dedup_hits     = 0;

    // Allocate initial capacity
    if (string_table_resize(table, COS_STRING_TABLE_INIT_CAPACITY) != COS_OK) {
        alloc->free(alloc, table, sizeof(cos_string_table_t));
        return NULL;
    }

    // Allocate initial buffer
    if (string_buffer_grow(table, 1) != COS_OK) {
        alloc->free(alloc, table->slots, table->capacity * sizeof(cos_string_slot_t));
        alloc->free(alloc, table, sizeof(cos_string_table_t));
        return NULL;
    }

    return table;
}

void cos_string_table_destroy(cos_string_table_t* table) {
    if (!table) return;
    if (table->slots)  table->alloc->free(table->alloc, table->slots, table->capacity * sizeof(cos_string_slot_t));
    if (table->buffer) table->alloc->free(table->alloc, table->buffer, table->buffer_size);
    table->alloc->free(table->alloc, table, sizeof(cos_string_table_t));
}

void cos_string_table_reset(cos_string_table_t* table) {
    if (!table) return;
    memset(table->slots, 0, table->capacity * sizeof(cos_string_slot_t));
    table->count = 0;
    table->buffer_used = 0;
    table->total_requests = 0;
    table->dedup_hits = 0;
}

// ── Core Operations ──────────────────────────────────────────────────────

cos_string_id_t cos_string_intern(cos_string_table_t* table, cos_string_view_t sv) {
    if (!table || !sv.data || sv.length == 0) return COS_STRING_ID_NULL;

    table->total_requests++;

    cos_hash_t hash = cos_sv_hash(sv);
    size_t idx = (size_t)(hash % table->capacity);

    // Look for existing string (linear probing)
    while (true) {
        cos_string_slot_t* slot = &table->slots[idx];
        if (slot->id == 0) break;  // Empty slot

        if (slot->hash == hash && slot->length == sv.length) {
            // Compare actual string data
            const char* stored = table->buffer + slot->offset;
            if (memcmp(stored, sv.data, sv.length) == 0) {
                table->dedup_hits++;
                return slot->id;
            }
        }

        idx = (idx + 1) % table->capacity;
    }

    // Not found — insert new string
    cos_string_id_t id = (cos_string_id_t)(table->count + 1);  // 1-based

    // Ensure buffer has room
    if (table->buffer_used + sv.length + 1 > table->buffer_size) {
        if (string_buffer_grow(table, sv.length + 1) != COS_OK) return COS_STRING_ID_NULL;
    }

    // Copy string into buffer
    memcpy(table->buffer + table->buffer_used, sv.data, sv.length);
    table->buffer[table->buffer_used + sv.length] = '\0';  // Null-terminate (for C interop)

    // Fill slot
    table->slots[idx].hash   = hash;
    table->slots[idx].id     = id;
    table->slots[idx].offset = (uint32_t)table->buffer_used;
    table->slots[idx].length = (uint32_t)sv.length;

    table->buffer_used += sv.length + 1;
    table->count++;

    // Check load factor
    if (table->count * 100 / table->capacity > COS_STRING_MAX_LOAD_PERCENT) {
        string_table_resize(table, table->capacity * COS_STRING_GROW_FACTOR);
    }

    return id;
}

cos_string_id_t cos_string_intern_cstr(cos_string_table_t* table, const char* cstr) {
    if (!cstr) return COS_STRING_ID_NULL;
    return cos_string_intern(table, cos_sv_cstr(cstr));
}

cos_string_view_t cos_string_lookup(const cos_string_table_t* table, cos_string_id_t id) {
    cos_string_view_t sv = { NULL, 0 };
    if (!table || id == COS_STRING_ID_NULL) return sv;

    // Linear scan to find the slot with this ID
    // Optimization: we could store IDs sorted, but for simplicity we scan.
    // In practice, callers should keep the string_view and only use IDs for storage.
    for (size_t i = 0; i < table->capacity; i++) {
        if (table->slots[i].id == id) {
            sv.data   = table->buffer + table->slots[i].offset;
            sv.length = table->slots[i].length;
            return sv;
        }
    }
    return sv;
}

cos_string_id_t cos_string_find(const cos_string_table_t* table, cos_string_view_t sv) {
    if (!table || !sv.data || sv.length == 0) return COS_STRING_ID_NULL;

    cos_hash_t hash = cos_sv_hash(sv);
    size_t idx = (size_t)(hash % table->capacity);

    while (true) {
        const cos_string_slot_t* slot = &table->slots[idx];
        if (slot->id == 0) return COS_STRING_ID_NULL;

        if (slot->hash == hash && slot->length == sv.length) {
            const char* stored = table->buffer + slot->offset;
            if (memcmp(stored, sv.data, sv.length) == 0) {
                return slot->id;
            }
        }

        idx = (idx + 1) % table->capacity;
    }
}

// ── Introspection ────────────────────────────────────────────────────────

size_t cos_string_table_count(const cos_string_table_t* table) {
    return table ? table->count : 0;
}

size_t cos_string_table_memory_used(const cos_string_table_t* table) {
    if (!table) return 0;
    return sizeof(cos_string_table_t) +
           table->capacity * sizeof(cos_string_slot_t) +
           table->buffer_size;
}

size_t cos_string_table_bytes_saved(const cos_string_table_t* table) {
    if (!table || table->total_requests == 0) return 0;
    // Estimate: without interning, each request would allocate a copy
    // With interning, only unique strings are stored once.
    // Total "saved" = (total_requests - count) * average_length
    size_t avg_length = table->count > 0 ? table->buffer_used / table->count : 0;
    return (table->total_requests - table->count) * avg_length;
}
