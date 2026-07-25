// tools.h - Tool System
//
// Design: Tools are actions the runtime can perform on behalf of the user.
// Each tool has a name, description, input schema, and execute function.
//
// Unlike plugins (which extend the runtime), tools are user-facing actions:
//   - Search the web
//   - Read a file
//   - Calculate math
//   - Run code
//
// Memory: Tool definitions are static. Inputs/outputs use caller-provided buffers.

#ifndef COS_TOOLS_H
#define COS_TOOLS_H

#include "cos/core.h"
#include "cos/allocator.h"
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

// -- Tool execute function type (forward declaration needed for self-reference)
typedef struct cos_tool_s cos_tool_t;
typedef cos_status_t (*cos_tool_execute_fn_t)(const cos_tool_t* tool, const char* args, size_t args_length, char* out_buffer, size_t buffer_size, size_t* out_written);

// -- Tool Definition --------------------------------------------------------
struct cos_tool_s {
    const char*          name;
    const char*          description;
    cos_tool_execute_fn_t execute;
    void*                context;  // Tool-specific state
};

// -- Opaque Tool Registry ---------------------------------------------------
typedef struct cos_tool_registry_s cos_tool_registry_t;

// -- Lifecycle --------------------------------------------------------------
cos_tool_registry_t* cos_tool_registry_create(cos_allocator_t* alloc);
void                 cos_tool_registry_destroy(cos_tool_registry_t* reg);

// -- Registration -----------------------------------------------------------
cos_status_t cos_tool_register(cos_tool_registry_t* reg, const cos_tool_t* tool);
cos_status_t cos_tool_unregister(cos_tool_registry_t* reg, const char* name);

// -- Discovery & Execution --------------------------------------------------
const cos_tool_t* cos_tool_find(const cos_tool_registry_t* reg, const char* name);
cos_status_t      cos_tool_execute(const cos_tool_registry_t* reg, const char* name, const char* args, size_t args_length, char* out_buffer, size_t buffer_size, size_t* out_written);

// -- Built-in tools registration --------------------------------------------
cos_status_t cos_register_builtin_tools(cos_tool_registry_t* reg);
cos_status_t cos_register_math_tool(cos_tool_registry_t* reg);

// -- Introspection ----------------------------------------------------------
size_t cos_tool_count(const cos_tool_registry_t* reg);
// Get a pointer to the tool at index. Returns NULL if out of range.
const cos_tool_t* cos_tool_get(const cos_tool_registry_t* reg, size_t index);

#ifdef __cplusplus
}
#endif

#endif // COS_TOOLS_H
