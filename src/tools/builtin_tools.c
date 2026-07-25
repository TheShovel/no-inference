// builtin_tools.c — Built-in Tool Implementations
//
// Design: Tools that ship with COS by default.
// Each tool is a simple function matching the cos_tool_t::execute signature.

#include "cos/core.h"
#include "cos/tools.h"
#include <string.h>
#include <stdio.h>

// ── Help Tool ────────────────────────────────────────────────────────────
static cos_status_t help_execute(const cos_tool_t* tool,
                                  const char* args,
                                  size_t args_length,
                                  char* out_buffer,
                                  size_t buffer_size,
                                  size_t* out_written) {
    (void)tool;
    (void)args;
    (void)args_length;

    const char* help_text =
        "COS - Conversation Operating System\n"
        "Available commands:\n"
        "  help    - Show this help\n"
        "  status  - Show system status\n"
        "  memory  - Show memory usage\n"
        "  debug   - Toggle debug mode\n";

    size_t len = strlen(help_text);
    size_t to_copy = len < buffer_size - 1 ? len : buffer_size - 1;
    memcpy(out_buffer, help_text, to_copy);
    out_buffer[to_copy] = '\0';
    *out_written = to_copy;
    return COS_OK;
}

static const cos_tool_t g_help_tool = {
    .name        = "help",
    .description = "Show available commands and help information",
    .execute     = help_execute,
    .context     = NULL,
};

// ── Status Tool ──────────────────────────────────────────────────────────
static cos_status_t status_execute(const cos_tool_t* tool,
                                    const char* args,
                                    size_t args_length,
                                    char* out_buffer,
                                    size_t buffer_size,
                                    size_t* out_written) {
    (void)tool;
    (void)args;
    (void)args_length;

    int n = snprintf(out_buffer, buffer_size,
                     "COS v%d.%d.%d\nStatus: Running\n",
                     COS_VERSION_MAJOR, COS_VERSION_MINOR, COS_VERSION_PATCH);
    if (n < 0) n = 0;
    *out_written = (size_t)n < buffer_size ? (size_t)n : buffer_size - 1;
    out_buffer[*out_written] = '\0';
    return COS_OK;
}

static const cos_tool_t g_status_tool = {
    .name        = "status",
    .description = "Show COS system status",
    .execute     = status_execute,
    .context     = NULL,
};

// ── Built-in Tool Registration ───────────────────────────────────────────

cos_status_t cos_register_builtin_tools(cos_tool_registry_t* reg) {
    cos_status_t s;
    s = cos_tool_register(reg, &g_help_tool);
    if (s != COS_OK) return s;
    s = cos_tool_register(reg, &g_status_tool);
    return s;
}
