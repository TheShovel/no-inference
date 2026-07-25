# src/conversation/CMakeLists.txt
# Conversation engine.

add_library(cos_conversation STATIC
    conversation.c
)

target_include_directories(cos_conversation PUBLIC ${COS_INCLUDE_DIR})
target_link_libraries(cos_conversation PUBLIC
    cos_core cos_semantic cos_planner cos_reasoning
    cos_knowledge cos_parser cos_language cos_generator cos_memory cos_string)
target_compile_features(cos_conversation PUBLIC c_std_17)
