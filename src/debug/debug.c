// debug.c — Built-in Debugger Implementation
//
// Design: Ring buffer of debug events. Each subsystem logs events
// without memory allocation (events are small fixed-size structs).
// Snapshots collect system-wide metrics.
//
// Memory: Pre-allocated ring buffer — zero allocations during logging.
// Snapshot structs are stack-allocated.

#include "cos/core.h"
#include "cos/debug.h"
#include "cos/semantic.h"
#include "cos/planner.h"
#include "cos/allocator.h"
#include <string.h>
#include <stdalign.h>
#include <stdio.h>
#include <stdarg.h>

#ifdef __cplusplus
extern "C" {
#endif

// ── Debug Context ────────────────────────────────────────────────────────
struct cos_debug_s {
    cos_allocator_t*    alloc;
    cos_debug_event_t*  events;
    size_t              event_capacity;
    size_t              event_count;
    size_t              event_head;     // Next write position (ring buffer)

    bool                enable_profiling;
    bool                enable_allocs;

    // Profiling counters
    size_t              total_events_dropped;
};

// ── Lifecycle ────────────────────────────────────────────────────────────

cos_debug_t* cos_debug_create(const cos_debug_config_t* config) {
    if (!config) return NULL;

    cos_debug_t* dbg = (cos_debug_t*)
        config->allocator->alloc(config->allocator, sizeof(cos_debug_t), alignof(cos_debug_t));
    if (!dbg) return NULL;

    size_t max_events = config->max_events > 0 ? config->max_events : 1024;

    dbg->events = (cos_debug_event_t*)
        config->allocator->alloc(config->allocator,
            max_events * sizeof(cos_debug_event_t), alignof(cos_debug_event_t));
    if (!dbg->events) {
        config->allocator->free(config->allocator, dbg, sizeof(cos_debug_t));
        return NULL;
    }

    dbg->alloc         = config->allocator;
    dbg->event_capacity = max_events;
    dbg->event_count   = 0;
    dbg->event_head    = 0;
    dbg->enable_profiling = config->enable_profiling;
    dbg->enable_allocs    = config->enable_allocs;
    dbg->total_events_dropped = 0;

    return dbg;
}

void cos_debug_destroy(cos_debug_t* dbg) {
    if (!dbg) return;
    if (dbg->events) dbg->alloc->free(dbg->alloc, dbg->events,
        dbg->event_capacity * sizeof(cos_debug_event_t));
    dbg->alloc->free(dbg->alloc, dbg, sizeof(cos_debug_t));
}

// ── Event Logging ────────────────────────────────────────────────────────

void cos_debug_log(cos_debug_t* dbg, cos_debug_event_type_t type, const char* subsystem, const char* message) {
    if (!dbg) return;

    cos_debug_event_t* evt = &dbg->events[dbg->event_head];
    evt->type           = type;
    evt->timestamp      = cos_timestamp_now();
    evt->subsystem      = subsystem;
    evt->message        = message;
    evt->message_length = message ? strlen(message) : 0;
    evt->context_data   = NULL;
    evt->context_size   = 0;

    dbg->event_head = (dbg->event_head + 1) % dbg->event_capacity;
    if (dbg->event_count < dbg->event_capacity) {
        dbg->event_count++;
    } else {
        dbg->total_events_dropped++;
    }
}

void cos_debug_log_fmt(cos_debug_t* dbg, cos_debug_event_type_t type, const char* subsystem, const char* fmt, ...) {
    if (!dbg || !fmt) return;

    char buffer[256];
    va_list args;
    va_start(args, fmt);
    vsnprintf(buffer, sizeof(buffer), fmt, args);
    va_end(args);

    cos_debug_log(dbg, type, subsystem, buffer);
}

// ── Snapshot ─────────────────────────────────────────────────────────────

cos_status_t cos_debug_snapshot(const cos_debug_t* dbg, cos_debug_snapshot_t* out_snapshot) {
    if (!dbg || !out_snapshot) return COS_ERROR_NULL;

    memset(out_snapshot, 0, sizeof(cos_debug_snapshot_t));
    out_snapshot->cpu_time_ms         = 0.0f;
    out_snapshot->cache_hit_rate      = 0.0f;
    out_snapshot->interned_strings    = 0;
    out_snapshot->alloc_count         = dbg->event_count;
    out_snapshot->ram_used            = dbg->event_capacity * sizeof(cos_debug_event_t);

    return COS_OK;
}

// ── Display ──────────────────────────────────────────────────────────────

void cos_debug_print_semantic_graph(const cos_semantic_graph_t* graph, FILE* output) {
    if (!graph || !output) return;
    fprintf(output, "=== Semantic Graph ===\n");
    fprintf(output, "  Root: %u\n", (unsigned int)cos_semantic_root(graph));
    // In a full implementation, iterate all nodes and edges
    fprintf(output, "  (graph dump requires full node iteration)\n");
}

void cos_debug_print_plan(const cos_plan_t* plan, FILE* output) {
    if (!plan || !output) return;
    fprintf(output, "=== Execution Plan ===\n");
    fprintf(output, "  Steps: %zu\n", plan->step_count);
    fprintf(output, "  Confidence: %.2f\n", plan->confidence);
    for (size_t i = 0; i < plan->step_count; i++) {
        fprintf(output, "  [%zu] %s (priority: %u)\n",
                i, cos_plan_step_type_name(plan->steps[i].type),
                (unsigned int)plan->steps[i].priority);
    }
}

void cos_debug_print_snapshot(const cos_debug_snapshot_t* snapshot, FILE* output) {
    if (!snapshot || !output) return;
    fprintf(output, "=== System Snapshot ===\n");
    fprintf(output, "  RAM used:    %zu bytes\n", snapshot->ram_used);
    fprintf(output, "  RAM peak:    %zu bytes\n", snapshot->ram_peak);
    fprintf(output, "  Allocations: %zu\n", snapshot->alloc_count);
    fprintf(output, "  Arenas:      %zu\n", snapshot->arena_count);
    fprintf(output, "  Pools:       %zu\n", snapshot->pool_count);
    fprintf(output, "  CPU time:    %.2f ms\n", snapshot->cpu_time_ms);
    fprintf(output, "  Cache hit:   %.1f%%\n", snapshot->cache_hit_rate * 100.0f);
    fprintf(output, "  Knowledge:   %zu facts\n", snapshot->knowledge_facts);
    fprintf(output, "  Turns:       %zu\n", snapshot->conversation_turns);
    fprintf(output, "  Interned:    %zu strings\n", snapshot->interned_strings);
}

void cos_debug_print_events(const cos_debug_t* dbg, FILE* output, size_t max_events) {
    if (!dbg || !output) return;
    fprintf(output, "=== Debug Events ===\n");

    size_t start = 0;
    size_t count = dbg->event_count;

    if (max_events > 0 && count > max_events) {
        start = count - max_events;
        count = max_events;
    }

    for (size_t i = 0; i < count; i++) {
        size_t idx = (dbg->event_head + i) % dbg->event_capacity;
        const cos_debug_event_t* evt = &dbg->events[idx];
        fprintf(output, "  [%zu] %lld %s: %s\n",
                i, (long long)evt->timestamp,
                evt->subsystem ? evt->subsystem : "?",
                evt->message ? evt->message : "");
    }
}

size_t cos_debug_event_count(const cos_debug_t* dbg) {
    return dbg ? dbg->event_count : 0;
}

const cos_debug_event_t* cos_debug_get_event(const cos_debug_t* dbg, size_t index) {
    if (!dbg || index >= dbg->event_count) return NULL;
    size_t idx = (dbg->event_head + index) % dbg->event_capacity;
    return &dbg->events[idx];
}

#ifdef __cplusplus
}
#endif
