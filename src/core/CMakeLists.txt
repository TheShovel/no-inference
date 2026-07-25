# src/core/CMakeLists.txt
# Core utility library — fundamental types, hashing, platform abstractions.

add_library(cos_core STATIC
    core.c
    hash.c
    sys_alloc.c
)

target_include_directories(cos_core PUBLIC ${COS_INCLUDE_DIR})
target_compile_features(cos_core PUBLIC c_std_17)
