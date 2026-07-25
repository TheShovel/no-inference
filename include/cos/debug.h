// debug.h — Built-in Debugger
//
// Design: Every subsystem can be introspected at runtime.
// The debug engine collects and displays:
//   - Semantic graph state
//   - Planner decisions
//   - Knowledge lookups
//   - Memory allocator state
//   - Reasoning chains
//   - Sentence plans
//   - Timing and CPU usage
//   - RAM usage and cache hit rates
//
// All debug information is opt-in per subsystem and incurs zero
// overhead when disabled (compile-time flag).

#ifndef COS_DEBUG_H
#define COS_DEBUG_H

#include "cos/core.h"
#include "cos/semantic.h"
#include "cos/planner.h"
#include "cos/allocator.h"
#include <stddef.h>
#include <stdio.h>

#ifdef __cplusplus
extern "C" {
#endif

// ── Debug Event Types ────────────────────────────────────────────────────
typedef enum {
    COS_DEBUG_PARSE        = 0,
    COS_DEBUG_PLAN         = 1,
    COS_DEBUG_REASON       = 2,
    COS_DEBUG_KNOWLEDGE    = 3,
    COS_DEBUG_MEMORY       = 4,
    COS_DEBUG_GENERATE     = 5,
    COS_DEBUG_TOOL         = 6,
    COS_DEBUG_PLUGIN       = 7,
    COS_DEBUG_ALLOC        = 8,
} cos_debug_event_type_t;

// ── Debug Event ─────────────────────────────────────────────────────────
typedef struct cos_debug_event_s {
    cos_debug_event_type_t type;
    cos_timestamp_t   timestamp;
    const char*       subsystem;
    const char*       message;
    size_t            message_length;
    void*             context_data;   // Event-specific data
    size_t            context_size;
} cos_debug_event_t;

// ── Debug Snapshot ───────────────────────────────────────────────────────
typedef struct cos_debug_snapshot_s {
    size_t   ram_used;
    size_t   ram_peak;
    size_t   alloc_count;
    size_t   arena_count;
    size_t   pool_count;
    float    cpu_time_ms;
    float    cache_hit_rate;  // 0.0–1.0
    size_t   knowledge_facts;
    size_t   conversation_turns;
    size_t   interned_strings;
} cos_debug_snapshot_t;

// ── Opaque Debugger ──────────────────────────────────────────────────────
typedef struct cos_debug_s cos_debug_t;

typedef struct cos_debug_config_s {
    cos_allocator_t* allocator;
    size_t           max_events;   // Max events to keep in ring buffer
    bool             enable_profiling;
    bool             enable_allocs;
} cos_debug_config_t;

// ── Lifecycle ────────────────────────────────────────────────────────────
cos_debug_t* cos_debug_create(const cos_debug_config_t* config);
void         cos_debug_destroy(cos_debug_t* dbg);

// ── Event Logging ────────────────────────────────────────────────────────
void cos_debug_log(cos_debug_t* dbg, cos_debug_event_type_t type, const char* subsystem, const char* message);
void cos_debug_log_fmt(cos_debug_t* dbg, cos_debug_event_type_t type, const char* subsystem, const char* fmt, ...);

// ── Snapshot ─────────────────────────────────────────────────────────────
cos_status_t cos_debug_snapshot(const cos_debug_t* dbg, cos_debug_snapshot_t* out_snapshot);

// ── Display ──────────────────────────────────────────────────────────────
void cos_debug_print_semantic_graph(const cos_semantic_graph_t* graph, FILE* output);
void cos_debug_print_plan(const cos_plan_t* plan, FILE* output);
void cos_debug_print_snapshot(const cos_debug_snapshot_t* snapshot, FILE* output);
void cos_debug_print_events(const cos_debug_t* dbg, FILE* output, size_t max_events);

// ── Event Access ─────────────────────────────────────────────────────────
size_t cos_debug_event_count(const cos_debug_t* dbg);
const cos_debug_event_t* cos_debug_get_event(const cos_debug_t* dbg, size_t index);

#ifdef __cplusplus
}
#endif

#endif // COS_DEBUG_H
