// plugins.h — Plugin System
//
// Design: Everything is replaceable via plugins. Each plugin registers
// itself with the plugin registry. The planner discovers available
// plugins automatically.
//
// A plugin is a shared library (or compiled-in module) that exposes
// a standard C interface.
//
// Memory: Plugin descriptors are small fixed-size structs.
// Plugins share the runtime's allocator and string table.

#ifndef COS_PLUGINS_H
#define COS_PLUGINS_H

#include "cos/core.h"
#include "cos/allocator.h"
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

// ── Plugin Capabilities ──────────────────────────────────────────────────
typedef uint32_t cos_plugin_capability_t;

enum {
    COS_PLUGIN_SEARCH      = 1 << 0,
    COS_PLUGIN_DATABASE    = 1 << 1,
    COS_PLUGIN_FILESYSTEM  = 1 << 2,
    COS_PLUGIN_MATH        = 1 << 3,
    COS_PLUGIN_WEB         = 1 << 4,
    COS_PLUGIN_IMAGE       = 1 << 5,
    COS_PLUGIN_CODE        = 1 << 6,
    COS_PLUGIN_CUSTOM      = (int)0x80000000,
};

// ── Plugin Descriptor ────────────────────────────────────────────────────
typedef struct cos_plugin_descriptor_s {
    const char*            name;
    const char*            version;
    cos_plugin_capability_t capabilities;
    void*                  (*create)(cos_allocator_t* alloc);
    void                   (*destroy)(void* instance);
    cos_status_t           (*execute)(void* instance, const void* input, size_t input_size, void** output, size_t* output_size);
} cos_plugin_descriptor_t;

// ── Opaque Plugin Registry ───────────────────────────────────────────────
typedef struct cos_plugin_registry_s cos_plugin_registry_t;

// ── Lifecycle ────────────────────────────────────────────────────────────
cos_plugin_registry_t* cos_plugin_registry_create(cos_allocator_t* alloc);
void                   cos_plugin_registry_destroy(cos_plugin_registry_t* reg);

// ── Registration ─────────────────────────────────────────────────────────
cos_status_t cos_plugin_register(cos_plugin_registry_t* reg, const cos_plugin_descriptor_t* descriptor);
cos_status_t cos_plugin_unregister(cos_plugin_registry_t* reg, const char* name);

// ── Discovery ────────────────────────────────────────────────────────────
size_t cos_plugin_find(const cos_plugin_registry_t* reg, cos_plugin_capability_t capabilities, const char*** out_names, size_t max_results);
const cos_plugin_descriptor_t* cos_plugin_get(const cos_plugin_registry_t* reg, const char* name);

// ── Execution ────────────────────────────────────────────────────────────
cos_status_t cos_plugin_execute(cos_plugin_registry_t* reg, const char* name, const void* input, size_t input_size, void** output, size_t* output_size);

// ── Introspection ────────────────────────────────────────────────────────
size_t cos_plugin_count(const cos_plugin_registry_t* reg);

#ifdef __cplusplus
}
#endif

#endif // COS_PLUGINS_H
