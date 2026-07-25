// core.c — Core Utilities Implementation
//
// This file provides basic runtime support functions.
// Kept under 300 lines per project style guide.

#define _POSIX_C_SOURCE 199309L

#include "cos/core.h"
#include <string.h>
#include <stdio.h>
#include <stdarg.h>

// ── Status Code Descriptions ─────────────────────────────────────────────

const char* cos_status_string(cos_status_t status) {
    switch (status) {
        case COS_OK:                return "OK";
        case COS_ERROR_NOMEM:       return "Out of memory";
        case COS_ERROR_NULL:        return "NULL pointer provided";
        case COS_ERROR_INVALID_ARG: return "Invalid argument";
        case COS_ERROR_NOT_FOUND:   return "Not found";
        case COS_ERROR_EXISTS:      return "Already exists";
        case COS_ERROR_BOUNDS:      return "Out of bounds";
        case COS_ERROR_EMPTY:       return "Collection is empty";
        case COS_ERROR_FULL:        return "Collection is full";
        case COS_ERROR_IO:          return "I/O error";
        case COS_ERROR_PARSE:       return "Parse error";
        case COS_ERROR_TYPE:        return "Type mismatch";
        case COS_ERROR_STATE:       return "Invalid state";
        case COS_ERROR_NOT_IMPL:    return "Not implemented";
        default: {
            if (status < 0) return "Unknown error";
            return "OK";
        }
    }
}

// ── Timestamp ────────────────────────────────────────────────────────────

#if defined(_WIN32)
#include <windows.h>
cos_timestamp_t cos_timestamp_now(void) {
    FILETIME ft;
    GetSystemTimePreciseAsFileTime(&ft);
    ULARGE_INTEGER li;
    li.LowPart  = ft.dwLowDateTime;
    li.HighPart = ft.dwHighDateTime;
    // Convert from 100-ns intervals to ms since epoch
    return (cos_timestamp_t)((li.QuadPart - 116444736000000000ULL) / 10000);
}
#elif defined(__linux__) || defined(__unix__)
#include <time.h>
cos_timestamp_t cos_timestamp_now(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (cos_timestamp_t)(ts.tv_sec * 1000) + (cos_timestamp_t)(ts.tv_nsec / 1000000);
}
#else
#include <time.h>
cos_timestamp_t cos_timestamp_now(void) {
    time_t s = time(NULL);
    return (cos_timestamp_t)s * 1000;
}
#endif

// ── Logging ──────────────────────────────────────────────────────────────

void cos_log(cos_status_t level, const char* subsystem, const char* format, ...) {
    (void)level;
    (void)subsystem;
    (void)format;
    // Stub: will be connected to the debug system
}
