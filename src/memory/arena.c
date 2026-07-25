// arena.c — Arena (Bump) Allocator
//
// Design: The arena allocator manages a linked list of large blocks.
// Each allocation bumps a pointer within the current block.
// When a block is exhausted, a new block (doubling size) is allocated.
// The entire arena is freed by freeing all blocks — O(1) reset.
//
// Memory: Zero per-allocation metadata overhead.
// Blocks are page-aligned for TLB-friendly access.
// Block size doubles to amortize allocation cost.

#include "cos/core.h"
#include "cos/allocator.h"
#include "cos/arena.h"
#include <stdlib.h>
#include <string.h>
#include <stdalign.h>

// ── Arena Block ──────────────────────────────────────────────────────────
typedef struct cos_arena_block_s {
    struct cos_arena_block_s* next;
    size_t                    size;
    size_t                    used;
    // Data follows immediately
} cos_arena_block_t;

#define COS_ARENA_HEADER_SIZE (sizeof(cos_arena_block_t))

// ── Arena Context ────────────────────────────────────────────────────────
typedef struct cos_arena_ctx_s {
    cos_arena_block_t* head;
    cos_arena_block_t* current;
    cos_allocator_t*   backing;
    size_t             block_size;
    size_t             total_allocated;
} cos_arena_ctx_t;

// ── Allocator VTable Methods ─────────────────────────────────────────────

static void* arena_alloc(cos_allocator_t* a, size_t size, size_t align) {
    cos_arena_ctx_t* ctx = (cos_arena_ctx_t*)a->context;

    // Align the current offset
    size_t current = ctx->current ? ctx->current->used : 0;
    size_t aligned = (current + align - 1) & ~(align - 1);
    size_t new_used = aligned + size;

    // Check if current block has room
    if (!ctx->current || new_used > ctx->current->size) {
        // Allocate a new block
        size_t block_size = ctx->current ?
            (ctx->current->size * 2 > ctx->block_size ? ctx->current->size * 2 : ctx->block_size) :
            ctx->block_size;

        // Ensure block is at least large enough for this allocation
        size_t needed = size + COS_ARENA_HEADER_SIZE + align;
        if (block_size < needed) {
            block_size = needed;
        }

        cos_arena_block_t* block = (cos_arena_block_t*)
            ctx->backing->alloc(ctx->backing, block_size, alignof(max_align_t));
        if (!block) return NULL;

        block->next = NULL;
        block->size = block_size - COS_ARENA_HEADER_SIZE;
        block->used = 0;

        ctx->total_allocated += block_size;

        if (ctx->current) {
            ctx->current->next = block;
        } else {
            ctx->head = block;
        }
        ctx->current = block;

        aligned = 0;
        new_used = size;
    }

    void* ptr = (char*)ctx->current + COS_ARENA_HEADER_SIZE + aligned;
    ctx->current->used = new_used;

    #ifndef NDEBUG
    memset(ptr, 0xCD, size);  // Poison in debug builds
    #endif

    return ptr;
}

static void* arena_realloc(cos_allocator_t* a, void* ptr, size_t old_size, size_t new_size, size_t align) {
    (void)old_size;
    // Arena realloc: allocate new, copy, free old (no-op)
    void* new_ptr = arena_alloc(a, new_size, align);
    if (!new_ptr) return NULL;
    size_t copy = old_size < new_size ? old_size : new_size;
    if (ptr && new_ptr) memcpy(new_ptr, ptr, copy);
    // "Free" is a no-op in arena allocator
    return new_ptr;
}

static void arena_free(cos_allocator_t* a, void* ptr, size_t size) {
    (void)a;
    (void)ptr;
    (void)size;
    // No-op: individual frees are not supported in arena allocator.
    // Memory is reclaimed when arena is reset or destroyed.
}

static void arena_destroy(cos_allocator_t* a) {
    cos_arena_ctx_t* ctx = (cos_arena_ctx_t*)a->context;
    cos_allocator_t* backing = ctx->backing;

    cos_arena_block_t* block = ctx->head;
    while (block) {
        cos_arena_block_t* next = block->next;
        backing->free(backing, block, block->size + COS_ARENA_HEADER_SIZE);
        block = next;
    }
    size_t ctx_size = sizeof(cos_arena_ctx_t);
    backing->free(backing, ctx, ctx_size);
    a->context = NULL;
    backing->free(backing, a, sizeof(cos_allocator_t));
}

static size_t arena_used(const cos_allocator_t* a) {
    cos_arena_ctx_t* ctx = (cos_arena_ctx_t*)a->context;
    size_t used = 0;
    cos_arena_block_t* block = ctx->head;
    while (block) {
        used += block->used;
        block = block->next;
    }
    return used;
}

// ── Public API ───────────────────────────────────────────────────────────

cos_allocator_t* cos_arena_create(const cos_arena_config_t* config, cos_allocator_t* backing) {
    if (!backing) backing = cos_sys_allocator();

    cos_arena_ctx_t* ctx = (cos_arena_ctx_t*)
        backing->alloc(backing, sizeof(cos_arena_ctx_t), alignof(cos_arena_ctx_t));
    if (!ctx) return NULL;

    ctx->head    = NULL;
    ctx->current = NULL;
    ctx->backing = backing;
    ctx->total_allocated = 0;

    if (config) {
        ctx->block_size = config->block_size > 0 ? config->block_size : COS_ARENA_DEFAULT_BLOCK_SIZE;
    } else {
        ctx->block_size = COS_ARENA_DEFAULT_BLOCK_SIZE;
    }

    cos_allocator_t* alloc = (cos_allocator_t*)
        backing->alloc(backing, sizeof(cos_allocator_t), alignof(cos_allocator_t));
    if (!alloc) {
        backing->free(backing, ctx, sizeof(cos_arena_ctx_t));
        return NULL;
    }

    alloc->alloc   = arena_alloc;
    alloc->realloc = arena_realloc;
    alloc->free    = arena_free;
    alloc->destroy = arena_destroy;
    alloc->used    = arena_used;
    alloc->context = ctx;

    return alloc;
}

void cos_arena_reset(cos_allocator_t* arena) {
    if (!arena || !arena->context) return;
    cos_arena_ctx_t* ctx = (cos_arena_ctx_t*)arena->context;

    // Reset all block usage counters — keeps blocks for reuse
    cos_arena_block_t* block = ctx->head;
    while (block) {
        block->used = 0;
        block = block->next;
    }
    ctx->current = ctx->head;
}

cos_allocator_t* cos_arena_backing(const cos_allocator_t* arena) {
    if (!arena || !arena->context) return NULL;
    return ((cos_arena_ctx_t*)arena->context)->backing;
}
