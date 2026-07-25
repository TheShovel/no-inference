// stack_alloc.h — Stack (LIFO) Allocator
//
// Design: A marker-based stack allocator. Allocations push a marker;
// freeing rewinds to a marker. Ideal for scoped, nested allocations
// during parsing or graph traversal.
//
// Memory: Zero per-allocation overhead. Only a stack of markers.
// Markers are 16 bytes each.
//
// Performance: Alloc is O(1) (bump with overflow check).
// Free-to-marker is O(1). No per-allocation tracking.

#ifndef COS_STACK_ALLOC_H
#define COS_STACK_ALLOC_H

#include "cos/core.h"
#include "cos/allocator.h"
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

// ── Opaque stack marker ──────────────────────────────────────────────────
typedef struct cos_stack_marker_s {
    size_t block_index;
    size_t offset;
} cos_stack_marker_t;

// ── Lifecycle ────────────────────────────────────────────────────────────
cos_allocator_t* cos_stack_alloc_create(size_t block_size, cos_allocator_t* backing);
void             cos_stack_alloc_destroy(cos_allocator_t* sa);

// ── Marker Operations ────────────────────────────────────────────────────
cos_stack_marker_t cos_stack_mark(const cos_allocator_t* sa);
void               cos_stack_rewind(cos_allocator_t* sa, cos_stack_marker_t marker);
void               cos_stack_reset(cos_allocator_t* sa);

#ifdef __cplusplus
}
#endif

#endif // COS_STACK_ALLOC_H
