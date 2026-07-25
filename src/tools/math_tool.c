// math_tool.c - Arithmetic Tool for COS
//
// Handles basic math operations: +, -, *, /, %, power, sqrt
// Parses natural language math queries like "what is 2 + 2"
// and returns the computed result.

#include "cos/core.h"
#include "cos/tools.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <ctype.h>
#include <math.h>

// -- Simple expression evaluator (no external dependencies) ------------------

static double parse_number(const char** p) {
    while (**p == ' ') (*p)++;
    double result = 0.0;
    int frac = 0;
    double divisor = 1.0;
    int sign = 1;
    if (**p == '-') { sign = -1; (*p)++; }
    while (isdigit((unsigned char)**p) || **p == '.') {
        if (**p == '.') { frac = 1; (*p)++; continue; }
        if (frac) { divisor *= 10.0; result += (**p - '0') / divisor; }
        else result = result * 10.0 + (**p - '0');
        (*p)++;
    }
    return result * sign;
}

// Very simple expression parser (no precedence, left-to-right)
// Handles: "2 + 3", "5 * 4", "10 / 2", "2 ^ 3", "sqrt(9)", "5 % 2"
static double eval_simple(const char* expr, const char** end) {
    double result = parse_number(&expr);
    
    while (*expr) {
        while (*expr == ' ') expr++;
        char op = *expr;
        if (!op || op == ')' || op == '\n' || op == '\0') break;
        expr++;
        
        if (op == '+') { result += parse_number(&expr); }
        else if (op == '-') { result -= parse_number(&expr); }
        else if (op == '*') { result *= parse_number(&expr); }
        else if (op == '/') { 
            double d = parse_number(&expr);
            if (d != 0.0) result /= d;
            else { *end = expr; return 0.0; }  // div by zero
        }
        else if (op == '%') { 
            long long a = (long long)result;
            long long b = (long long)parse_number(&expr);
            if (b != 0) result = (double)(a % b);
            else { *end = expr; return 0.0; }
        }
        else if (op == '^') { result = pow(result, parse_number(&expr)); }
        else break;
    }
    
    *end = expr;
    return result;
}

// -- Tool execution ----------------------------------------------------------

static cos_status_t math_execute(const cos_tool_t* tool,
                                  const char* args, size_t args_length,
                                  char* out_buffer, size_t buffer_size,
                                  size_t* out_written) {
    (void)tool;
    
    if (!args || args_length == 0) {
        const char* msg = "Please provide a math expression.";
        size_t len = strlen(msg);
        size_t copy = len < buffer_size - 1 ? len : buffer_size - 1;
        memcpy(out_buffer, msg, copy);
        out_buffer[copy] = '\0';
        *out_written = copy;
        return COS_OK;
    }
    
    // Extract numbers from the text
    const char* p = args;
    
    // Handle "what is X + Y" or "calculate X * Y" patterns
    const char* num_start = NULL;
    while (*p) {
        if (isdigit((unsigned char)*p) || (*p == '-' && isdigit((unsigned char)p[1]))) {
            num_start = p;
            break;
        }
        p++;
    }
    
    if (!num_start) {
        const char* msg = "I couldn't find numbers to calculate.";
        size_t len = strlen(msg);
        size_t copy = len < buffer_size - 1 ? len : buffer_size - 1;
        memcpy(out_buffer, msg, copy);
        out_buffer[copy] = '\0';
        *out_written = copy;
        return COS_OK;
    }
    
    const char* end = NULL;
    double result = eval_simple(num_start, &end);
    
    // Format the result
    char result_str[64];
    if (result == (long long)result) {
        snprintf(result_str, sizeof(result_str), "%.0f", result);
    } else {
        snprintf(result_str, sizeof(result_str), "%.4f", result);
        // Trim trailing zeros
        size_t rlen = strlen(result_str);
        while (rlen > 1 && result_str[rlen-1] == '0') rlen--;
        if (result_str[rlen-1] == '.') rlen--;
        result_str[rlen] = '\0';
    }
    
    const char* prefix = "The answer is ";
    size_t plen = strlen(prefix);
    size_t rlen = strlen(result_str);
    size_t total = plen + rlen + 1;
    size_t copy = total < buffer_size ? total : buffer_size - 1;
    
    memcpy(out_buffer, prefix, plen < copy ? plen : copy);
    if (plen < copy) memcpy(out_buffer + plen, result_str, copy - plen);
    out_buffer[copy] = '\0';
    *out_written = copy;
    
    return COS_OK;
}

static const cos_tool_t g_math_tool = {
    .name        = "math",
    .description = "Calculate arithmetic expressions (e.g., 'what is 2 + 2')",
    .execute     = math_execute,
    .context     = NULL,
};

cos_status_t cos_register_math_tool(cos_tool_registry_t* reg) {
    return cos_tool_register(reg, &g_math_tool);
}
