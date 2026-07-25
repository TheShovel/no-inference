# src/generator/CMakeLists.txt
# Text generator.

add_library(cos_generator STATIC
    generator.c
)

target_include_directories(cos_generator PUBLIC ${COS_INCLUDE_DIR})
target_link_libraries(cos_generator PUBLIC cos_core cos_semantic cos_memory cos_string)
target_compile_features(cos_generator PUBLIC c_std_17)
