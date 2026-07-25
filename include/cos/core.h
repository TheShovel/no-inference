// core.h - COS Core Type Definitions
//
// Design: Defines the fundamental types shared across every subsystem.
// No dependencies on other COS headers.
// All types are plain-old-data where possible for cache-friendly layouts.
//
// Memory: < 64 bytes - trivially fits in L1 cache line.

#ifndef COS_CORE_H
#define COS_CORE_H

#include <stddef.h>   // size_t, ptrdiff_t, NULL
#include <stdint.h>   // fixed-width integer types
#include <stdbool.h>  // bool, true, false
#include <limits.h>   // INT_MAX, etc.

#ifdef __cplusplus
extern "C" {
#endif

// -- Version ---------------------------------------------------------------
#define COS_VERSION_MAJOR 0
#define COS_VERSION_MINOR 1
#define COS_VERSION_PATCH 0

// -- Status Codes ----------------------------------------------------------
// Every public API function returns a cos_status_t.
// Zero means success, negative values are errors, positive are warnings/info.
typedef int32_t cos_status_t;

#define COS_OK                      0
#define COS_ERROR_NOMEM            -1   // Allocation failed
#define COS_ERROR_NULL             -2   // NULL pointer provided
#define COS_ERROR_INVALID_ARG      -3   // Invalid argument
#define COS_ERROR_NOT_FOUND        -4   // Resource not found
#define COS_ERROR_EXISTS           -5   // Resource already exists
#define COS_ERROR_BOUNDS           -6   // Out of bounds
#define COS_ERROR_EMPTY            -7   // Collection is empty
#define COS_ERROR_FULL             -8   // Collection is full
#define COS_ERROR_IO               -9   // I/O error
#define COS_ERROR_PARSE           -10   // Parse error
#define COS_ERROR_TYPE            -11   // Type mismatch
#define COS_ERROR_STATE           -12   // Invalid state
#define COS_ERROR_NOT_IMPL        -99   // Not implemented

// -- Opaque Handle ---------------------------------------------------------
// A typed pointer that hides implementation details.
typedef struct cos_handle_s {
    void* ptr;
} cos_handle_t;

// -- Result Wrapper --------------------------------------------------------
// Lightweight result type for fallible operations.
typedef struct cos_result_s {
    cos_status_t status;
    void*        data;
} cos_result_t;

// -- String View -----------------------------------------------------------
// A non-owning view into a string buffer.
// 16 bytes - two registers, trivially copyable.
// This is the PRIMARY string type throughout COS.
typedef struct cos_string_view_s {
    const char* data;
    size_t      length;
} cos_string_view_t;

// -- Interned String ID ----------------------------------------------------
typedef uint32_t cos_string_id_t;

// -- Node / Edge IDs -------------------------------------------------------
typedef uint32_t cos_node_id_t;
typedef uint32_t cos_edge_id_t;

#define COS_NODE_ID_NULL  UINT32_MAX
#define COS_EDGE_ID_NULL  UINT32_MAX

// -- Timestamps ------------------------------------------------------------
typedef int64_t cos_timestamp_t;

// -- Hash values -----------------------------------------------------------
typedef uint64_t cos_hash_t;

// -- Utility Functions -----------------------------------------------------
const char* cos_status_string(cos_status_t status);
cos_timestamp_t cos_timestamp_now(void);
void cos_log(cos_status_t level, const char* subsystem, const char* format, ...);

#ifdef __cplusplus
}

#endif

#endif // COS_CORE_H
