# src/benchmark/CMakeLists.txt
# Benchmarks and performance tests.

add_executable(cos_benchmark
    benchmark.c
)

target_include_directories(cos_benchmark PUBLIC ${COS_INCLUDE_DIR})
target_link_libraries(cos_benchmark PRIVATE
    cos_core cos_memory cos_string cos_graph cos_semantic
    cos_parser cos_planner cos_reasoning cos_knowledge
    cos_conversation cos_debug)
target_compile_features(cos_benchmark PUBLIC c_std_17)

add_executable(cos_bench
    cos_bench.c
)

target_include_directories(cos_bench PUBLIC ${COS_INCLUDE_DIR})
target_link_libraries(cos_bench PRIVATE
    cos_core cos_memory cos_string cos_graph cos_semantic
    cos_parser cos_planner cos_reasoning cos_knowledge
    cos_language cos_generator cos_conversation cos_debug
    cos_tools)
target_compile_features(cos_bench PUBLIC c_std_17)

add_executable(cos_bench_runner
    bench_runner.c
)

target_include_directories(cos_bench_runner PUBLIC ${COS_INCLUDE_DIR})
target_link_libraries(cos_bench_runner PRIVATE
    cos_core cos_memory cos_string cos_graph cos_semantic
    cos_parser cos_planner cos_reasoning cos_knowledge
    cos_language cos_generator cos_conversation cos_debug
    cos_template_matcher cos_fact_lookup)
target_compile_features(cos_bench_runner PUBLIC c_std_17)
