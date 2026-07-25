// knowledge_loader.c - Dataset-to-Knowledge-Base Importer
//
// Reads TSV conversation data (pre-processed from JSONL) and extracts:
//   1. Facts -> knowledge base (subject-predicate-object triples)
//   2. Response templates (question/answer pairs)
//
// Input format (tab-separated, preprocessed by cos_preprocess.py):
//   role\tcontent
//   ---  (conversation separator)
//
// Usage: python3 cos_preprocess.py dataset.jsonl | ./cos_knowledge_loader /dev/stdin

#include "cos/core.h"
#include "cos/allocator.h"
#include "cos/arena.h"
#include "cos/string_intern.h"
#include "cos/string_view.h"
#include "cos/parser.h"
#include "cos/semantic.h"
#include "cos/knowledge.h"
#include "cos/string_view.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_LINE 262144

int main(int argc, char** argv) {
    const char* input_path = argc > 1 ? argv[1] : "/dev/stdin";
    const char* tmpl_path  = argc > 2 ? argv[2] : "cos_templates.txt";

    printf("COS Knowledge Loader v0.1.0\n");
    printf("  Input:  %s\n", input_path);
    printf("  Output: %s\n\n", tmpl_path);

    // Init COS runtime
    cos_allocator_t* sys      = cos_sys_allocator();
    cos_string_table_t* strings = cos_string_table_create(sys);
    cos_knowledge_base_t* kb  = cos_knowledge_create(sys);

    cos_parser_config_t pc;
    pc.string_table = strings;
    pc.allocator    = sys;
    pc.scratch      = NULL;
    cos_parser_t* parser = cos_parser_create(&pc);
    if (!parser) { fprintf(stderr, "Failed to create parser\n"); return 1; }

    FILE* f = fopen(input_path, "r");
    if (!f) { fprintf(stderr, "Cannot open: %s\n", input_path); return 1; }

    FILE* tmpl = fopen(tmpl_path, "w");
    if (!tmpl) { fprintf(stderr, "Cannot write: %s\n", tmpl_path); return 1; }

    fprintf(tmpl, "# COS Response Templates\n");
    fprintf(tmpl, "# Source: %s\n\n", input_path);

    // Read TSV: role TAB content, with --- as conversation separator
    char buf[MAX_LINE];
    size_t line_count = 0, fact_count = 0, template_count = 0;
    char last_user_content[16384] = {0};

    while (fgets(buf, sizeof(buf), f)) {
        line_count++;
        size_t len = strlen(buf);
        while (len > 0 && (buf[len-1] == '\n' || buf[len-1] == '\r')) buf[--len] = '\0';
        if (len == 0) continue;

        // Conversation separator
        if (len >= 3 && memcmp(buf, "---", 3) == 0) {
            last_user_content[0] = '\0';
            continue;
        }

        // Split on first tab
        char* tab = strchr(buf, '\t');
        if (!tab) continue;

        *tab = '\0';
        const char* role = buf;
        const char* content = tab + 1;

        // Normalize role names: human/user/User -> user, gpt/assistant/bot -> assistant
        bool is_user = (strcmp(role, "user") == 0 || strcmp(role, "human") == 0);
        bool is_assistant = (strcmp(role, "assistant") == 0 || strcmp(role, "gpt") == 0);

        if (is_user) {
            // Parse user input and extract facts
            strncpy(last_user_content, content, sizeof(last_user_content)-1);
            last_user_content[sizeof(last_user_content)-1] = '\0';

            cos_semantic_graph_t* graph = NULL;
            if (cos_parser_parse(parser, cos_sv_cstr(content), &graph) == COS_OK && graph) {
                cos_knowledge_store_graph(kb, graph);
                cos_semantic_destroy(graph);
            }

        } else if (is_assistant && last_user_content[0]) {
            // Store response template - truncate very long content
            size_t rlen = strlen(content);
            if (rlen > 5 && rlen < 32000) {
                fprintf(tmpl, "Q: %s\n", last_user_content);
                fprintf(tmpl, "A: %s\n\n", content);
                template_count++;
            }
            last_user_content[0] = '\0';
        }

        fact_count = cos_knowledge_fact_count(kb);
        if (line_count % 10000 == 0) {
            printf("  %zu lines | %zu facts | %zu templates\n",
                   line_count, fact_count, template_count);
        }
    }

    fclose(f);
    fclose(tmpl);

    printf("\nDone! %zu lines processed.\n", line_count);
    printf("  Facts stored:  %zu\n", fact_count);
    printf("  Templates:     %zu\n", template_count);

    // Show sample facts
    printf("\nSample stored facts:\n");
    cos_query_result_t qr;
    if (cos_knowledge_query(kb, &(cos_query_t){0,0,0,10,true}, &qr, sys) == COS_OK) {
        for (size_t i = 0; i < qr.count && i < 8; i++) {
            cos_string_view_t s = cos_string_lookup(strings, qr.facts[i].subject);
            cos_string_view_t p = cos_string_lookup(strings, qr.facts[i].predicate);
            cos_string_view_t o = cos_string_lookup(strings, qr.facts[i].object);
            printf("  (%.*s, %.*s, %.*s)\n",
                   (int)s.length, s.data ? s.data : "?",
                   (int)p.length, p.data ? p.data : "?",
                   (int)o.length, o.data ? o.data : "?");
        }
    }

    cos_parser_destroy(parser);
    cos_knowledge_destroy(kb);
    cos_string_table_destroy(strings);
    return 0;
}
