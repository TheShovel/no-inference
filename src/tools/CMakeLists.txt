# src/tools/CMakeLists.txt
# Tool system.

add_library(cos_tools STATIC
    tools.c
    builtin_tools.c
    math_tool.c
)

target_include_directories(cos_tools PUBLIC ${COS_INCLUDE_DIR})
target_link_libraries(cos_tools PUBLIC cos_core cos_memory m)
target_compile_features(cos_tools PUBLIC c_std_17)
