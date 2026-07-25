# src/planner/CMakeLists.txt
# Execution planner.

add_library(cos_planner STATIC
    planner.c
)

target_include_directories(cos_planner PUBLIC ${COS_INCLUDE_DIR})
target_link_libraries(cos_planner PUBLIC cos_core cos_semantic cos_string cos_memory)
target_compile_features(cos_planner PUBLIC c_std_17)
