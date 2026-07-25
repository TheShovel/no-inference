# CMakeLists.txt - Conversation Operating System (COS)
# Build system root
#
# Design: Minimal, modular, C17. Every subsystem compiles independently.
# Each module is a static library to enable linker-level dead code elimination.

cmake_minimum_required(VERSION 3.16)
project(cos
    VERSION 0.1.0
    DESCRIPTION "Conversation Operating System - A symbolic conversational AI runtime"
    LANGUAGES C
)

# ── C Standard ──────────────────────────────────────────────────────────────
set(CMAKE_C_STANDARD 17)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

# ── Build Configuration ─────────────────────────────────────────────────────
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

# Strict warnings
if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
    add_compile_options(
        -Wall -Wextra -Wpedantic
        -Wshadow -Wconversion -Wdouble-promotion
        -Wformat=2 -Wundef -Wstrict-prototypes
        -Wmissing-prototypes -Wmissing-declarations
        -Wcast-qual -Wwrite-strings
        -Werror=vla
    )
    if(CMAKE_BUILD_TYPE MATCHES "Debug|RelWithDebInfo")
        add_compile_options(-g3 -O0 -fno-omit-frame-pointer -fsanitize=address)
        add_link_options(-fsanitize=address)
    else()
        add_compile_options(-O2 -DNDEBUG)
    endif()
endif()

# ── Global Include Paths ────────────────────────────────────────────────────
set(COS_INCLUDE_DIR "${CMAKE_SOURCE_DIR}/include")
include_directories(${COS_INCLUDE_DIR})

# ── Subsystem Libraries ─────────────────────────────────────────────────────
# Each subsystem builds as a static library with a clean C API.
# Order matters: core is first, everything depends on it.

add_subdirectory(src/core)
add_subdirectory(src/memory)
add_subdirectory(src/string)
add_subdirectory(src/graph)
add_subdirectory(src/semantic)
add_subdirectory(src/parser)
add_subdirectory(src/planner)
add_subdirectory(src/reasoning)
add_subdirectory(src/knowledge)
add_subdirectory(src/language)
add_subdirectory(src/grammar)
add_subdirectory(src/generator)
add_subdirectory(src/tools)
add_subdirectory(src/plugins)
add_subdirectory(src/database)
add_subdirectory(src/conversation)
add_subdirectory(src/debug)
add_subdirectory(src/knowledge_loader)

# ── Main Executable ─────────────────────────────────────────────────────────
add_subdirectory(src/benchmark)

if(COS_BUILD_TESTS OR CMAKE_BUILD_TYPE MATCHES "Debug")
    enable_testing()
    add_subdirectory(tests)
endif()

# ── Convenience Target ──────────────────────────────────────────────────────
add_executable(cos_main src/main.c)
target_link_libraries(cos_main
    PRIVATE
    cos_conversation
    cos_debug
    cos_plugins
    cos_tools
    cos_generator
    cos_grammar
    cos_language
    cos_reasoning
    cos_knowledge
    cos_planner
    cos_parser
    cos_semantic
    cos_graph
    cos_string
    cos_memory
    cos_core
    cos_template_matcher
)

# ── Install Rules ───────────────────────────────────────────────────────────
install(TARGETS cos_main DESTINATION bin)
install(DIRECTORY include/cos DESTINATION include)
