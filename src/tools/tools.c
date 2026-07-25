// tools.c — Tool Registry Implementation
//
// Design: Central registry for user-facing tools.
// Tools are registered at startup and discovered by the planner.
//
// Memory: Tool array is fixed-size pre-allocated array.
// No allocations during registration or lookup.

#include "cos/core.h"
#include "cos/tools.h"
#include "cos/allocator.h"
#include <string.h>
#include <stdalign.h>

#ifdef __cplusplus
extern "C" {
#endif

// ── Tool Registry ────────────────────────────────────────────────────────
#define COS_TOOL_REGISTRY_MAX 64

struct cos_tool_registry_s {
    cos_allocator_t* alloc;
    cos_tool_t       tools[COS_TOOL_REGISTRY_MAX];
    size_t           tool_count;
};

// ── Lifecycle ────────────────────────────────────────────────────────────

cos_tool_registry_t* cos_tool_registry_create(cos_allocator_t* alloc) {
    if (!alloc) alloc = cos_sys_allocator();

    cos_tool_registry_t* reg = (cos_tool_registry_t*)
        alloc->alloc(alloc, sizeof(cos_tool_registry_t), alignof(cos_tool_registry_t));
    if (!reg) return NULL;

    memset(reg, 0, sizeof(cos_tool_registry_t));
    reg->alloc = alloc;
    return reg;
}

void cos_tool_registry_destroy(cos_tool_registry_t* reg) {
    if (!reg) return;
    reg->alloc->free(reg->alloc, reg, sizeof(cos_tool_registry_t));
}

// ── Registration ─────────────────────────────────────────────────────────

cos_status_t cos_tool_register(cos_tool_registry_t* reg, const cos_tool_t* tool) {
    if (!reg || !tool) return COS_ERROR_NULL;
    if (reg->tool_count >= COS_TOOL_REGISTRY_MAX) return COS_ERROR_FULL;

    // Check for duplicate
    for (size_t i = 0; i < reg->tool_count; i++) {
        if (strcmp(reg->tools[i].name, tool->name) == 0) {
            return COS_ERROR_EXISTS;
        }
    }

    reg->tools[reg->tool_count++] = *tool;
    return COS_OK;
}

cos_status_t cos_tool_unregister(cos_tool_registry_t* reg, const char* name) {
    if (!reg || !name) return COS_ERROR_NULL;

    for (size_t i = 0; i < reg->tool_count; i++) {
        if (strcmp(reg->tools[i].name, name) == 0) {
            // Shift remaining tools
            memmove(&reg->tools[i], &reg->tools[i+1],
                    (reg->tool_count - i - 1) * sizeof(cos_tool_t));
            reg->tool_count--;
            return COS_OK;
        }
    }
    return COS_ERROR_NOT_FOUND;
}

// ── Discovery & Execution ────────────────────────────────────────────────

const cos_tool_t* cos_tool_find(const cos_tool_registry_t* reg, const char* name) {
    if (!reg || !name) return NULL;

    for (size_t i = 0; i < reg->tool_count; i++) {
        if (strcmp(reg->tools[i].name, name) == 0) {
            return &reg->tools[i];
        }
    }
    return NULL;
}

cos_status_t cos_tool_execute(const cos_tool_registry_t* reg,
                               const char* name,
                               const char* args,
                               size_t args_length,
                               char* out_buffer,
                               size_t buffer_size,
                               size_t* out_written) {
    const cos_tool_t* tool = cos_tool_find(reg, name);
    if (!tool) return COS_ERROR_NOT_FOUND;
    return tool->execute(tool, args, args_length, out_buffer, buffer_size, out_written);
}

// ── Introspection ────────────────────────────────────────────────────────

size_t cos_tool_count(const cos_tool_registry_t* reg) {
    return reg ? reg->tool_count : 0;
}

const cos_tool_t* cos_tool_get(const cos_tool_registry_t* reg, size_t index) {
    if (!reg || index >= reg->tool_count) return NULL;
    return &reg->tools[index];
}

#ifdef __cplusplus
}
#endif
