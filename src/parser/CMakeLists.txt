# src/parser/CMakeLists.txt
# Semantic parser engine.

add_library(cos_parser STATIC
    parser.c
    tokenizer.c
)

target_include_directories(cos_parser PUBLIC ${COS_INCLUDE_DIR})
target_link_libraries(cos_parser PUBLIC cos_core cos_semantic cos_string cos_memory)
target_compile_features(cos_parser PUBLIC c_std_17)
