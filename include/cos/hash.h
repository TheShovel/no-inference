// hash.h — COS Hash Functions
//
// Public declarations for hash functions used across the runtime.

#ifndef COS_HASH_H
#define COS_HASH_H

#include "cos/core.h"
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// FNV-1a hash for arbitrary binary data.
cos_hash_t cos_hash_data(const void* data, size_t length);

// Combine two hashes (Bob Jenkins-style).
cos_hash_t cos_hash_combine(cos_hash_t h1, cos_hash_t h2);

// Identity hash for integer keys (Thomas Wang's integer hash).
cos_hash_t cos_hash_identity(uint64_t key);

#ifdef __cplusplus
}
#endif

#endif // COS_HASH_H
