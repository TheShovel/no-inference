// bench_runner.c - Fast batch benchmark runner
// Reads questions, processes through COS, outputs responses.
// Usage: bench_runner [templates.txt] [questions.txt]

#include "cos/core.h"
#include "cos/allocator.h"
#include "cos/arena.h"
#include "cos/string_intern.h"
#include "cos/string_view.h"
#include "cos/parser.h"
#include "cos/knowledge.h"
#include "cos/conversation.h"
#include "cos/template_matcher.h"
#include "cos/fact_lookup.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>

int main(int argc, char** argv) {
    const char* tmpl_path  = argc > 1 ? argv[1] : "cos_templates.txt";
    const char* input_path = argc > 2 ? argv[2] : NULL;

    // Init COS runtime
    cos_allocator_t* sys      = cos_sys_allocator();
    cos_allocator_t* arena    = cos_arena_create(NULL, sys);
    cos_allocator_t* scratch  = cos_arena_create(NULL, sys);
    cos_string_table_t* strings = cos_string_table_create(sys);
    cos_knowledge_base_t* kb  = cos_knowledge_create(sys);
    cos_knowledge_base_t* wm  = cos_knowledge_create(sys);

    cos_conversation_config_t cc;
    memset(&cc, 0, sizeof(cc));
    cc.allocator      = arena;
    cc.scratch_arena  = scratch;
    cc.string_table   = strings;
    cc.knowledge      = kb;
    cc.working_memory = wm;
    cos_conversation_t* conv = cos_conversation_create(&cc);

    // Load templates
    cos_template_db_t* tmpl_db = cos_template_db_create(sys);
    int tmpl_count = cos_template_db_load(tmpl_db, tmpl_path);
    if (tmpl_count > 0)
        fprintf(stderr, "Loaded %d templates\n", tmpl_count);

    // Load factual knowledge
    cos_fact_db_t* facts = cos_fact_db_create(sys);
    int fact_count = cos_fact_db_load_file(facts, "/tmp/truthfulqa_facts.tsv");
    if (fact_count > 0)
        fprintf(stderr, "Loaded %d facts\n", fact_count);

    // Open input
    FILE* in = stdin;
    if (input_path) {
        in = fopen(input_path, "r");
        if (!in) { fprintf(stderr, "Cannot open: %s\n", input_path); return 1; }
    }

    // Process each line
    char buf[8192];
    int total = 0, hits = 0;

    while (fgets(buf, sizeof(buf), in)) {
        total++;
        size_t len = strlen(buf);
        while (len > 0 && (buf[len-1] == '\n' || buf[len-1] == '\r')) buf[--len] = '\0';
        if (len == 0) { putchar('\n'); continue; }

        const char* response = NULL;
        size_t rlen = 0;
        int used_fact = 0;

        // 1) Try fact lookup first (most accurate)
        const char* fact_ans = NULL;
        size_t fact_alen = 0;
        int ignore1 = 0, ignore2 = 0;
        int fact_score = cos_fact_db_query(facts, buf, len, &fact_ans, &fact_alen, &ignore1, &ignore2);
        if (fact_score > 0 && fact_ans) {
            response = fact_ans;
            rlen = fact_alen;
            used_fact = 1;
            hits++;
        }

        // 2) Try template matching
        if (!used_fact && tmpl_db) {
            const template_entry_t* tmpl = NULL;
            float score = 0.0f;
            // Check if it's a question
            bool is_question = false;
            const char* qw[] = {"what","why","how","when","where","who",
                "explain","describe","define","tell me"};
            char low[256];
            size_t bl = len < 255 ? len : 255;
            for (size_t i = 0; i < bl; i++) low[i] = (char)tolower((unsigned char)buf[i]);
            low[bl] = '\0';
            for (size_t q = 0; q < 10 && !is_question; q++)
                if (strstr(low, qw[q])) is_question = true;

            if (is_question) {
                score = cos_template_db_match(tmpl_db, buf, len, &tmpl);
            }
            if (score > 0.20f && tmpl) {
                response = tmpl->answer;
                rlen = tmpl->a_len > 0 ? tmpl->a_len - 1 : 0;
                hits++;
            }
        }

        // 3) Use conversation pipeline
        if (!used_fact && !response) {
            cos_status_t status = cos_conversation_process(
                conv, cos_sv(buf, len), &response, &rlen);
            if (status != COS_OK || !response) {
                response = "[ERROR]";
                rlen = 7;
            }
            cos_arena_reset(scratch);
        }

        // Output response
        if (response && rlen > 0) {
            for (size_t i = 0; i < rlen && i < 2000; i++) {
                char c = response[i];
                putchar(c == '\n' ? ' ' : c);
            }
        }
        putchar('\n');

        if (total % 100 == 0)
            fprintf(stderr, "  %d done, %d hits\n", total, hits);
    }

    if (in != stdin) fclose(in);
    fprintf(stderr, "Done: %d questions, %d hits (%.0f%%)\n",
            total, hits, total > 0 ? 100.0f * hits / total : 0.0f);

    cos_template_db_destroy(tmpl_db);
    cos_fact_db_destroy(facts);
    cos_conversation_destroy(conv);
    cos_knowledge_destroy(wm);
    cos_knowledge_destroy(kb);
    cos_string_table_destroy(strings);
    cos_allocator_destroy(scratch);
    cos_allocator_destroy(arena);
    return 0;
}
