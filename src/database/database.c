// database.c — Database Abstraction Layer Implementation
//
// Design: Provides a uniform interface for different database backends.
// Default backend is an in-memory store. SQLite and DuckDB can be attached.
//
// Memory: In-memory store uses simple arrays. External databases handle
// their own memory.

#include "cos/core.h"
#include "cos/database.h"
#include "cos/allocator.h"
#include <string.h>
#include <stdalign.h>

#ifdef __cplusplus
extern "C" {
#endif

// ── In-Memory Database ───────────────────────────────────────────────────
// Simple key-value store for the default backend.

typedef struct cos_db_mem_row_s {
    cos_string_view_t* values;
    size_t             count;
} cos_db_mem_row_t;

typedef struct cos_db_mem_table_s {
    char*              name;
    cos_string_view_t* column_names;
    size_t             column_count;
    cos_db_mem_row_t*  rows;
    size_t             row_count;
    size_t             row_capacity;
} cos_db_mem_table_t;

typedef struct cos_db_mem_ctx_s {
    cos_allocator_t*   alloc;
    cos_db_mem_table_t tables[8];
    size_t             table_count;
} cos_db_mem_ctx_t;

// ── Database ─────────────────────────────────────────────────────────────
struct cos_database_s {
    cos_db_type_t    type;
    cos_allocator_t* alloc;
    void*            backend_ctx;     // Backend-specific context
    char*            path;
};

// ── Lifecycle ────────────────────────────────────────────────────────────

cos_database_t* cos_database_create(const cos_database_config_t* config) {
    if (!config) return NULL;

    cos_database_t* db = (cos_database_t*)
        config->allocator->alloc(config->allocator, sizeof(cos_database_t), alignof(cos_database_t));
    if (!db) return NULL;

    db->type  = config->type;
    db->alloc = config->allocator;
    db->backend_ctx = NULL;

    if (config->path) {
        size_t path_len = strlen(config->path);
        db->path = (char*)config->allocator->alloc(config->allocator, path_len + 1, alignof(char));
        if (db->path) memcpy(db->path, config->path, path_len + 1);
    } else {
        db->path = NULL;
    }

    // Initialize backend
    if (config->type == COS_DB_MEMORY || config->type == COS_DB_CUSTOM) {
        cos_db_mem_ctx_t* mem = (cos_db_mem_ctx_t*)
            config->allocator->alloc(config->allocator, sizeof(cos_db_mem_ctx_t), alignof(cos_db_mem_ctx_t));
        if (mem) {
            memset(mem, 0, sizeof(cos_db_mem_ctx_t));
            mem->alloc = config->allocator;
            db->backend_ctx = mem;
        }
    }

    return db;
}

void cos_database_destroy(cos_database_t* db) {
    if (!db) return;
    if (db->backend_ctx) {
        // Free in-memory backend data
        if (db->type == COS_DB_MEMORY || db->type == COS_DB_CUSTOM) {
            cos_db_mem_ctx_t* mem = (cos_db_mem_ctx_t*)db->backend_ctx;
            for (size_t t = 0; t < mem->table_count; t++) {
                cos_db_mem_table_t* table = &mem->tables[t];
                for (size_t r = 0; r < table->row_count; r++) {
                    if (table->rows[r].values) {
                        mem->alloc->free(mem->alloc, table->rows[r].values,
                            table->rows[r].count * sizeof(cos_string_view_t));
                    }
                }
                if (table->rows) mem->alloc->free(mem->alloc, table->rows,
                    table->row_capacity * sizeof(cos_db_mem_row_t));
                if (table->name) mem->alloc->free(mem->alloc, table->name, strlen(table->name) + 1);
            }
            mem->alloc->free(mem->alloc, mem, sizeof(cos_db_mem_ctx_t));
        }
    }
    if (db->path) db->alloc->free(db->alloc, db->path, strlen(db->path) + 1);
    db->alloc->free(db->alloc, db, sizeof(cos_database_t));
}

// ── Queries ──────────────────────────────────────────────────────────────

cos_status_t cos_database_query(cos_database_t* db,
                                 const char* query,
                                 cos_db_result_t* out_result,
                                 cos_allocator_t* scratch) {
    (void)db;
    (void)query;
    (void)out_result;
    (void)scratch;
    return COS_ERROR_NOT_IMPL;
}

cos_status_t cos_database_exec(cos_database_t* db, const char* statement) {
    (void)db;
    (void)statement;
    return COS_ERROR_NOT_IMPL;
}

// ── Prepared Statements ──────────────────────────────────────────────────

struct cos_db_stmt_s {
    // Stub
    int dummy;
};

cos_status_t cos_database_prepare(cos_database_t* db, const char* query, cos_db_stmt_t** out_stmt) {
    (void)db;
    (void)query;
    (void)out_stmt;
    return COS_ERROR_NOT_IMPL;
}

cos_status_t cos_db_stmt_bind_text(cos_db_stmt_t* stmt, int index, cos_string_view_t value) {
    (void)stmt;
    (void)index;
    (void)value;
    return COS_ERROR_NOT_IMPL;
}

cos_status_t cos_db_stmt_bind_int(cos_db_stmt_t* stmt, int index, int64_t value) {
    (void)stmt;
    (void)index;
    (void)value;
    return COS_ERROR_NOT_IMPL;
}

cos_status_t cos_db_stmt_step(cos_db_stmt_t* stmt) {
    (void)stmt;
    return COS_ERROR_NOT_IMPL;
}

cos_status_t cos_db_stmt_reset(cos_db_stmt_t* stmt) {
    (void)stmt;
    return COS_ERROR_NOT_IMPL;
}

void cos_db_stmt_destroy(cos_db_stmt_t* stmt) {
    (void)stmt;
}

// ── Introspection ────────────────────────────────────────────────────────

cos_db_type_t cos_database_type(const cos_database_t* db) {
    return db ? db->type : COS_DB_MEMORY;
}

size_t cos_database_memory_used(const cos_database_t* db) {
    if (!db) return 0;
    return sizeof(cos_database_t) + (db->path ? strlen(db->path) + 1 : 0);
}

#ifdef __cplusplus
}
#endif
