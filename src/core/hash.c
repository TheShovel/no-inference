// hash.c — Hash Functions
//
// Design: Fast, deterministic hash functions for use throughout COS.
// FNV-1a for strings (already in string_view.h inline).
// Murmur3-style for general data.
//
// These are NOT cryptographic — they are for hash tables and dedup.

#include "cos/core.h"
#include "cos/hash.h"
#include <string.h>

// ── FNV-1a (for variable-length data) ────────────────────────────────────

cos_hash_t cos_hash_data(const void* data, size_t length) {
    cos_hash_t hash = 14695981039346656037ULL;
    const unsigned char* bytes = (const unsigned char*)data;
    for (size_t i = 0; i < length; i++) {
        hash ^= bytes[i];
        hash *= 1099511628211ULL;
    }
    return hash;
}

// ── Combine two hashes ───────────────────────────────────────────────────

cos_hash_t cos_hash_combine(cos_hash_t h1, cos_hash_t h2) {
    // Bob Jenkins' hash combining
    h1 ^= h2 + 0x9e3779b9 + (h1 << 6) + (h1 >> 2);
    return h1;
}

// ── Identity hash (for integer keys) ─────────────────────────────────────

cos_hash_t cos_hash_identity(uint64_t key) {
    // Thomas Wang's integer hash
    key = (~key) + (key << 21);
    key ^= key >> 24;
    key += (key << 3) + (key << 8);
    key ^= key >> 14;
    key += (key << 2) + (key << 4);
    key ^= key >> 28;
    key += (key << 31);
    return (cos_hash_t)key;
}
