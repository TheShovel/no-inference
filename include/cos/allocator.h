// allocator.h — Abstract Allocator Interface
//
// Design: Every memory allocation in COS goes through a cos_allocator_t.
// This enables full control over memory strategy per subsystem:
//   - Arena allocators for batch deallocation
//   - Pool allocators for fixed-size objects
//   - Stack allocators for LIFO-scoped allocations
//   - Wrappers around malloc/free for bootstrapping
//
// Memory: Allocator vtable is 5 function pointers = 40 bytes on 64-bit.
// Per-allocation overhead is ZERO when using arena/pool allocators.

#ifndef COS_ALLOCATOR_H
#define COS_ALLOCATOR_H

#include "cos/core.h"
#include <stddef.h>
#include <stdalign.h>

#ifdef __cplusplus
extern "C" {
#endif

// ── Allocator Function Table ─────────────────────────────────────────────
// Each allocator instance provides its own implementations.
// This vtable approach adds indirection but enables composition
// (e.g., a pool allocator that falls back to an arena).
typedef struct cos_allocator_s cos_allocator_t;

// Allocate `size` bytes, aligned to `align`.
// Returns NULL on failure (caller checks).
typedef void* (*cos_alloc_fn_t)(cos_allocator_t* a, size_t size, size_t align);

// Reallocate `ptr` (must have been returned by this allocator).
// Returns NULL on failure. Original block is unchanged on failure.
typedef void* (*cos_realloc_fn_t)(cos_allocator_t* a, void* ptr, size_t old_size, size_t new_size, size_t align);

// Free `ptr` (must have been returned by this allocator).
// May be a no-op for arena/pool allocators.
typedef void  (*cos_free_fn_t)(cos_allocator_t* a, void* ptr, size_t size);

// Destroy the allocator and release all resources.
typedef void  (*cos_destroy_fn_t)(cos_allocator_t* a);

// Return an estimate of total bytes allocated.
typedef size_t (*cos_alloc_used_fn_t)(const cos_allocator_t* a);

struct cos_allocator_s {
    cos_alloc_fn_t      alloc;
    cos_realloc_fn_t    realloc;
    cos_free_fn_t       free;
    cos_destroy_fn_t    destroy;
    cos_alloc_used_fn_t used;
    void*               context;  // allocator-specific state
};

// ── Convenience Inline Helpers ───────────────────────────────────────────
// These reduce boilerplate at call sites.

static inline void*
cos_alloc(cos_allocator_t* a, size_t size, size_t align) {
    return a->alloc(a, size, align);
}

static inline void*
cos_alloc_default(cos_allocator_t* a, size_t size) {
    return a->alloc(a, size, alignof(max_align_t));
}

static inline void*
cos_realloc(cos_allocator_t* a, void* ptr, size_t old_size, size_t new_size, size_t align) {
    return a->realloc(a, ptr, old_size, new_size, align);
}

static inline void
cos_free(cos_allocator_t* a, void* ptr, size_t size) {
    if (ptr) a->free(a, ptr, size);
}

static inline void
cos_allocator_destroy(cos_allocator_t* a) {
    if (a && a->destroy) a->destroy(a);
}

static inline size_t
cos_allocator_used(const cos_allocator_t* a) {
    return a->used ? a->used(a) : 0;
}

// ── System Allocator (malloc/free wrapper) ───────────────────────────────
// Only for bootstrapping. Production allocators should use arena/pool.
cos_allocator_t* cos_sys_allocator(void);

#ifdef __cplusplus
}
#endif

#endif // COS_ALLOCATOR_H
