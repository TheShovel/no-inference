// database.h — Database Abstraction Layer
//
// Design: Provides a uniform interface over different database backends.
// Supports both embedded (SQLite) and columnar (DuckDB) databases,
// plus custom memory-mapped binary formats.
//
// Memory: Results use caller-provided memory. Queries are pre-compiled
// statements cached in a pool.

#ifndef COS_DATABASE_H
#define COS_DATABASE_H

#include "cos/core.h"
#include "cos/allocator.h"
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

// ── Database Types ───────────────────────────────────────────────────────
typedef uint32_t cos_db_type_t;

enum {
    COS_DB_MEMORY     = 0,   // In-memory hash/index store
    COS_DB_SQLITE     = 1,   // SQLite backend
    COS_DB_DUCKDB     = 2,   // DuckDB backend
    COS_DB_MMAP       = 3,   // Memory-mapped binary file
    COS_DB_CUSTOM     = 4,   // Custom backend
};

// ── Row ──────────────────────────────────────────────────────────────────
typedef struct cos_db_row_s {
    cos_string_view_t* columns;    // Array of column values
    size_t             column_count;
} cos_db_row_t;

// ── Query Result ─────────────────────────────────────────────────────────
typedef struct cos_db_result_s {
    cos_db_row_t* rows;
    size_t        row_count;
    size_t        column_count;
    cos_string_view_t* column_names;
} cos_db_result_t;

// ── Opaque Database ──────────────────────────────────────────────────────
typedef struct cos_database_s cos_database_t;

typedef struct cos_database_config_s {
    cos_db_type_t    type;
    cos_allocator_t* allocator;
    const char*      path;        // Path to database file (NULL for in-memory)
} cos_database_config_t;

// ── Lifecycle ────────────────────────────────────────────────────────────
cos_database_t* cos_database_create(const cos_database_config_t* config);
void            cos_database_destroy(cos_database_t* db);

// ── Queries ──────────────────────────────────────────────────────────────
cos_status_t cos_database_query(cos_database_t* db, const char* query, cos_db_result_t* out_result, cos_allocator_t* scratch);
cos_status_t cos_database_exec(cos_database_t* db, const char* statement);

// ── Prepared Statements ──────────────────────────────────────────────────
typedef struct cos_db_stmt_s cos_db_stmt_t;
cos_status_t cos_database_prepare(cos_database_t* db, const char* query, cos_db_stmt_t** out_stmt);
cos_status_t cos_db_stmt_bind_text(cos_db_stmt_t* stmt, int index, cos_string_view_t value);
cos_status_t cos_db_stmt_bind_int(cos_db_stmt_t* stmt, int index, int64_t value);
cos_status_t cos_db_stmt_step(cos_db_stmt_t* stmt);
cos_status_t cos_db_stmt_reset(cos_db_stmt_t* stmt);
void         cos_db_stmt_destroy(cos_db_stmt_t* stmt);

// ── Introspection ────────────────────────────────────────────────────────
cos_db_type_t cos_database_type(const cos_database_t* db);
size_t        cos_database_memory_used(const cos_database_t* db);

#ifdef __cplusplus
}
#endif

#endif // COS_DATABASE_H
