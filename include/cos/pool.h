// pool.h — Fixed-Size Object Pool Allocator
//
// Design: Pre-allocates a block of memory and divides it into
// fixed-size slots. Free slots are tracked via a free-list embedded
// in the slots themselves (no separate metadata array).
//
// Memory: Zero overhead per allocation (free list is stored in freed slots).
// Perfect for graph nodes, AST nodes, symbols, etc.
//
// Performance: O(1) alloc/free. Excellent cache locality — objects of same
// type are packed in contiguous memory.

#ifndef COS_POOL_H
#define COS_POOL_H

#include "cos/core.h"
#include "cos/allocator.h"
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

// ── Pool Config ──────────────────────────────────────────────────────────
typedef struct cos_pool_config_s {
    size_t  object_size;     // Size of each pooled object (must be >= sizeof(void*))
    size_t  object_align;    // Alignment of each object
    size_t  initial_capacity;// Initial number of slots (0 = default 1024)
    size_t  grow_count;      // Number of slots to add when full (0 = double)
} cos_pool_config_t;

// ── Lifecycle ────────────────────────────────────────────────────────────
cos_allocator_t* cos_pool_create(const cos_pool_config_t* config, cos_allocator_t* backing);
void             cos_pool_destroy(cos_allocator_t* pool);
void             cos_pool_reset(cos_allocator_t* pool);

// ── Introspection ────────────────────────────────────────────────────────
size_t cos_pool_capacity(const cos_allocator_t* pool);
size_t cos_pool_available(const cos_allocator_t* pool);

#ifdef __cplusplus
}
#endif

#endif // COS_POOL_H
