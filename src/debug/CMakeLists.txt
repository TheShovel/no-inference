# src/debug/CMakeLists.txt
# Built-in debugger and introspection system.

add_library(cos_debug STATIC
    debug.c
)

target_include_directories(cos_debug PUBLIC ${COS_INCLUDE_DIR})
target_link_libraries(cos_debug PUBLIC cos_core cos_semantic cos_planner cos_memory)
target_compile_features(cos_debug PUBLIC c_std_17)
