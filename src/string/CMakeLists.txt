# src/string/CMakeLists.txt
# String interning library.

add_library(cos_string STATIC
    string_intern.c
)

target_include_directories(cos_string PUBLIC ${COS_INCLUDE_DIR})
target_link_libraries(cos_string PUBLIC cos_core cos_memory)
target_compile_features(cos_string PUBLIC c_std_17)
