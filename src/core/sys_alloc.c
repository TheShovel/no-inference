// sys_alloc.c — System Allocator (malloc/free Wrapper)
//
// Design: Wraps the C standard library malloc/free in the cos_allocator_t
// interface. This is the BOOTSTRAP allocator — used only to initialize
// arena/pool allocators which handle all production allocations.
//
// Memory: Delegates to libc. Only used during startup.

#include "cos/core.h"
#include "cos/allocator.h"
#include <stdlib.h>
#include <stddef.h>
#include <stdalign.h>
#include <string.h>

// ── Internal State ───────────────────────────────────────────────────────
// The system allocator is stateless, so context is NULL.

static void* sys_alloc(cos_allocator_t* a, size_t size, size_t align) {
    (void)a;
    (void)align;  // malloc returns suitably aligned memory for all types
    void* ptr = malloc(size);
    // Zero-initialize for safety (development builds)
    // In release, this is skipped for performance.
    #ifndef NDEBUG
    if (ptr) memset(ptr, 0, size);
    #endif
    return ptr;
}

static void* sys_realloc(cos_allocator_t* a, void* ptr, size_t old_size, size_t new_size, size_t align) {
    (void)a;
    (void)old_size;
    (void)align;
    return realloc(ptr, new_size);
}

static void sys_free(cos_allocator_t* a, void* ptr, size_t size) {
    (void)a;
    (void)size;
    free(ptr);
}

static void sys_destroy(cos_allocator_t* a) {
    (void)a;
    // Nothing to clean up — this is the root allocator.
}

static size_t sys_used(const cos_allocator_t* a) {
    (void)a;
    return 0;  // The system allocator cannot track usage
}

// ── Singleton ────────────────────────────────────────────────────────────
// The system allocator is a singleton (stateless, reusable).

static cos_allocator_t g_sys_allocator = {
    .alloc   = sys_alloc,
    .realloc = sys_realloc,
    .free    = sys_free,
    .destroy = sys_destroy,
    .used    = sys_used,
    .context = NULL,
};

cos_allocator_t* cos_sys_allocator(void) {
    return &g_sys_allocator;
}
