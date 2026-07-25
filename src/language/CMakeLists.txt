# src/language/CMakeLists.txt
# Language generation engine.

add_library(cos_language STATIC
    language.c
)

target_include_directories(cos_language PUBLIC ${COS_INCLUDE_DIR})
target_link_libraries(cos_language PUBLIC cos_core cos_semantic cos_memory cos_string)
target_compile_features(cos_language PUBLIC c_std_17)
