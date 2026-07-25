# src/memory/CMakeLists.txt
# Memory allocator implementations — arena, pool, stack.

add_library(cos_memory STATIC
    arena.c
    pool.c
    stack_alloc.c
)

target_include_directories(cos_memory PUBLIC ${COS_INCLUDE_DIR})
target_link_libraries(cos_memory PUBLIC cos_core)
target_compile_features(cos_memory PUBLIC c_std_17)
