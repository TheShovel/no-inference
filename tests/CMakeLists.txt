# tests/CMakeLists.txt
# Unit tests for all subsystems.

add_executable(cos_test_core
    test_core.c
)
target_link_libraries(cos_test_core PRIVATE cos_core)
target_compile_features(cos_test_core PUBLIC c_std_17)
add_test(NAME test_core COMMAND cos_test_core)

add_executable(cos_test_memory
    test_memory.c
)
target_link_libraries(cos_test_memory PRIVATE cos_core cos_memory)
target_compile_features(cos_test_memory PUBLIC c_std_17)
add_test(NAME test_memory COMMAND cos_test_memory)

add_executable(cos_test_string
    test_string.c
)
target_link_libraries(cos_test_string PRIVATE cos_core cos_memory cos_string)
target_compile_features(cos_test_string PUBLIC c_std_17)
add_test(NAME test_string COMMAND cos_test_string)

add_executable(cos_test_graph
    test_graph.c
)
target_link_libraries(cos_test_graph PRIVATE cos_core cos_memory cos_graph)
target_compile_features(cos_test_graph PUBLIC c_std_17)
add_test(NAME test_graph COMMAND cos_test_graph)

add_executable(cos_test_parser
    test_parser.c
)
target_link_libraries(cos_test_parser PRIVATE
    cos_core cos_memory cos_string cos_graph cos_semantic cos_parser)
target_compile_features(cos_test_parser PUBLIC c_std_17)
add_test(NAME test_parser COMMAND cos_test_parser)

add_executable(cos_test_conversation
    test_conversation.c
)
target_link_libraries(cos_test_conversation PRIVATE
    cos_core cos_memory cos_string cos_graph cos_semantic cos_parser
    cos_planner cos_reasoning cos_knowledge cos_language cos_generator cos_conversation)
target_compile_features(cos_test_conversation PUBLIC c_std_17)
add_test(NAME test_conversation COMMAND cos_test_conversation)
