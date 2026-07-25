# src/graph/CMakeLists.txt
# Generic graph engine.

add_library(cos_graph STATIC
    graph.c
)

target_include_directories(cos_graph PUBLIC ${COS_INCLUDE_DIR})
target_link_libraries(cos_graph PUBLIC cos_core cos_memory)
target_compile_features(cos_graph PUBLIC c_std_17)
