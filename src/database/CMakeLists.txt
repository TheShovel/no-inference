# src/database/CMakeLists.txt
# Database abstraction layer.

add_library(cos_database STATIC
    database.c
)

target_include_directories(cos_database PUBLIC ${COS_INCLUDE_DIR})
target_link_libraries(cos_database PUBLIC cos_core cos_memory)
target_compile_features(cos_database PUBLIC c_std_17)
