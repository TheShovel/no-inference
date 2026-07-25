// arena.h — Arena (Bump) Allocator
//
// Design: Allocate large blocks (e.g., 64KB pages) and bump-allocate
// within them. Freeing individual allocations is a no-op; the entire
// arena is reset at once. Ideal for per-request / per-conversation
// scratch memory.
//
// Memory: Zero per-allocation overhead (no metadata stored).
// Fragmentation is impossible. Cache-friendly sequential access.
//
// Performance: Allocation is ~3 instructions (check, bump, return).
// Reset is O(1) — just reset the bump pointer.

#ifndef COS_ARENA_H
#define COS_ARENA_H

#include "cos/core.h"
#include "cos/allocator.h"
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

// ── Arena Config ─────────────────────────────────────────────────────────
typedef struct cos_arena_config_s {
    size_t block_size;      // Size of each arena block (default: 64KB)
    size_t initial_size;    // First block size (default: block_size)
} cos_arena_config_t;

#define COS_ARENA_DEFAULT_BLOCK_SIZE (64UL * 1024UL)  // 64 KB

// ── Lifecycle ────────────────────────────────────────────────────────────
// Create an arena allocator. `backing` is used for the arena's own block
// allocations; pass cos_sys_allocator() for bootstrapping.
cos_allocator_t* cos_arena_create(const cos_arena_config_t* config, cos_allocator_t* backing);

// Reset the arena — all allocations are invalidated.
// O(1) operation regardless of how many allocations were made.
void cos_arena_reset(cos_allocator_t* arena);

// Return the arena allocator's backing allocator (for chaining).
cos_allocator_t* cos_arena_backing(const cos_allocator_t* arena);

#ifdef __cplusplus
}
#endif

#endif // COS_ARENA_H
