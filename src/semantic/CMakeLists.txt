# src/semantic/CMakeLists.txt
# Semantic graph layer.

add_library(cos_semantic STATIC
    semantic.c
)

target_include_directories(cos_semantic PUBLIC ${COS_INCLUDE_DIR})
target_link_libraries(cos_semantic PUBLIC cos_core cos_graph cos_string)
target_compile_features(cos_semantic PUBLIC c_std_17)
