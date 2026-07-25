// pool.c — Fixed-Size Object Pool Allocator
//
// Design: Manages a pool of fixed-size objects in contiguous blocks.
// Free slots are tracked via a singly-linked free list embedded in the
// freed slots themselves (zero overhead).
//
// Memory: Slots are packed in contiguous arrays for cache locality.
// Free list uses freed memory — zero overhead per slot.
//
// Performance: O(1) alloc and free. Adjacent allocations are adjacent
// in memory (excellent spatial locality).

#include "cos/core.h"
#include "cos/allocator.h"
#include "cos/pool.h"
#include <stdlib.h>
#include <string.h>
#include <stdalign.h>

// ── Pool Block ───────────────────────────────────────────────────────────
typedef struct cos_pool_block_s {
    struct cos_pool_block_s* next;
    size_t                   slot_count;
    // Slots follow immediately
} cos_pool_block_t;

#define POOL_BLOCK_HEADER_SIZE (sizeof(cos_pool_block_t))

// ── Free List Node (embedded in freed slots) ─────────────────────────────
typedef struct cos_pool_free_node_s {
    struct cos_pool_free_node_s* next;
} cos_pool_free_node_t;

// ── Pool Context ─────────────────────────────────────────────────────────
typedef struct cos_pool_ctx_s {
    cos_allocator_t*       backing;
    cos_pool_free_node_t*  free_list;
    cos_pool_block_t*      blocks;
    size_t                 object_size;
    size_t                 object_align;
    size_t                 slot_size;       // object_size rounded up to align
    size_t                 grow_count;
    size_t                 total_capacity;
    size_t                 total_allocated;
} cos_pool_ctx_t;

// Round up size to alignment
static inline size_t align_up(size_t size, size_t align) {
    return (size + align - 1) & ~(align - 1);
}

// ── Grow the pool (add a new block) ──────────────────────────────────────
static cos_status_t pool_grow(cos_pool_ctx_t* ctx) {
    size_t slots = ctx->grow_count > 0 ? ctx->grow_count :
                   (ctx->total_capacity > 0 ? ctx->total_capacity : 1024);

    size_t block_size = POOL_BLOCK_HEADER_SIZE + slots * ctx->slot_size;
    cos_pool_block_t* block = (cos_pool_block_t*)
        ctx->backing->alloc(ctx->backing, block_size, alignof(max_align_t));
    if (!block) return COS_ERROR_NOMEM;

    block->next = ctx->blocks;
    block->slot_count = slots;
    ctx->blocks = block;
    ctx->total_capacity += slots;

    // Add all new slots to the free list
    char* slot_start = (char*)block + POOL_BLOCK_HEADER_SIZE;
    for (size_t i = 0; i < slots; i++) {
        cos_pool_free_node_t* node = (cos_pool_free_node_t*)(slot_start + i * ctx->slot_size);
        node->next = ctx->free_list;
        ctx->free_list = node;
    }

    return COS_OK;
}

// ── Allocator VTable ─────────────────────────────────────────────────────

static void* pool_alloc(cos_allocator_t* a, size_t size, size_t align) {
    cos_pool_ctx_t* ctx = (cos_pool_ctx_t*)a->context;

    // Pool only handles fixed-size allocations
    if (size > ctx->object_size || align > ctx->object_align) {
        // Fallback to backing allocator for mismatched sizes
        return ctx->backing->alloc(ctx->backing, size, align);
    }

    if (!ctx->free_list) {
        if (pool_grow(ctx) != COS_OK) return NULL;
    }

    cos_pool_free_node_t* node = ctx->free_list;
    ctx->free_list = node->next;

    #ifndef NDEBUG
    memset(node, 0xCD, ctx->object_size);  // Poison
    #endif

    return (void*)node;
}

static void pool_free(cos_allocator_t* a, void* ptr, size_t size);

static void* pool_realloc(cos_allocator_t* a, void* ptr, size_t old_size, size_t new_size, size_t align) {
    cos_pool_ctx_t* ctx = (cos_pool_ctx_t*)a->context;

    if (new_size <= ctx->object_size && (!ptr || old_size <= ctx->object_size)) {
        // Within pool range — just return new allocation (or same)
        if (!ptr) return pool_alloc(a, new_size, align);
        void* new_ptr = pool_alloc(a, new_size, align);
        if (new_ptr && ptr) {
            size_t copy = old_size < new_size ? old_size : new_size;
            memcpy(new_ptr, ptr, copy);
        }
        pool_free(a, ptr, old_size);
        return new_ptr;
    }

    // Fallback
    return ctx->backing->realloc(ctx->backing, ptr, old_size, new_size, align);
}

