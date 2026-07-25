# src/knowledge_loader/CMakeLists.txt
# Dataset-to-Knowledge-Base importer.

add_library(cos_template_matcher STATIC
    template_matcher.c
)

target_include_directories(cos_template_matcher PUBLIC ${COS_INCLUDE_DIR})
target_link_libraries(cos_template_matcher PUBLIC cos_core cos_memory cos_string)
target_compile_features(cos_template_matcher PUBLIC c_std_17)

add_executable(cos_knowledge_loader
    knowledge_loader.c
)

target_include_directories(cos_knowledge_loader PUBLIC ${COS_INCLUDE_DIR})
target_link_libraries(cos_knowledge_loader PRIVATE
    cos_core cos_memory cos_string cos_graph cos_semantic
    cos_parser cos_knowledge cos_conversation)
target_compile_features(cos_knowledge_loader PUBLIC c_std_17)

add_library(cos_fact_lookup STATIC
    fact_lookup.c
)

target_include_directories(cos_fact_lookup PUBLIC ${COS_INCLUDE_DIR})
target_link_libraries(cos_fact_lookup PUBLIC cos_core)
target_compile_features(cos_fact_lookup PUBLIC c_std_17)
