# src/grammar/CMakeLists.txt
# Grammar engine.

add_library(cos_grammar STATIC
    grammar.c
)

target_include_directories(cos_grammar PUBLIC ${COS_INCLUDE_DIR})
target_link_libraries(cos_grammar PUBLIC cos_core cos_memory cos_string)
target_compile_features(cos_grammar PUBLIC c_std_17)