static void pool_free(cos_allocator_t* a, void* ptr, size_t size) {
    cos_pool_ctx_t* ctx = (cos_pool_ctx_t*)a->context;

    if (!ptr) return;
    if (size > ctx->object_size) {
        ctx->backing->free(ctx->backing, ptr, size);
        return;
    }

    // Return to free list
    cos_pool_free_node_t* node = (cos_pool_free_node_t*)ptr;
    node->next = ctx->free_list;
    ctx->free_list = node;
}

static void pool_destroy(cos_allocator_t* a) {
    cos_pool_ctx_t* ctx = (cos_pool_ctx_t*)a->context;
    cos_allocator_t* backing = ctx->backing;

    cos_pool_block_t* block = ctx->blocks;
    while (block) {
        cos_pool_block_t* next = block->next;
        size_t block_size = POOL_BLOCK_HEADER_SIZE + block->slot_count * ctx->slot_size;
        backing->free(backing, block, block_size);
        block = next;
    }
    size_t ctx_size = sizeof(cos_pool_ctx_t);
    backing->free(backing, ctx, ctx_size);
    a->context = NULL;
    backing->free(backing, a, sizeof(cos_allocator_t));
}

static size_t pool_used(const cos_allocator_t* a) {
    cos_pool_ctx_t* ctx = (cos_pool_ctx_t*)a->context;
    size_t allocated = ctx->total_capacity;
    size_t free_count = 0;
    cos_pool_free_node_t* node = ctx->free_list;
    while (node) {
        free_count++;
        node = node->next;
    }
    return (allocated - free_count) * ctx->object_size;
}

// ── Public API ───────────────────────────────────────────────────────────

cos_allocator_t* cos_pool_create(const cos_pool_config_t* config, cos_allocator_t* backing) {
    if (!backing) backing = cos_sys_allocator();

    cos_pool_ctx_t* ctx = (cos_pool_ctx_t*)
        backing->alloc(backing, sizeof(cos_pool_ctx_t), alignof(cos_pool_ctx_t));
    if (!ctx) return NULL;

    ctx->backing      = backing;
    ctx->free_list    = NULL;
    ctx->blocks       = NULL;
    ctx->total_capacity = 0;
    ctx->total_allocated = 0;

    if (config) {
        ctx->object_size  = config->object_size > sizeof(void*) ? config->object_size : sizeof(void*);
        ctx->object_align = config->object_align > 0 ? config->object_align : alignof(max_align_t);
        ctx->grow_count   = config->grow_count;
    } else {
        ctx->object_size  = sizeof(void*);
        ctx->object_align = alignof(max_align_t);
        ctx->grow_count   = 0;
    }

    ctx->slot_size = align_up(ctx->object_size, ctx->object_align);

    // Pre-allocate first block if initial capacity specified
    size_t initial = config ? config->initial_capacity : 0;
    if (initial > 0) {
        ctx->grow_count = initial;  // Will be used on first growth
        ctx->grow_count = ctx->grow_count;  // Already set
    }

    cos_allocator_t* alloc = (cos_allocator_t*)
        backing->alloc(backing, sizeof(cos_allocator_t), alignof(cos_allocator_t));
    if (!alloc) {
        backing->free(backing, ctx, sizeof(cos_pool_ctx_t));
        return NULL;
    }

    alloc->alloc   = pool_alloc;
    alloc->realloc = pool_realloc;
    alloc->free    = pool_free;
    alloc->destroy = pool_destroy;
    alloc->used    = pool_used;
    alloc->context = ctx;

    // Pre-allocate if initial capacity was requested
    if (initial > 0) {
        pool_grow(ctx);
    }

    return alloc;
}

void cos_pool_destroy(cos_allocator_t* pool) {
    if (pool && pool->destroy) pool->destroy(pool);
}

void cos_pool_reset(cos_allocator_t* pool) {
    if (!pool || !pool->context) return;
    cos_pool_ctx_t* ctx = (cos_pool_ctx_t*)pool->context;
    ctx->free_list = NULL;

    // Rebuild free list from all blocks
    cos_pool_block_t* block = ctx->blocks;
    while (block) {
        char* slot_start = (char*)block + POOL_BLOCK_HEADER_SIZE;
        for (size_t i = 0; i < block->slot_count; i++) {
            cos_pool_free_node_t* node = (cos_pool_free_node_t*)(slot_start + i * ctx->slot_size);
            node->next = ctx->free_list;
            ctx->free_list = node;
        }
        block = block->next;
    }
}

size_t cos_pool_capacity(const cos_allocator_t* pool) {
    if (!pool || !pool->context) return 0;
    return ((cos_pool_ctx_t*)pool->context)->total_capacity;
}

size_t cos_pool_available(const cos_allocator_t* pool) {
    if (!pool || !pool->context) return 0;
    cos_pool_ctx_t* ctx = (cos_pool_ctx_t*)pool->context;
    size_t count = 0;
    cos_pool_free_node_t* node = ctx->free_list;
    while (node) { count++; node = node->next; }
    return count;
}
