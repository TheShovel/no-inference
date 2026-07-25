# src/knowledge/CMakeLists.txt
# Knowledge base interface.

add_library(cos_knowledge STATIC
    knowledge.c
)

target_include_directories(cos_knowledge PUBLIC ${COS_INCLUDE_DIR})
target_link_libraries(cos_knowledge PUBLIC cos_core cos_semantic cos_memory cos_string)
target_compile_features(cos_knowledge PUBLIC c_std_17)
