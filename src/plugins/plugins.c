// plugins.c — Plugin Registry Implementation
//
// Design: Plugin registry discovers and manages plugins.
// Each plugin exposes a cos_plugin_descriptor_t with lifecycle hooks.
// Plugins can be compiled-in or loaded from shared libraries.
//
// Memory: Plugin descriptors are stored in a fixed-size array.
// No allocations during registration.

#include "cos/core.h"
#include "cos/plugins.h"
#include "cos/allocator.h"
#include <stdint.h>
#include <string.h>
#include <stdalign.h>

#ifdef __cplusplus
extern "C" {
#endif

// ── Plugin Registry ──────────────────────────────────────────────────────
#define COS_PLUGIN_REGISTRY_MAX 64

struct cos_plugin_registry_s {
    cos_allocator_t*           alloc;
    cos_plugin_descriptor_t*   descriptors[COS_PLUGIN_REGISTRY_MAX];
    void*                      instances[COS_PLUGIN_REGISTRY_MAX];
    size_t                     count;
};

// ── Lifecycle ────────────────────────────────────────────────────────────

cos_plugin_registry_t* cos_plugin_registry_create(cos_allocator_t* alloc) {
    if (!alloc) alloc = cos_sys_allocator();

    cos_plugin_registry_t* reg = (cos_plugin_registry_t*)
        alloc->alloc(alloc, sizeof(cos_plugin_registry_t), alignof(cos_plugin_registry_t));
    if (!reg) return NULL;

    memset(reg, 0, sizeof(cos_plugin_registry_t));
    reg->alloc = alloc;
    return reg;
}

void cos_plugin_registry_destroy(cos_plugin_registry_t* reg) {
    if (!reg) return;

    // Destroy all plugin instances
    for (size_t i = 0; i < reg->count; i++) {
        if (reg->descriptors[i] && reg->descriptors[i]->destroy && reg->instances[i]) {
            reg->descriptors[i]->destroy(reg->instances[i]);
        }
    }

    reg->alloc->free(reg->alloc, reg, sizeof(cos_plugin_registry_t));
}

// ── Registration ─────────────────────────────────────────────────────────

cos_status_t cos_plugin_register(cos_plugin_registry_t* reg,
                                  const cos_plugin_descriptor_t* descriptor) {
    if (!reg || !descriptor) return COS_ERROR_NULL;
    if (reg->count >= COS_PLUGIN_REGISTRY_MAX) return COS_ERROR_FULL;

    // Check for duplicate
    for (size_t i = 0; i < reg->count; i++) {
        if (reg->descriptors[i] && strcmp(reg->descriptors[i]->name, descriptor->name) == 0) {
            return COS_ERROR_EXISTS;
        }
    }

    reg->descriptors[reg->count] = (cos_plugin_descriptor_t*)(uintptr_t)descriptor;

    // Create plugin instance
    if (descriptor->create) {
        reg->instances[reg->count] = descriptor->create(reg->alloc);
    } else {
        reg->instances[reg->count] = NULL;
    }

    reg->count++;
    return COS_OK;
}

cos_status_t cos_plugin_unregister(cos_plugin_registry_t* reg, const char* name) {
    if (!reg || !name) return COS_ERROR_NULL;

    for (size_t i = 0; i < reg->count; i++) {
        if (reg->descriptors[i] && strcmp(reg->descriptors[i]->name, name) == 0) {
            if (reg->descriptors[i]->destroy && reg->instances[i]) {
                reg->descriptors[i]->destroy(reg->instances[i]);
            }
            // Shift remaining
            memmove(&reg->descriptors[i], &reg->descriptors[i+1],
                    (reg->count - i - 1) * sizeof(cos_plugin_descriptor_t*));
            memmove(&reg->instances[i], &reg->instances[i+1],
                    (reg->count - i - 1) * sizeof(void*));
            reg->count--;
            return COS_OK;
        }
    }
    return COS_ERROR_NOT_FOUND;
}

// ── Discovery ────────────────────────────────────────────────────────────

size_t cos_plugin_find(const cos_plugin_registry_t* reg,
                        cos_plugin_capability_t capabilities,
                        const char*** out_names,
                        size_t max_results) {
    if (!reg || !out_names) return 0;

    size_t found = 0;
    for (size_t i = 0; i < reg->count && found < max_results; i++) {
        if (reg->descriptors[i] && (reg->descriptors[i]->capabilities & capabilities)) {
            out_names[found++] = &reg->descriptors[i]->name;
        }
    }
    return found;
}

const cos_plugin_descriptor_t* cos_plugin_get(const cos_plugin_registry_t* reg,
                                               const char* name) {
    if (!reg || !name) return NULL;

    for (size_t i = 0; i < reg->count; i++) {
        if (reg->descriptors[i] && strcmp(reg->descriptors[i]->name, name) == 0) {
            return reg->descriptors[i];
        }
    }
    return NULL;
}

// ── Execution ────────────────────────────────────────────────────────────

cos_status_t cos_plugin_execute(cos_plugin_registry_t* reg,
                                 const char* name,
                                 const void* input,
                                 size_t input_size,
                                 void** output,
                                 size_t* output_size) {
    const cos_plugin_descriptor_t* desc = cos_plugin_get(reg, name);
    if (!desc) return COS_ERROR_NOT_FOUND;
    if (!desc->execute) return COS_ERROR_STATE;

    // Find instance
    void* instance = NULL;
    for (size_t i = 0; i < reg->count; i++) {
        if (reg->descriptors[i] == desc) {
            instance = reg->instances[i];
            break;
        }
    }

    return desc->execute(instance, input, input_size, output, output_size);
}

// ── Introspection ────────────────────────────────────────────────────────

size_t cos_plugin_count(const cos_plugin_registry_t* reg) {
    return reg ? reg->count : 0;
}

#ifdef __cplusplus
}
#endif
