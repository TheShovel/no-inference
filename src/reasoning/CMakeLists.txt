# src/reasoning/CMakeLists.txt
# Symbolic reasoning engine.

add_library(cos_reasoning STATIC
    reasoning.c
    logic.c
    math.c
    temporal.c
)

target_include_directories(cos_reasoning PUBLIC ${COS_INCLUDE_DIR})
target_link_libraries(cos_reasoning PUBLIC cos_core cos_semantic cos_knowledge cos_memory)
target_compile_features(cos_reasoning PUBLIC c_std_17)
