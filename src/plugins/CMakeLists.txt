# src/plugins/CMakeLists.txt
# Plugin system.

add_library(cos_plugins STATIC
    plugins.c
)

target_include_directories(cos_plugins PUBLIC ${COS_INCLUDE_DIR})
target_link_libraries(cos_plugins PUBLIC cos_core cos_memory)
target_compile_features(cos_plugins PUBLIC c_std_17)
