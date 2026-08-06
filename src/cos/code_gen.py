"""
COS Code Generator — deterministic, rule-based code synthesis.

Unlike the curated code KB (code_knowledge.py) which answers "what is X" /
"how do I do X" from hand-written entries, this module *synthesizes* code for
common developer tasks by detecting the programming language and the task
from the query, then assembling a correct, complete code template.

The code is always real and runnable — it comes from a template library, not
from generation. There is no inference anywhere in this module.

Pipeline:
    query -> detect_language(query) -> detect_task(query) -> compose_answer()

Public API:
    generate_code(query) -> Optional[str]   full markdown answer, or None
    detect_language(query) -> Optional[str] canonical language name
    detect_task(query) -> Optional[str]     task id
"""

import re
from typing import Optional

# ── Language detection ──────────────────────────────────────────────────────
# canonical language -> (aliases with word boundaries, regex patterns)
_LANG_ALIASES = {
    'python':    {'python', 'python3', 'py', 'pandas', 'numpy', 'django',
                  'flask', 'fastapi', 'requests library', 'venv'},
    'javascript': {'javascript', 'js', 'node', 'node.js', 'nodejs', 'express',
                   'react', 'vue', 'axios', 'fetch api'},
    'typescript': {'typescript', 'ts', 'tsx'},
    'java':      {'java', 'javac', 'spring boot'},
    'c++':       {'c++', 'cpp', 'cplusplus'},
    'c':         {'c programming', 'c language'},
    'c#':        {'c#', 'csharp', 'c sharp', '.net'},
    'go':        {'go', 'golang'},
    'rust':      {'rust', 'rs'},
    'ruby':      {'ruby', 'rails'},
    'php':       {'php', 'laravel'},
    'swift':     {'swift'},
    'kotlin':    {'kotlin'},
    'sql':       {'sql', 'mysql', 'postgres', 'postgresql', 'sqlite',
                  'sql server', 'oracle'},
    'bash':      {'bash', 'shell', 'sh', 'zsh', 'command line', 'terminal',
                  'cli', 'curl', 'linux', 'ubuntu', 'unix', 'debian', 'mac'},
    'html':      {'html'},
    'css':       {'css'},
}

# Aliases that need a bit of context before they are treated as languages.
# "go" is a normal English word ("how to go about this"), so it only counts
# when a coding cue is nearby ("in go", "go program", "write ... in go").
_CONTEXTUAL_LANGS = {'go'}

_CODING_CUE_RE = re.compile(
    r'\b(?:write|implement|create|make|build|fix|debug|function|program|'
    r'code|snippet|class|algorithm|using|in|with)\b', re.IGNORECASE)


def _norm_aliases(text: str) -> str:
    """Normalize punctuation-heavy language names so they match aliases."""
    t = text.lower()
    # "c++" -> "cplusplus"  (also "c++11", "c++17")
    t = re.sub(r'\bc\s*\+\+\s*(?:\d+)?\b', 'cplusplus', t)
    # "c#" -> "csharp"
    t = re.sub(r'\bc\s*#\b', 'csharp', t)
    t = re.sub(r'\bc#\s*(?:\.net)?\b', 'csharp', t)
    # "node.js" -> "node.js" is already a literal alias
    return t


def detect_language(query: str) -> Optional[str]:
    """Return the canonical language name mentioned in the query, or None.

    If no language is mentioned, returns None — callers decide the default.
    """
    q = _norm_aliases(query)
    # 0. Explicit script-language phrases outrank any coincidental mention of
    #    another language's name ("write a bash script to list all python
    #    files" is a bash request even though 'python' appears).
    if re.search(r'\b(?:bash|shell|zsh|sh)\s+script\b', q, re.IGNORECASE):
        return 'bash'
    if re.search(r'\b(?:command\s*line|terminal|cli)\b', q, re.IGNORECASE):
        return 'bash'
    # 1. Exact alias hits (word-boundary), longest alias first.
    for lang, aliases in _LANG_ALIASES.items():
        for alias in sorted(aliases, key=len, reverse=True):
            alias_n = _norm_aliases(alias)
            if not alias_n:
                continue
            if alias_n in ('go',) and lang == 'go':
                # contextual: "go" must sit next to a coding cue
                if re.search(r'\bgolang\b', q):
                    return 'go'
                if re.search(r'\bgo\b', q) and _CODING_CUE_RE.search(query):
                    return 'go'
                continue
            if re.search(r'(?<![a-z0-9])' + re.escape(alias_n) + r'(?![a-z0-9])', q):
                return lang
    # 2. Tool-to-language fallbacks for framework names.
    if re.search(r'\bflask\b|\bfastapi\b|\bdjango\b', q, re.IGNORECASE):
        return 'python'
    if re.search(r'\bexpress\b|\bnode\b|react|vue', q, re.IGNORECASE):
        return 'javascript'
    if re.search(r'\bpandas\b|\bnumpy\b', q, re.IGNORECASE):
        return 'python'
    return None


# ── Task detection ──────────────────────────────────────────────────────────
# (task_id, [regex patterns]) — first task whose any pattern matches wins.
# Patterns are ordered from most specific to most general within each task.
_TASK_PATTERNS = [
    # ── web pages (synthesized HTML/CSS) ──────────────────────────────────
    ('web_page', [
        r'\b(?:create|make|build|design|generate|develop|craft|code)\b.*\b'
        r'(?:website|web\s*site|web\s*page|landing\s*page|homepage|'
        r'home\s*page|portfolio|web\s*app)\b(?!\s+(?:scraper|scraping))',
        r'\b(?:website|web\s*site|web\s*page|site|landing\s*page)\s+'
        r'(?:for|about|of)\b',
        # terse noun-first requests: "taco shop website"
        r'\b(?:taco|pizza|burger|sushi|coffee|cafe|bakery|ice\s*cream|bar|'
        r'restaurant)\b.*\b(?:website|web\s*site|web\s*page|site)\b\s*$',
        r'\bportfolio\s+(?:website|web\s*site|web\s*page|site)\b\s*$',
    ]),
    # ── numbers / algorithms ─────────────────────────────────────────────
    ('prime', [
        r'\b(?:check\s+(?:if\s+)?|test\s+(?:if\s+)?|find\s+|determine\s+)?'
        r'(?:whether\s+)?(?:a\s+)?(?:number|integer|num|n)\s+(?:is|be)\s+'
        r'(?:a\s+)?prime\b',
        r'\bprimality\b',
        r'\bprime\s+check\w*\b',
        r'\bisprime\b',
        r'\bprime\s+numbers?\s+(?:up\s+to|between|less\s+than|under|'
        r'below|in\s+range)\b',
        r'\bprime\s+numbers?\b',
        r'\bprime\b',
    ]),
    ('factorial', [
        r'\bfactorial\b', r'\bfact(?:orial)?\s+of\s+(\d+|\w+)',
    ]),
    ('fibonacci', [
        r'\bfib(?:onacci)?\s*(?:series|sequence|numbers?)?\b',
        r'\bnth\s+fib\b',
    ]),
    ('fizzbuzz', [
        r'\bfizz\s*buzz\b', r'\bfizzbuzz\b',
    ]),
    ('gcd', [
        r'\bgcd\b', r'\bgcf\b', r'greatest\s+common\s+(?:divisor|factor)\b',
        r'\blcm\b', r'least\s+common\s+multiple\b',
    ]),
    ('binary_search', [
        r'\bbinary\s+search\b(?!\s+tree)',
    ]),
    ('merge_sorted', [
        r'\bmerge\s+(?:two\s+)?sorted\s+(?:lists?|arrays?)\b',
        r'\bmerge\s+sorted\b',
    ]),
    ('sort_list', [
        r'\bsort\s+(?:a\s+)?(?:list|array|slice|vector)\b',
        r'\bsort\s+(?:the\s+)?(?:list|array|slice)\s+(?:in|by)\b',
        r'\bsorting\s+(?:a\s+)?(?:list|array|slice)\b',
        r'\bquicksort\b', r'\bmerge\s+sort\b', r'\bbubble\s+sort\b',
        r'\bselection\s+sort\b', r'\binsertion\s+sort\b',
    ]),
    ('reverse_string', [
        r'\brevers(?:e|es|ing)\s+(?:a\s+|the\s+)?string\b',
        r'\brevers(?:e|es|ing)\s+(?:the\s+)?(?:characters\s+of\s+)?(?:a\s+)?string\b',
        r'\brevers(?:e|es|ing)\s+word(?:s)?\b',
    ]),
    ('reverse_array', [
        r'\brevers(?:e|es|ing)\s+(?:an?\s+)?(?:array|list|slice|vector)\b',
        r'\brevers(?:e|es|ing)\s+(?:the\s+)?(?:array|list|slice)\b',
    ]),
    ('palindrome_string', [
        r'\bpalindrome\b',
    ]),
    ('anagram', [
        r'\banagram\b',
    ]),
    ('most_frequent', [
        r'\bmost\s+(?:frequently\s+)?occurring\s+(?:character|element|word)\b',
        r'\bfind\s+the\s+most\s+common\b',
        r'\bmost\s+common\s+(?:character|element|word)\b',
        r'\bmode\s+of\s+(?:a\s+)?(?:list|array)\b',
    ]),
    ('count_occurrences', [
        r'\bcount\s+(?:the\s+)?(?:number\s+of\s+)?(?:occurrences|frequency)'
        r'\s+of\b',
        r'\bfrequency\s+of\s+(?:each|every|characters?|elements?|words?)\b',
        r'\bcharacter\s+counter\b', r'\bword\s+count(?:er)?\b',
    ]),
    ('backup_dir', [
        r'\b(?:back\s+up|backup)\b.*\b(?:directory|folder|files|data|'
        r'dir|project)\b',
        r'\b(?:create|make|write)\b.*\bbackup\s+script\b',
        r'\bbackup\s+(?:the\s+)?(?:directory|folder|dir)\b',
    ]),
    ('for_loop', [
        r'\bfor\s+loop\b',
        r'\bwrite\s+(?:a\s+)?loop\b',
        r'\bprint\s+numbers?\s+1\s+to\b',
        r'\bloop\s+that\s+prints\b',
        r'\biterate\s+(?:from|over)\s+.*\b(?:range|numbers?)\b',
    ]),
    ('comment_syntax', [
        r'\bcomment\b',
    ]),
    ('array_contains', [
        r'\b(?:check\s+if\s+)?(?:an?\s+)?array\s+(?:contains|includes|has)\b',
        r'\bcontains\s+.*\b(?:value|item|element)\b',
        r'\bincludes\s+.*\b(?:value|item|element)\b',
    ]),
    ('string_to_number', [
        r'\bconvert\s+(?:a\s+)?string\s+to\s+(?:a\s+)?(?:number|int)\b',
        r'\bparse\s+int\b', r'\bparseint\b',
        r'\bstring\s+to\s+(?:number|int)\b',
        r'\bconvert\s+.*\bstring\b.*\b(?:number|integer)\b',
    ]),
    ('rename_file', [
        r'\brename\s+(?:a\s+)?file\b',
        r'\bmove\s+(?:a\s+)?file\b',
        r'\brename\s+(?:a\s+)?directory\b',
    ]),
    ('pip_install', [
        r'\bpip\s+install\b',
        r'\binstall\s+(?:a\s+)?package\s+with\s+pip\b',
        r'\binstall\s+.*\bpip\b',
        r'\b(?:install|manage)\s+.*\bpackages?\s+with\s+pip\b',
    ]),
    ('npm_install', [
        r'\bnpm\s+install\b',
        r'\binstall\s+(?:a\s+)?package\s+with\s+npm\b',
        r'\b(?:install|manage)\s+.*\bpackages?\s+with\s+npm\b',
    ]),
    ('sys_disk', [
        r'\b(?:check|see|find\s+out)\s+(?:disk|drive)\s+(?:space|usage)\b',
        r'\bdisk\s+(?:space|usage)\b', r'\bhow\s+much\s+disk\b',
        r'\bdf\s*-h\b',
    ]),
    ('sys_mem', [
        r'\b(?:check|see)\s+(?:memory|ram)\s+usage\b',
        r'\bmemory\s+usage\b', r'\bram\s+usage\b',
        r'\bhow\s+much\s+(?:memory|ram)\b',
    ]),
    ('sys_kill', [
        r'\bkill\s+(?:a\s+)?process\b', r'\bstop\s+(?:a\s+)?process\b',
        r'\bkill\s+by\s+pid\b', r'\bforce\s+kill\b',
        r'\bkilled\s+process\b',
    ]),
    ('sys_port', [
        r'\b(?:what|which)\s+(?:process|program|service).*\b(?:using|on)\b.*\bport\b',
        r'\bport\s+in\s+use\b', r'\bport\s+usage\b',
        r'\blistening\s+on\s+(?:a\s+)?port\b',
        r'\busing\s+(?:a\s+)?port\b',
    ]),
    ('sys_large_files', [
        r'\bfind\s+large\s+files\b', r'\blargest\s+files?\b',
        r'\bfiles\s+larger\s+than\b', r'\bbig\s+files\b',
    ]),
    ('dedup', [
        r'\bremove\s+duplicates?\b', r'\bdedup(?:licate)?\b',
        r'\bunique\s+(?:values?|elements?)\b',
        r'\bduplicates?\s+from\s+(?:a\s+)?(?:list|array)\b',
    ]),
    ('flatten', [
        r'\bflatten(?:s|ed|ing)?\s+(?:a\s+)?(?:nested\s+)?(?:list|array|tuple)\b',
        r'\bflatten(?:s|ed|ing)?\s+nested\b', r'\bflatten(?:s|ed|ing)?\b',
    ]),
    ('sum_list', [
        r'\bsum\s+(?:of\s+)?(?:a\s+)?(?:list|array|numbers?)\b',
        r'\btotal\s+of\s+(?:a\s+)?(?:list|array)\b',
        r'\baverage\s+of\s+(?:a\s+)?(?:list|array|numbers?)\b',
        r'\bmean\s+of\s+(?:a\s+)?(?:list|array)\b',
    ]),
    ('two_sum', [
        r'\btwo\s*sum\b', r'\bfind\s+pair\s+that\s+sums?\s+to\b',
    ]),
    # ── data structures ─────────────────────────────────────────────────
    ('bst', [
        r'\bbinary\s+search\s+tree\b', r'\bbst\b',
    ]),
    ('linked_list', [
        r'\breverse\s+(?:a\s+)?linked\s+list\b',
        r'\blinked\s+list\b',
    ]),
    ('graph_traversal', [
        r'\b(?:breadth|depth)[\s-]*(?:first|fs|first\s+search)\b',
        r'\bbfs\b', r'\bdfs\b', r'\btraverse\s+(?:a\s+)?graph\b',
    ]),
    # ── regex / strings ─────────────────────────────────────────────────
    ('regex_email', [
        r'\b(?:validat|check|verif|test)\w*\s+(?:if\s+)?(?:a\s+|an?\s+|the\s+)?'
        r'(?:string\s+is\s+)?(?:valid\s+)?email(?:\.?\s+address)?\b',
        r'\bemail\s+(?:validation|validator|regex|regexp)\b',
        r'\bregex\s+(?:to|for)\s+.*\bemail\b',
    ]),
    ('regex_phone', [
        r'\b(?:validate|check|verify)\s+(?:a\s+)?phone\s+number\b',
        r'\bphone\s+(?:validation|validator|regex|regexp)\b',
    ]),
    ('regex_password', [
        r'\b(?:password|passwd)\s+(?:validation|validator|strength|regex|'
        r'check)\b',
        r'\bvalidate\s+(?:a\s+)?password\b',
        r'\bstrong\s+password\b',
    ]),
    ('regex_url', [
        r'\b(?:validate|check)\s+(?:an?\s+)?url\b',
        r'\burl\s+(?:validation|validator|regex|regexp)\b',
    ]),
    ('extract_emails', [
        r'\bextract\s+(?:all\s+)?emails?\b',
        r'\bfind\s+(?:all\s+)?email\s+addresses\b',
        r'\bscrape\s+emails\b',
    ]),
    # ── IO / data ────────────────────────────────────────────────────────
    ('read_csv', [
        r'\bread\s+(?:a\s+)?csv\b', r'\bread\s+csv\s+file\b',
        r'\bparse\s+(?:a\s+)?csv\b', r'\bcsv\s+file\b',
        r'\bcsv\s+reader\b', r'\bcsv\s+parser\b',
    ]),
    ('write_csv', [
        r'\bwrite\s+(?:a\s+)?csv\b', r'\bexport\s+.*csv\b',
        r'\bsave\s+.*\bcsv\b',
    ]),
    ('read_file', [
        r'\bread\s+(?:a\s+)?file\b', r'\bread\s+file\s+line\s+by\s+line\b',
        r'\bopen\s+(?:and\s+)?read\s+(?:a\s+)?file\b',
        r'\bread\s+text\s+file\b',
    ]),
    ('write_file', [
        r'\bwrite\s+(?:to\s+)?(?:a\s+)?file\b',
        r'\bappend\s+to\s+(?:a\s+)?file\b',
        r'\bcreate\s+(?:a\s+)?file\b',
    ]),
    ('read_json', [
        r'\b(?:read|parse|load)\s+(?:a\s+)?json\s+file\b',
        r'\bparse\s+json\b', r'\bjson\s+parser\b',
        r'\bconvert\s+json\s+to\b',
    ]),
    ('write_json', [
        r'\b(?:write|save|dump)\s+.*\bjson\b',
        r'\bconvert\s+.*to\s+json\b',
        r'\bserialize\s+.*(?:to\s+)?json\b',
    ]),
    ('http_get', [
        r'\b(?:make|send|do)\s+(?:an?\s+)?http\s+(?:get|request)\b',
        r'\bfetch\s+(?:data\s+from\s+)?(?:an?\s+)?(?:api|url|endpoint)\b',
        r'\bget\s+request\b', r'\bhttp\s+request\b',
        r'\brequests?\s+library\b', r'\baxios\b',
        r'\bdownload\s+(?:a\s+)?(?:file|page|data)\b',
        r'\bapi\s+call\b', r'\bcall\s+an\s+api\b',
    ]),
    ('http_post', [
        r'\bpost\s+(?:data|json|a\s+request)\b',
        r'\bhttp\s+post\b', r'\bsend\s+(?:a\s+)?post\b',
        r'\bsubmit\s+(?:a\s+)?form\b',
    ]),
    ('web_scrape', [
        r'\b(?:web\s+)?scrap(?:e|ing)\b', r'\bscrape\b',
        r'\bextract\s+(?:all\s+)?links?\b',
        r'\bextract\s+(?:the\s+)?(?:title|headings?|text)\s+from\b',
        r'\bparse\s+(?:an?\s+)?html\b',
    ]),
    ('fetch_table', [
        r'\bfetch\s+.*\btable\b', r'\bdisplay\s+.*\btable\b',
        r'\btable\s+from\s+(?:an?\s+)?api\b',
    ]),
    ('express_api', [
        r'\bexpress\s+(?:api|server|app|route|endpoint)\b',
        r'\bnode\.?js\s+(?:api|server|endpoint)\b',
    ]),
    ('flask_api', [
        r'\bflask\s+(?:api|app|server|endpoint|route)\b',
    ]),
    # ── SQL ──────────────────────────────────────────────────────────────
    ('sql_select', [
        r'\bselect\b.*\b(?:from|where|order\s+by|limit)\b', r'\bselect\b',
    ]),
    ('sql_insert', [
        r'\binsert\s+(?:into|new\s+rows?)\b',
    ]),
    ('sql_update', [
        r'\bupdate\s+(?:a\s+)?(?:table|row|record)\b',
    ]),
    ('sql_delete', [
        r'\bdelete\s+(?:from\s+)?(?:a\s+)?(?:table|row|record)\b',
    ]),
    ('sql_join', [
        r'\bjoin\s+(?:two\s+)?tables\b', r'\b(?:inner|left|right|outer)\s+'
        r'join\b', r'\bsql\s+join\b',
    ]),
    ('sql_group_by', [
        r'\bgroup\s+by\b', r'\bgrouped\s+by\b',
        r'\b(?:sum|average|count)\s+.*\bper\b',
        r'\bcount\s+rows\b', r'\bcount\s+records\b',
    ]),
    ('sql_duplicates', [
        r'\bduplicate\s+rows\b', r'\bduplicates?\s+in\s+(?:a\s+)?table\b',
        r'\bfind\s+duplicates?\b',
    ]),
    ('sql_create_table', [
        r'\bcreate\s+(?:a\s+)?table\b', r'\bmake\s+(?:a\s+)?table\b',
        r'\bschema\s+for\b',
    ]),
    ('sql_aggregate', [
        r'\b(?:sum|average|avg|min|max|count)\s+of\b',
    ]),
    # ── git / bash ───────────────────────────────────────────────────────
    ('git_undo', [
        r'\bundo\s+(?:a\s+)?commit\b', r'\brevert\s+(?:a\s+)?commit\b',
        r'\breset\s+(?:a\s+)?commit\b', r'\buncommit\b',
        r'\bundo\s+last\s+commit\b',
    ]),
    ('git_commit', [
        r'\bcommit\s+(?:changes?|code|files?)\b',
        r'\bmake\s+(?:a\s+)?commit\b',
        r'\bcommit\s+message\b',
    ]),
    ('git_branch', [
        r'\b(?:create|switch|rename|delete)\s+(?:a\s+)?branch\b',
        r'\bgit\s+branch\b', r'\bmerge\s+(?:a\s+)?branch\b',
        r'\bnew\s+branch\b',
    ]),
    ('git_stash', [
        r'\bstash\b',
    ]),
    ('git_log', [
        r'\bgit\s+log\b', r'\bcommit\s+history\b',
        r'\bshow\s+(?:the\s+)?(?:last|recent|all)\s+commits\b',
    ]),
    ('bash_file_ops', [
        r'\b(?:list|find|count)\s+(?:all\s+|the\s+)?(?:[a-z0-9_.-]+\s+)*'
        r'(?:files?|directories?)\b',
        r'\b(?:copy|move|rename|delete)\s+(?:a\s+)?file\b',
        r'\bpermissions?\s+(?:on\s+)?(?:a\s+)?file\b',
        r'\bchmod\b', r'\bchown\b', r'\bgrep\b',
        r'\bshow\s+.*\bcontents?\s+of\b',
    ]),
    ('bash_curl', [
        r'\bcurl\b',
    ]),
    # ── data munging / helpers ────────────────────────────────────────────
    ('chunk_list', [
        r'\bchunk\w*\b.*\b(?:list|array)\b',
        r'\bsplit\s+(?:a\s+|the\s+)?(?:list|array)\s+into\b',
        r'\b(?:list|array)\s+into\s+(?:chunks|groups|batches)\b',
        r'\bpartition\s+.*\b(?:list|array)\b',
    ]),
    ('transpose_matrix', [
        r'\btranspose\b',
        r'\bmatrix\s+transpose\b',
        r'\brotate\s+(?:a\s+)?matrix\b',
    ]),
    ('count_words', [
        r'\bcount\s+words?\b',
        r'\bword\s+frequenc\w+\b',
        r'\bword\s+count\b',
        r'\bhow\s+many\s+times\s+each\s+word\b',
    ]),
    ('slugify', [
        r'\bslugify\b',
        r'\b(?:url|seo)[-\s]friendly\s+string\b',
        r'\bconvert\s+.*\bto\s+a\s+slug\b',
    ]),
    ('caesar_cipher', [
        r'\bcaesar\b',
        r'\brot(?:13|47)?\b',
        r'\bshift\s+cipher\b',
        r'\bencrypt\s+.*\b(?:shift|letter)\b',
    ]),
    ('password_gen', [
        r'\bgenerate\s+(?:a\s+|an\s+)?(?:random\s+)?password\b',
        r'\bpassword\s+generator\b',
        r'\brandom\s+password\b',
        r'\bstrong\s+password\s+generator\b',
    ]),
    ('shuffle_list', [
        r'\bshuffle\b',
        r'\bfisher[-\s]yates\b',
        r'\brandomi[sz]e\s+(?:a\s+|the\s+)?(?:list|array|deck)\b',
    ]),
    ('memoize', [
        r'\bmemoiz\w+\b',
        r'\bcaching\s+decorator\b',
        r'\bcache\s+(?:a\s+)?function\s+(?:call\s+)?results\b',
        r'\bmemoization\b',
    ]),
    ('retry_backoff', [
        r'\bretry\b.*\bbackoff\b',
        r'\bexponential\s+backoff\b',
        r'\bretry\s+(?:a\s+)?function\b',
        r'\bretry\s+logic\b',
    ]),
    ('json_pretty', [
        r'\bpretty[\s-]?print\b.*\bjson\b',
        r'\bformat\s+json\b',
        r'\bjson\s+with\s+indent(?:ation)?\b',
        r'\bpretty\s+json\b',
    ]),
]

# ── Per-task intro + notes (composed with {lang}) ──────────────────────────
_TASK_INTRO = {
    'prime': "Here's a {lang} function that checks whether a number is prime.",
    'factorial': "Here's a {lang} function that computes the factorial of a non-negative integer.",
    'fibonacci': "Here's a {lang} function that generates the Fibonacci sequence up to n terms.",
    'fizzbuzz': "Here's a {lang} program that prints FizzBuzz for numbers 1 through n.",
    'gcd': "Here's a {lang} function that computes the greatest common divisor using the Euclidean algorithm.",
    'binary_search': "Here's a {lang} implementation of binary search on a sorted array.",
    'merge_sorted': "Here's a {lang} function that merges two sorted arrays into one sorted array.",
    'sort_list': "Here's a {lang} function that sorts a list of numbers in ascending order.",
    'reverse_string': "Here's a {lang} function that reverses a string.",
    'reverse_array': "Here's a {lang} function that reverses an array in place.",
    'palindrome_string': "Here's a {lang} function that checks whether a string is a palindrome.",
    'anagram': "Here's a {lang} function that checks whether two strings are anagrams of each other.",
    'most_frequent': "Here's a {lang} function that finds the most frequently occurring element in a collection.",
    'count_occurrences': "Here's a {lang} snippet that counts how many times each element appears.",
    'backup_dir': "Here's a {lang} script that backs up a directory with a timestamped copy.",
    'for_loop': "Here's how to write a for loop in {lang}.",
    'comment_syntax': "Here's how to write comments in {lang}.",
    'array_contains': "Here's how to check whether an array contains a value in {lang}.",
    'string_to_number': "Here's how to convert a string to a number in {lang}.",
    'rename_file': "Here's how to rename (or move) a file in {lang}.",
    'pip_install': "Here's how to install Python packages with pip.",
    'npm_install': "Here's how to install packages with npm.",
    'sys_disk': "Here's how to check disk space and usage from the {lang} command line.",
    'sys_mem': "Here's how to check memory (RAM) usage from the {lang} command line.",
    'sys_kill': "Here's how to find and kill a process from the {lang} command line.",
    'sys_port': "Here's how to find which process is using a port from the {lang} command line.",
    'sys_large_files': "Here's how to find large files from the {lang} command line.",
    'dedup': "Here's a {lang} function that removes duplicate elements from a list while preserving order.",
    'flatten': "Here's a {lang} function that flattens a nested list structure into a single flat list.",
    'sum_list': "Here's a {lang} snippet that computes the sum (and average) of a list of numbers.",
    'two_sum': "Here's a {lang} function that finds the indices of two numbers that add up to a target.",
    'linked_list': "Here's a {lang} implementation of a singly linked list with a reverse method.",
    'bst': "Here's a {lang} implementation of a binary search tree with insert, search, and traversal methods.",
    'graph_traversal': "Here's a {lang} implementation of breadth-first and depth-first graph traversal.",
    'regex_email': "Here's a {lang} function that validates an email address with a regular expression.",
    'regex_phone': "Here's a {lang} function that validates a phone number with a regular expression.",
    'regex_password': "Here's a {lang} function that checks password strength with a regular expression.",
    'regex_url': "Here's a {lang} function that validates a URL with a regular expression.",
    'extract_emails': "Here's a {lang} function that extracts all email addresses from a block of text.",
    'read_csv': "Here's how to read a CSV file in {lang}.",
    'write_csv': "Here's how to write data to a CSV file in {lang}.",
    'read_file': "Here's how to read a text file in {lang}.",
    'write_file': "Here's how to write to a text file in {lang}.",
    'read_json': "Here's how to parse a JSON file in {lang}.",
    'write_json': "Here's how to serialize data to JSON in {lang}.",
    'http_get': "Here's how to make an HTTP GET request in {lang}.",
    'http_post': "Here's how to make an HTTP POST request with a JSON body in {lang}.",
    'web_scrape': "Here's a {lang} web scraper that downloads a page and extracts structured data from it.",
    'fetch_table': "Here's a {lang} function that fetches data from an API and renders it in an HTML table.",
    'express_api': "Here's a minimal Express API server in {lang}.",
    'flask_api': "Here's a minimal Flask API server in {lang}.",
    'sql_select': "Here's an SQL query that selects data from a table.",
    'sql_insert': "Here's an SQL statement that inserts a row into a table.",
    'sql_update': "Here's an SQL statement that updates existing rows.",
    'sql_delete': "Here's an SQL statement that deletes rows from a table.",
    'sql_join': "Here's an SQL query that joins two tables.",
    'sql_group_by': "Here's an SQL query that groups rows and computes an aggregate.",
    'sql_duplicates': "Here's an SQL query that finds duplicate rows in a table.",
    'sql_create_table': "Here's an SQL statement that creates a table.",
    'sql_aggregate': "Here's an SQL query using an aggregate function.",
    'git_undo': "Here's how to undo a commit in Git, depending on whether it has been pushed.",
    'git_commit': "Here's the standard Git workflow for committing changes.",
    'git_branch': "Here's how to work with branches in Git.",
    'git_stash': "Here's how to stash and restore uncommitted work in Git.",
    'git_log': "Here's how to inspect commit history with Git.",
    'bash_file_ops': "Here's how to work with files and directories from the {lang} command line.",
    'bash_curl': "Here's how to make HTTP requests from the {lang} command line with curl.",
    'chunk_list': "Here's a {lang} function that splits a list into fixed-size chunks.",
    'transpose_matrix': "Here's a {lang} function that transposes a matrix (rows become columns).",
    'count_words': "Here's a {lang} function that counts how many times each word appears in a text.",
    'slugify': "Here's a {lang} function that turns any text into a URL-friendly slug.",
    'caesar_cipher': "Here's a {lang} implementation of the Caesar cipher (shift encryption).",
    'password_gen': "Here's a {lang} function that generates a cryptographically strong random password.",
    'shuffle_list': "Here's a {lang} implementation of Fisher–Yates shuffle (fair, in-place).",
    'memoize': "Here's a {lang} memoization wrapper that caches function results by argument.",
    'retry_backoff': "Here's a {lang} retry wrapper with exponential backoff and jitter.",
    'json_pretty': "Here's how to pretty-print JSON in {lang}.",
}

_TASK_NOTES = {
    'prime': "It rejects numbers below 2, then tests divisors only up to the square root of n, so it runs in O(√n) time. The 6k±1 step skips multiples of 2 and 3 for a constant-factor speedup.",
    'factorial': "Factorial grows extremely fast: 20! already overflows a 64-bit integer. For large n, prefer an iterative loop or a library function; for non-integer input, use the gamma function.",
    'fibonacci': "The iterative version runs in O(n) time and O(1) space. The naive recursive version is O(2^n) — avoid it for anything past n ≈ 35. For large n, matrix exponentiation or fast doubling gives O(log n).",
    'fizzbuzz': "The trick is to check divisibility by 15 (3 and 5) first, otherwise numbers divisible by both get printed as 'Fizz' instead of 'FizzBuzz'.",
    'gcd': "The Euclidean algorithm is the classic O(log min(a,b)) solution. For more than two numbers, reduce pairwise: gcd(a, b, c) = gcd(gcd(a, b), c).",
    'binary_search': "Requires a sorted array. Each step halves the search space, giving O(log n) time and O(1) space. The classic bug is an off-by-one in the midpoint — the loop condition `left <= right` with `mid = left + (right - left) // 2` avoids overflow and infinite loops.",
    'merge_sorted': "This is the merge step of merge sort: O(n + m) time using O(n + m) extra space. Both inputs must already be sorted.",
    'sort_list': "The built-in sort (Timsort in Python/JS, introsort in C++, dual-pivot quicksort in Java) is almost always the right choice — O(n log n) average, stable, and heavily optimized. Only hand-roll a sort when you need a custom stable comparator or want to learn the algorithms.",
    'reverse_string': "Strings are immutable in most languages, so reversing produces a new string. In Python, `s[::-1]` is the idiomatic one-liner; in JS, `[...s].reverse().join('')` handles surrogate pairs correctly where `s.split('')` does not.",
    'reverse_array': "The two-pointer swap approach runs in O(n) time and O(1) extra space.",
    'palindrome_string': "A palindrome reads the same forward and backward. The two-pointer version compares characters from both ends and stops early, running in O(n) time and O(1) space.",
    'anagram': "Two strings are anagrams if they contain the same characters with the same counts. Comparing sorted versions is O(n log n); counting characters with a hash map is O(n).",
    'most_frequent': "This uses a hash map to tally frequencies in O(n) time, then a single pass to find the max. For ties, it returns the first-seen element.",
    'count_occurrences': "A hash map (or Counter in Python) counts each element in O(n) time. In SQL the same job is a GROUP BY with COUNT(*).",
    'backup_dir': "The timestamped copy keeps every backup (never overwrites). Add retention later: keep only the newest N backups by sorting the directory and deleting the rest. rsync (bash version) only copies changed files, so repeated runs are cheap.",
    'for_loop': "The classic index loop (`for i in range(...)` / `for (let i = 0; ...)`) is for when you need the index or a fixed number of iterations; the for-each forms are cleaner when you only need the values. In Python, `range` is lazy, so even huge ranges use constant memory.",
    'comment_syntax': "Comments are for explaining *why*, not what — the code itself shows what it does. Keep them short and up to date, because stale comments mislead more than no comments. Languages also have doc-comment conventions (`'''` docstrings in Python, JSDoc in JS, `///` in Rust, Javadoc) for documenting functions and types.",
    'array_contains': "`includes()` (JavaScript) and `in` (Python) both run in O(n) average time for lists. For repeated lookups, use a Set — membership checks become O(1). Remember JavaScript's `includes` uses SameValueZero, so it works with NaN where `indexOf` does not.",
    'string_to_number': "Watch out for partial conversion: `parseInt('42px')` returns 42 in JavaScript while `Number('42px')` returns NaN, and Python's `int('42px')` raises. Always handle the failure case, and prefer explicit conversions over implicit ones.",
    'rename_file': "Renaming within the same filesystem is a metadata operation (O(1), no data copy) — moving across filesystems is a copy+delete. In Python, `os.rename` works on both files and directories; `Path.rename` does the same with a nicer API. In bash, `mv` covers rename and move.",
    'pip_install': "Always install into a virtual environment rather than the system Python — it keeps projects isolated and avoids breaking OS packages. Pin versions (`requests==2.31.0`) in requirements.txt for reproducible builds, and use `pip freeze` to snapshot what you have.",
    'npm_install': "npm reads package.json (declared dependencies) and package-lock.json (exact resolved versions). `npm ci` is the fast, reproducible install for CI and deployments — it wipes node_modules and installs exactly what the lockfile says. `-D` saves to devDependencies (build/test tools), plain install to dependencies (runtime).",
    'sys_disk': "`df -h` shows filesystem-level usage; `du -sh *` shows per-directory usage from your current folder. `--max-depth` is GNU findutils (Linux); macOS uses `-d` instead. `sort -h` sorts human-readable sizes correctly (K < M < G).",
    'sys_mem': "`free -h` shows total/used/available memory; the 'available' number is the useful one. `ps aux --sort=-%mem` lists processes by memory so you can find the hog. `top`/`htop` give a live view.",
    'sys_kill': "Always try a graceful SIGTERM (`kill <pid>`) first so the process can clean up; use `kill -9` (SIGKILL) only when it won't die — it can't be caught and may leave temp files or locks behind. `pkill`/`pgrep` match by name and are handy for killing all instances.",
    'sys_port': "`lsof -i :8080` shows the PID listening on a port (run with sudo for full detail); `ss -tulpn` is the modern netstat replacement. Once you have the PID, `kill -9 <pid>` frees the port. Port 80/443 need root to bind on Linux.",
    'sys_large_files': "`find ... -size +100M` finds files over a size threshold; the `-printf '%s %p'` + `sort -rn` combo lists the largest. `-printf` is GNU-only (Linux); on macOS use `find . -type f -exec ls -lh {} \\;` piped to sort.",
    'dedup': "Using a set for seen items preserves the first occurrence of each element and runs in O(n) time. If order doesn't matter, `sorted(set(items))` is shorter.",
    'flatten': "The iterative stack-based version handles arbitrarily deep nesting without recursion limits. For shallow, fixed-depth nesting a list comprehension with two loops is cleaner.",
    'sum_list': "This runs in O(n) time. Watch out for floating-point precision when averaging; for exact decimals use an integer sum and divide at the end.",
    'two_sum': "The hash-map approach runs in O(n) time by storing each value's index and checking for the complement as you go — one pass, no nested loop.",
    'linked_list': "Reversing a linked list rewires each node's `next` pointer to point at the previous node while saving the old next pointer first — O(n) time, O(1) space. A common interview question, so it's worth knowing the iterative version by heart.",
    'bst': "The BST invariant: for every node, all keys in the left subtree are smaller and all in the right subtree are larger. Search/insert/delete are O(log n) on a balanced tree but degrade to O(n) on a degenerate (insertion-sorted) tree — use a self-balancing variant (AVL, red-black) when inputs can be adversarial.",
    'graph_traversal': "BFS uses a queue and finds shortest paths in unweighted graphs; DFS uses a stack (or recursion) and is better for exploring connectivity and cycles. Both run in O(V + E). Always track visited nodes to avoid infinite loops on cyclic graphs.",
    'regex_email': "RFC 5322 email addresses are notoriously complex; the common `[^@\\s]+@[^@\\s]+\\.[^@\\s]+` pattern covers the vast majority of real-world inputs. For production, pair the regex with a length check and avoid rejecting valid-but-unusual addresses.",
    'regex_phone': "Phone formats vary wildly by country. The pattern here accepts common US formats; for international numbers use a library like libphonenumber rather than a hand-written regex.",
    'regex_password': "Requiring uppercase, lowercase, digit, and special character plus a minimum length is the standard policy. Note that over-strict password rules often push users toward weaker, reused passwords — length is the strongest single factor.",
    'regex_url': "A pragmatic URL pattern accepts scheme://host/path with optional query string and fragment. For parsing (not just validation), use your language's URL/URI class instead of regex.",
    'extract_emails': "The regex finds `user@domain.tld` patterns inside arbitrary text. In production, prefer a well-tested email-extraction library — spammers deliberately craft strings that fool naive regexes.",
    'read_csv': "Use the csv module for anything with quoted fields, embedded commas, or newlines — naive `split(',')` breaks on those. pandas is the heavyweight option when you also need filtering, grouping, or plotting.",
    'write_csv': "Always open CSV files with `newline=''` in Python — otherwise the csv module can write stray blank lines on Windows. `csv.writer` handles quoting and escaping for you.",
    'read_file': "Use a context manager (with) so the file is closed even when an exception occurs. For large files, iterate line by line instead of calling read() to avoid loading the whole file into memory.",
    'write_file': "The `'w'` mode truncates the file; use `'a'` to append. Text encodings matter — specify `encoding='utf-8'` explicitly when the content is not plain ASCII.",
    'read_json': "JSON keys are case-sensitive and the format has no comments or trailing commas. Validate the file with a linter before parsing to get better error messages.",
    'write_json': "`json.dumps` with `indent=2` produces human-readable output. For non-ASCII text, `ensure_ascii=False` keeps the characters readable. A trailing newline at the end of the file is good practice.",
    'http_get': "Always check the response status code and handle network errors. Set a timeout so a slow endpoint can't hang your program. For JSON APIs, decode the body before parsing.",
    'http_post': "Set the `Content-Type: application/json` header when sending a JSON body, and make sure to encode the payload as JSON (not a Python dict or JS object) — forgetting the encoding is the most common 400-error cause.",
    'web_scrape': "Respect the site's robots.txt and terms of service, and rate-limit your requests. Many sites offer an official API that is more reliable than scraping. The scraper below uses only the standard library plus requests/BeautifulSoup-style helpers — install them with pip.",
    'fetch_table': "The `fetch` API returns a promise, so the function is async and awaits the response. Build table rows with `textContent` (not `innerHTML`) to avoid XSS when the data is user-controlled.",
    'express_api': "Express is the most widely used Node.js web framework. `app.listen` starts the server; `express.json()` middleware is required to parse JSON request bodies.",
    'flask_api': "Flask's `@app.route` decorator binds a URL to a handler. Return a dict or use `jsonify` to send JSON. For production, use a WSGI server like gunicorn — `app.run()` is only for development.",
    'sql_select': "Use explicit column lists instead of `SELECT *` in production code so schema changes don't silently break your queries. Add LIMIT while exploring large tables.",
    'sql_insert': "Column lists make the statement resilient to schema changes (adding a column won't break the insert). Use parameterized queries to avoid SQL injection — never concatenate user input into SQL strings.",
    'sql_update': "An UPDATE without a WHERE clause updates every row in the table. Run a SELECT with the same WHERE first to confirm which rows you're about to change.",
    'sql_delete': "A DELETE without a WHERE clause empties the table — always scope it with a WHERE and consider a transaction so you can roll back. Most production systems use soft deletes (a deleted_at flag) instead.",
    'sql_join': "INNER JOIN returns only matching rows; LEFT JOIN keeps all rows from the left table, filling NULLs for non-matching right rows. Pick the join type by what you want to happen to unmatched rows.",
    'sql_group_by': "Every column in the SELECT list that isn't wrapped in an aggregate function must appear in the GROUP BY clause — most SQL engines enforce this and error out if you forget.",
    'sql_duplicates': "The HAVING clause filters groups after aggregation (WHERE filters before). Group by the columns that define what 'duplicate' means — grouping by every column finds exact-row duplicates; grouping by a key column finds records sharing that key.",
    'sql_create_table': "Choose types carefully — changing them later requires an ALTER TABLE migration. PRIMARY KEY enforces uniqueness, NOT NULL rejects missing values, and a foreign key keeps related tables consistent.",
    'sql_aggregate': "Aggregates (COUNT, SUM, AVG, MIN, MAX) collapse many rows into one. COUNT(*) counts rows including NULLs; COUNT(col) counts only non-NULL values — a classic gotcha.",
    'git_undo': "The safe rule: never rewrite history that has been pushed. `git reset` rewrites history (use it only locally); `git revert` adds a new commit that undoes the changes (safe to push).",
    'git_commit': "Commit small, focused changes with a clear message, and commit early and often. `git status` and `git diff` before staging prevent accidentally committing debugging leftovers.",
    'git_branch': "Branches are cheap pointers to commits — create one per feature or fix. Merge with `git merge` for a merge commit or `git rebase` for a linear history (never rebase shared branches).",
    'git_stash': "`git stash` is for when you must switch branches mid-work. `git stash pop` restores and removes the stash; use `git stash apply` if you want to keep it. Stashes are local — they never push.",
    'git_log': "`git log --oneline` gives a compact history; `--graph` shows branch topology. Add `--author`, `--since`, or `-S` to filter. `git log -p` shows the actual diffs.",
    'bash_file_ops': "`find` is more powerful than `ls` for searching; `grep -r` searches inside files. `chmod` uses octal modes (755 = rwxr-xr-x) or symbolic ones (u+x). Always quote filenames with spaces.",
    'bash_curl': "`curl -s` silences the progress meter, `-o` writes to a file, and `-X POST -d '...'` sends a request body. Add `-H 'Content-Type: application/json'` when posting JSON, and `-i` to see response headers.",
    'chunk_list': "The slicing idiom `lst[i:i+size]` is O(size) per slice, so chunking the whole list is O(n). The final chunk is shorter when the length isn't a multiple of the chunk size — that's expected.",
    'transpose_matrix': "Transposing an m×n matrix gives an n×m one. `zip(*matrix)` is the Python one-liner but returns tuples — wrap each row in list() if you need mutable rows. The nested-list version is the explicit equivalent.",
    'count_words': "Lowercasing and splitting on whitespace handles most real text. For production-grade counting, strip punctuation too (the regex version) so 'Hello,' and 'hello' count as the same word.",
    'slugify': "The recipe: lowercase, replace non-alphanumerics with dashes, collapse runs of dashes, strip edges. Transliteration of accented characters (é → e) needs an extra library step in most languages.",
    'caesar_cipher': "A Caesar cipher shifts every letter by a fixed amount (rot13 is the classic). It's trivially breakable — use it for puzzles, not security. The `% 26` wrap-around is the part people get wrong.",
    'password_gen': "`secrets` (Python) and `crypto.getRandomValues` (JS) are cryptographically secure; `random`/`Math.random` are NOT safe for passwords. Include upper, lower, digits, and specials for strength.",
    'shuffle_list': "Fisher–Yates (the 'inside-out' loop) gives every permutation equal probability — the naive 'sort by random' approach is biased. Iterate from the end backward so each slot is swapped exactly once.",
    'memoize': "Memoization turns exponential recursion (naive Fibonacci) into O(n) by caching per-argument results. It only helps when the same arguments repeat — it's useless for one-shot calls and unbounded caches can leak memory (clear them or cap size).",
    'retry_backoff': "Backoff (0.5s, 1s, 2s, …) prevents hammering a failing service; jitter (±random) prevents synchronized retry storms. Only retry idempotent operations — retrying a non-idempotent POST can double-create resources.",
    'json_pretty': "`json.dumps(obj, indent=2)` (Python) and `JSON.stringify(obj, null, 2)` (JS) are the one-liners. Add `sort_keys=True` / sorted keys for deterministic, diff-friendly output.",
}


# ── Code templates per task per language ───────────────────────────────────
# Raw strings only — never .format() these (braces in JS/C++/Java/Go/Rust).
_CODE = {
    # ─────────────────────────── algorithms ────────────────────────────
    'prime': {
        'python': r'''def is_prime(n: int) -> bool:
    if n < 2:
        return False
    if n in (2, 3):
        return True
    if n % 2 == 0 or n % 3 == 0:
        return False
    i = 5
    while i * i <= n:
        if n % i == 0 or n % (i + 2) == 0:
            return False
        i += 6
    return True

# Example:
for x in (2, 17, 15, 97, 100):
    print(x, is_prime(x))''',
        'javascript': r'''function isPrime(n) {
    if (n < 2) return false;
    if (n === 2 || n === 3) return true;
    if (n % 2 === 0 || n % 3 === 0) return false;
    for (let i = 5; i * i <= n; i += 6) {
        if (n % i === 0 || n % (i + 2) === 0) return false;
    }
    return true;
}

// Example:
[2, 17, 15, 97, 100].forEach(x => console.log(x, isPrime(x)));''',
        'java': r'''public static boolean isPrime(int n) {
    if (n < 2) return false;
    if (n == 2 || n == 3) return true;
    if (n % 2 == 0 || n % 3 == 0) return false;
    for (int i = 5; (long) i * i <= n; i += 6) {
        if (n % i == 0 || n % (i + 2) == 0) return false;
    }
    return true;
}''',
        'c++': r'''bool isPrime(int n) {
    if (n < 2) return false;
    if (n == 2 || n == 3) return true;
    if (n % 2 == 0 || n % 3 == 0) return false;
    for (int i = 5; (long long) i * i <= n; i += 6) {
        if (n % i == 0 || n % (i + 2) == 0) return false;
    }
    return true;
}''',
        'c#': r'''static bool IsPrime(int n)
{
    if (n < 2) return false;
    if (n == 2 || n == 3) return true;
    if (n % 2 == 0 || n % 3 == 0) return false;
    for (int i = 5; (long) i * i <= n; i += 6)
        if (n % i == 0 || n % (i + 2) == 0) return false;
    return true;
}''',
        'go': r'''func IsPrime(n int) bool {
    if n < 2 {
        return false
    }
    if n == 2 || n == 3 {
        return true
    }
    if n%2 == 0 || n%3 == 0 {
        return false
    }
    for i := 5; i*i <= n; i += 6 {
        if n%i == 0 || n%(i+2) == 0 {
            return false
        }
    }
    return true
}''',
        'rust': r'''fn is_prime(n: u64) -> bool {
    if n < 2 {
        return false;
    }
    if n == 2 || n == 3 {
        return true;
    }
    if n % 2 == 0 || n % 3 == 0 {
        return false;
    }
    let mut i = 5u64;
    while i * i <= n {
        if n % i == 0 || n % (i + 2) == 0 {
            return false;
        }
        i += 6;
    }
    true
}''',
        'typescript': r'''function isPrime(n: number): boolean {
    if (n < 2) return false;
    if (n === 2 || n === 3) return true;
    if (n % 2 === 0 || n % 3 === 0) return false;
    for (let i = 5; i * i <= n; i += 6) {
        if (n % i === 0 || n % (i + 2) === 0) return false;
    }
    return true;
}''',
    },
    'factorial': {
        'python': r'''def factorial(n: int) -> int:
    if n < 0:
        raise ValueError("factorial is not defined for negative numbers")
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result

# Example:
print(factorial(5))  # 120''',
        'javascript': r'''function factorial(n) {
    if (n < 0) throw new Error('factorial is not defined for negative numbers');
    let result = 1;
    for (let i = 2; i <= n; i++) result *= i;
    return result;
}

// Example:
console.log(factorial(5));  // 120''',
        'java': r'''public static long factorial(int n) {
    if (n < 0) throw new IllegalArgumentException("negative input");
    long result = 1;
    for (int i = 2; i <= n; i++) result *= i;
    return result;
}''',
        'c++': r'''long long factorial(int n) {
    if (n < 0) throw std::invalid_argument("negative input");
    long long result = 1;
    for (int i = 2; i <= n; i++) result *= i;
    return result;
}''',
        'go': r'''func Factorial(n int) (int64, error) {
    if n < 0 {
        return 0, fmt.Errorf("factorial not defined for negative numbers")
    }
    result := int64(1)
    for i := 2; i <= n; i++ {
        result *= int64(i)
    }
    return result, nil
}''',
        'rust': r'''fn factorial(n: u64) -> u64 {
    (1..=n).product()
}''',
    },
    'fibonacci': {
        'python': r'''def fibonacci(n: int) -> list[int]:
    """Return the first n Fibonacci numbers."""
    if n <= 0:
        return []
    seq = [0, 1]
    while len(seq) < n:
        seq.append(seq[-1] + seq[-2])
    return seq[:n]

# Example:
print(fibonacci(10))  # [0, 1, 1, 2, 3, 5, 8, 13, 21, 34]''',
        'javascript': r'''function fibonacci(n) {
    if (n <= 0) return [];
    const seq = [0, 1];
    while (seq.length < n) {
        seq.push(seq[seq.length - 1] + seq[seq.length - 2]);
    }
    return seq.slice(0, n);
}

// Example:
console.log(fibonacci(10));  // [0, 1, 1, 2, 3, 5, 8, 13, 21, 34]''',
        'java': r'''public static List<Long> fibonacci(int n) {
    List<Long> seq = new ArrayList<>();
    if (n <= 0) return seq;
    seq.add(0L);
    if (n == 1) return seq;
    seq.add(1L);
    while (seq.size() < n) {
        seq.add(seq.get(seq.size() - 1) + seq.get(seq.size() - 2));
    }
    return seq;
}''',
        'c++': r'''std::vector<long long> fibonacci(int n) {
    std::vector<long long> seq;
    if (n <= 0) return seq;
    seq.push_back(0);
    if (n == 1) return seq;
    seq.push_back(1);
    while ((int) seq.size() < n) {
        seq.push_back(seq[seq.size() - 1] + seq[seq.size() - 2]);
    }
    return seq;
}''',
        'go': r'''func Fibonacci(n int) []int64 {
    seq := []int64{}
    if n <= 0 {
        return seq
    }
    seq = append(seq, 0)
    if n == 1 {
        return seq
    }
    seq = append(seq, 1)
    for len(seq) < n {
        seq = append(seq, seq[len(seq)-1]+seq[len(seq)-2])
    }
    return seq
}''',
        'rust': r'''fn fibonacci(n: usize) -> Vec<u64> {
    if n == 0 {
        return vec![];
    }
    let mut seq = vec![0u64, 1u64];
    while seq.len() < n {
        let next = seq[seq.len() - 1] + seq[seq.len() - 2];
        seq.push(next);
    }
    seq.truncate(n);
    seq
}''',
    },
    'fizzbuzz': {
        'python': r'''def fizzbuzz(n: int) -> None:
    for i in range(1, n + 1):
        if i % 15 == 0:
            print("FizzBuzz")
        elif i % 3 == 0:
            print("Fizz")
        elif i % 5 == 0:
            print("Buzz")
        else:
            print(i)

fizzbuzz(15)''',
        'javascript': r'''function fizzbuzz(n) {
    for (let i = 1; i <= n; i++) {
        if (i % 15 === 0) console.log('FizzBuzz');
        else if (i % 3 === 0) console.log('Fizz');
        else if (i % 5 === 0) console.log('Buzz');
        else console.log(i);
    }
}

fizzbuzz(15);''',
        'java': r'''for (int i = 1; i <= 100; i++) {
    if (i % 15 == 0) System.out.println("FizzBuzz");
    else if (i % 3 == 0) System.out.println("Fizz");
    else if (i % 5 == 0) System.out.println("Buzz");
    else System.out.println(i);
}''',
        'c++': r'''for (int i = 1; i <= 100; i++) {
    if (i % 15 == 0) std::cout << "FizzBuzz\\n";
    else if (i % 3 == 0) std::cout << "Fizz\\n";
    else if (i % 5 == 0) std::cout << "Buzz\\n";
    else std::cout << i << "\\n";
}''',
        'go': r'''func FizzBuzz(n int) {
    for i := 1; i <= n; i++ {
        switch {
        case i%15 == 0:
            fmt.Println("FizzBuzz")
        case i%3 == 0:
            fmt.Println("Fizz")
        case i%5 == 0:
            fmt.Println("Buzz")
        default:
            fmt.Println(i)
        }
    }
}''',
        'rust': r'''fn fizzbuzz(n: u32) {
    for i in 1..=n {
        match (i % 3, i % 5) {
            (0, 0) => println!("FizzBuzz"),
            (0, _) => println!("Fizz"),
            (_, 0) => println!("Buzz"),
            _ => println!("{i}"),
        }
    }
}''',
    },
    'gcd': {
        'python': r'''def gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return abs(a)

def lcm(a: int, b: int) -> int:
    return abs(a * b) // gcd(a, b)

# Example:
print(gcd(48, 18))  # 6
print(lcm(4, 6))    # 12''',
        'javascript': r'''function gcd(a, b) {
    while (b) [a, b] = [b, a % b];
    return Math.abs(a);
}

function lcm(a, b) {
    return Math.abs(a * b) / gcd(a, b);
}''',
        'java': r'''public static int gcd(int a, int b) {
    while (b != 0) {
        int t = b;
        b = a % b;
        a = t;
    }
    return Math.abs(a);
}''',
        'c++': r'''int gcd(int a, int b) {
    while (b != 0) {
        int t = b;
        b = a % b;
        a = t;
    }
    return std::abs(a);
}''',
        'go': r'''func GCD(a, b int) int {
    for b != 0 {
        a, b = b, a%b
    }
    return a
}''',
        'rust': r'''fn gcd(a: u64, b: u64) -> u64 {
    let (mut a, mut b) = (a, b);
    while b != 0 {
        let t = b;
        b = a % b;
        a = t;
    }
    a
}''',
    },
    'binary_search': {
        'python': r'''def binary_search(arr: list[int], target: int) -> int:
    """Return the index of target in sorted arr, or -1."""
    left, right = 0, len(arr) - 1
    while left <= right:
        mid = left + (right - left) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1

# Example:
print(binary_search([1, 3, 5, 7, 9, 11], 7))  # 3''',
        'javascript': r'''function binarySearch(arr, target) {
    let left = 0, right = arr.length - 1;
    while (left <= right) {
        const mid = left + Math.floor((right - left) / 2);
        if (arr[mid] === target) return mid;
        if (arr[mid] < target) left = mid + 1;
        else right = mid - 1;
    }
    return -1;
}''',
        'java': r'''public static int binarySearch(int[] arr, int target) {
    int left = 0, right = arr.length - 1;
    while (left <= right) {
        int mid = left + (right - left) / 2;
        if (arr[mid] == target) return mid;
        if (arr[mid] < target) left = mid + 1;
        else right = mid - 1;
    }
    return -1;
}''',
        'c++': r'''int binarySearch(const std::vector<int>& arr, int target) {
    int left = 0, right = (int) arr.size() - 1;
    while (left <= right) {
        int mid = left + (right - left) / 2;
        if (arr[mid] == target) return mid;
        if (arr[mid] < target) left = mid + 1;
        else right = mid - 1;
    }
    return -1;
}''',
        'go': r'''func BinarySearch(arr []int, target int) int {
    left, right := 0, len(arr)-1
    for left <= right {
        mid := left + (right-left)/2
        if arr[mid] == target {
            return mid
        }
        if arr[mid] < target {
            left = mid + 1
        } else {
            right = mid - 1
        }
    }
    return -1
}''',
        'rust': r'''fn binary_search(arr: &[i32], target: i32) -> Option<usize> {
    let mut left = 0usize;
    let mut right = arr.len();
    while left < right {
        let mid = left + (right - left) / 2;
        match arr[mid].cmp(&target) {
            std::cmp::Ordering::Equal => return Some(mid),
            std::cmp::Ordering::Less => left = mid + 1,
            std::cmp::Ordering::Greater => right = mid,
        }
    }
    None
}''',
    },
    'merge_sorted': {
        'python': r'''def merge_sorted(a: list[int], b: list[int]) -> list[int]:
    merged = []
    i = j = 0
    while i < len(a) and j < len(b):
        if a[i] <= b[j]:
            merged.append(a[i])
            i += 1
        else:
            merged.append(b[j])
            j += 1
    merged.extend(a[i:])
    merged.extend(b[j:])
    return merged

# Example:
print(merge_sorted([1, 3, 5], [2, 4, 6]))  # [1, 2, 3, 4, 5, 6]''',
        'javascript': r'''function mergeSorted(a, b) {
    const merged = [];
    let i = 0, j = 0;
    while (i < a.length && j < b.length) {
        if (a[i] <= b[j]) merged.push(a[i++]);
        else merged.push(b[j++]);
    }
    return merged.concat(a.slice(i), b.slice(j));
}''',
        'java': r'''public static int[] mergeSorted(int[] a, int[] b) {
    int[] merged = new int[a.length + b.length];
    int i = 0, j = 0, k = 0;
    while (i < a.length && j < b.length) {
        if (a[i] <= b[j]) merged[k++] = a[i++];
        else merged[k++] = b[j++];
    }
    while (i < a.length) merged[k++] = a[i++];
    while (j < b.length) merged[k++] = b[j++];
    return merged;
}''',
        'c++': r'''std::vector<int> mergeSorted(const std::vector<int>& a,
                              const std::vector<int>& b) {
    std::vector<int> merged;
    merged.reserve(a.size() + b.size());
    size_t i = 0, j = 0;
    while (i < a.size() && j < b.size()) {
        if (a[i] <= b[j]) merged.push_back(a[i++]);
        else merged.push_back(b[j++]);
    }
    merged.insert(merged.end(), a.begin() + i, a.end());
    merged.insert(merged.end(), b.begin() + j, b.end());
    return merged;
}''',
        'go': r'''func MergeSorted(a, b []int) []int {
    merged := make([]int, 0, len(a)+len(b))
    i, j := 0, 0
    for i < len(a) && j < len(b) {
        if a[i] <= b[j] {
            merged = append(merged, a[i])
            i++
        } else {
            merged = append(merged, b[j])
            j++
        }
    }
    merged = append(merged, a[i:]...)
    merged = append(merged, b[j:]...)
    return merged
}''',
        'rust': r'''fn merge_sorted(a: &[i32], b: &[i32]) -> Vec<i32> {
    let mut merged = Vec::with_capacity(a.len() + b.len());
    let (mut i, mut j) = (0, 0);
    while i < a.len() && j < b.len() {
        if a[i] <= b[j] {
            merged.push(a[i]);
            i += 1;
        } else {
            merged.push(b[j]);
            j += 1;
        }
    }
    merged.extend_from_slice(&a[i..]);
    merged.extend_from_slice(&b[j..]);
    merged
}''',
    },
    'sort_list': {
        'python': r'''# In-place sort (modifies the list):
numbers = [3, 1, 4, 1, 5, 9, 2]
numbers.sort()
print(numbers)  # [1, 1, 2, 3, 4, 5, 9]

# Return a new sorted list (any iterable):
words = ['banana', 'apple', 'cherry']
sorted_words = sorted(words)          # ['apple', 'banana', 'cherry']

# Custom key (sort dicts by a field, strings by length, ...):
people = [{'name': 'Alice', 'age': 30}, {'name': 'Bob', 'age': 25}]
by_age = sorted(people, key=lambda p: p['age'])

# Descending:
numbers.sort(reverse=True)''',
        'javascript': r'''// sort() sorts in place; with no comparator it sorts by UTF-16 code units,
// so numbers need an explicit comparator:
const numbers = [3, 1, 4, 1, 5, 9, 2];
numbers.sort((a, b) => a - b);
console.log(numbers);  // [1, 1, 2, 3, 4, 5, 9]

// Descending:
numbers.sort((a, b) => b - a);

// Sort objects by a property:
const people = [{name: 'Alice', age: 30}, {name: 'Bob', age: 25}];
people.sort((a, b) => a.age - b.age);''',
        'java': r'''import java.util.*;

// Arrays:
int[] nums = {3, 1, 4, 1, 5};
Arrays.sort(nums);                    // ascending, in place
// Boxed arrays / lists for reverse order:
Integer[] boxed = {3, 1, 4, 1, 5};
Arrays.sort(boxed, Collections.reverseOrder());

// Lists:
List<Integer> list = new ArrayList<>(List.of(3, 1, 4, 1, 5));
Collections.sort(list);
list.sort(Comparator.reverseOrder());

// Sort objects by a field:
people.sort(Comparator.comparingInt(p -> p.age));''',
        'c++': r'''#include <algorithm>
#include <vector>

std::vector<int> nums = {3, 1, 4, 1, 5};
std::sort(nums.begin(), nums.end());          // ascending
std::sort(nums.begin(), nums.end(), std::greater<int>());  // descending
// Custom comparator:
std::sort(v.begin(), v.end(), [](const Person& a, const Person& b) {
    return a.age < b.age;
});''',
        'go': r'''import "sort"

nums := []int{3, 1, 4, 1, 5}
sort.Ints(nums)                       // ascending, in place
sort.Sort(sort.Reverse(sort.IntSlice(nums)))  // descending

// Sort a slice of structs by a field:
sort.Slice(people, func(i, j int) bool {
    return people[i].Age < people[j].Age
})''',
        'rust': r'''let mut nums = vec![3, 1, 4, 1, 5];
nums.sort();                          // ascending, in place
nums.sort_by(|a, b| b.cmp(a));        // descending

// Sort structs by a field:
people.sort_by_key(|p| p.age);''',
    },
    'reverse_string': {
        'python': r'''def reverse_string(s: str) -> str:
    return s[::-1]

# Example:
print(reverse_string('hello'))  # 'olleh'

# Alternative (handles surrogate pairs correctly):
def reverse_string_alt(s: str) -> str:
    return ''.join(reversed(s))''',
        'javascript': r'''function reverseString(s) {
    return [...s].reverse().join('');
}

// Example:
console.log(reverseString('hello'));  // 'olleh'
// Note: [...s] iterates by code point, so emoji/surrogate pairs survive.
// s.split('').reverse().join('') would corrupt them.''',
        'java': r'''public static String reverseString(String s) {
    return new StringBuilder(s).reverse().toString();
}''',
        'c++': r'''std::string reverseString(std::string s) {
    std::reverse(s.begin(), s.end());
    return s;
}''',
        'go': r'''import "strings"

func ReverseString(s string) string {
    // Rune-aware: handles multi-byte UTF-8 characters.
    runes := []rune(s)
    for i, j := 0, len(runes)-1; i < j; i, j = i+1, j-1 {
        runes[i], runes[j] = runes[j], runes[i]
    }
    return string(runes)
}''',
        'rust': r'''fn reverse_string(s: &str) -> String {
    // .chars() iterates by Unicode scalar value (not bytes).
    s.chars().rev().collect()
}''',
        'c#': r'''static string ReverseString(string s)
{
    char[] chars = s.ToCharArray();
    Array.Reverse(chars);
    return new string(chars);
}''',
    },
    'reverse_array': {
        'python': r'''def reverse_array(arr: list) -> list:
    left, right = 0, len(arr) - 1
    while left < right:
        arr[left], arr[right] = arr[right], arr[left]
        left += 1
        right -= 1
    return arr

# Example:
nums = [1, 2, 3, 4, 5]
print(reverse_array(nums))  # [5, 4, 3, 2, 1]
# In-place one-liner: nums.reverse()   New list: nums[::-1]''',
        'javascript': r'''function reverseArray(arr) {
    let left = 0, right = arr.length - 1;
    while (left < right) {
        [arr[left], arr[right]] = [arr[right], arr[left]];
        left++;
        right--;
    }
    return arr;
}

// In-place method: arr.reverse()''',
        'java': r'''public static void reverseArray(int[] arr) {
    int left = 0, right = arr.length - 1;
    while (left < right) {
        int tmp = arr[left];
        arr[left] = arr[right];
        arr[right] = tmp;
        left++;
        right--;
    }
}''',
        'c++': r'''template <typename T>
void reverseArray(std::vector<T>& arr) {
    size_t left = 0, right = arr.size();
    while (left < right) {
        std::swap(arr[left], arr[right - 1]);
        left++;
        right--;
    }
}
// Or simply: std::reverse(arr.begin(), arr.end());''',
        'go': r'''func ReverseArray(arr []int) {
    for i, j := 0, len(arr)-1; i < j; i, j = i+1, j-1 {
        arr[i], arr[j] = arr[j], arr[i]
    }
}''',
        'rust': r'''fn reverse_array(arr: &mut [i32]) {
    let mut left = 0;
    let mut right = arr.len();
    while left < right {
        arr.swap(left, right - 1);
        left += 1;
        right -= 1;
    }
}
// Or simply: arr.reverse();''',
    },
    'palindrome_string': {
        'python': r'''def is_palindrome(s: str) -> bool:
    # Normalize: lowercase and drop non-alphanumeric characters.
    cleaned = ''.join(c.lower() for c in s if c.isalnum())
    return cleaned == cleaned[::-1]

# Examples:
print(is_palindrome('racecar'))        # True
print(is_palindrome('A man, a plan, a canal: Panama'))  # True
print(is_palindrome('hello'))          # False''',
        'javascript': r'''function isPalindrome(s) {
    const cleaned = s.toLowerCase().replace(/[^a-z0-9]/g, '');
    return cleaned === [...cleaned].reverse().join('');
}

// Examples:
console.log(isPalindrome('racecar'));   // true
console.log(isPalindrome('A man, a plan, a canal: Panama'));  // true''',
        'java': r'''public static boolean isPalindrome(String s) {
    String cleaned = s.toLowerCase().replaceAll("[^a-z0-9]", "");
    return new StringBuilder(cleaned).reverse().toString().equals(cleaned);
}''',
        'c++': r'''bool isPalindrome(const std::string& s) {
    int left = 0, right = (int) s.size() - 1;
    while (left < right) {
        while (left < right && !std::isalnum(s[left])) left++;
        while (left < right && !std::isalnum(s[right])) right--;
        if (std::tolower(s[left]) != std::tolower(s[right])) return false;
        left++;
        right--;
    }
    return true;
}''',
        'go': r'''func IsPalindrome(s string) bool {
    var cleaned []rune
    for _, r := range s {
        if unicode.IsLetter(r) || unicode.IsDigit(r) {
            cleaned = append(cleaned, unicode.ToLower(r))
        }
    }
    for i, j := 0, len(cleaned)-1; i < j; i, j = i+1, j-1 {
        if cleaned[i] != cleaned[j] {
            return false
        }
    }
    return true
}''',
        'rust': r'''fn is_palindrome(s: &str) -> bool {
    let cleaned: String = s
        .chars()
        .filter(|c| c.is_alphanumeric())
        .flat_map(|c| c.to_lowercase())
        .collect();
    cleaned.chars().eq(cleaned.chars().rev())
}''',
    },
    'anagram': {
        'python': r'''from collections import Counter

def are_anagrams(a: str, b: str) -> bool:
    norm = lambda s: Counter(c.lower() for c in s if c.isalnum())
    return norm(a) == norm(b)

# Examples:
print(are_anagrams('listen', 'silent'))   # True
print(are_anagrams('rail safety', 'fairy tales'))  # True
print(are_anagrams('hello', 'world'))     # False''',
        'javascript': r'''function areAnagrams(a, b) {
    const norm = s => s.toLowerCase().replace(/[^a-z0-9]/g, '').split('').sort().join('');
    return norm(a) === norm(b);
}

// Examples:
console.log(areAnagrams('listen', 'silent'));       // true
console.log(areAnagrams('rail safety', 'fairy tales'));  // true''',
        'java': r'''public static boolean areAnagrams(String a, String b) {
    char[] x = a.toLowerCase().replaceAll("[^a-z0-9]", "").toCharArray();
    char[] y = b.toLowerCase().replaceAll("[^a-z0-9]", "").toCharArray();
    Arrays.sort(x);
    Arrays.sort(y);
    return Arrays.equals(x, y);
}''',
        'c++': r'''bool areAnagrams(const std::string& a, const std::string& b) {
    auto norm = [](std::string s) {
        s.erase(std::remove_if(s.begin(), s.end(),
            [](unsigned char c) { return !std::isalnum(c); }), s.end());
        std::transform(s.begin(), s.end(), s.begin(),
            [](unsigned char c) { return std::tolower(c); });
        std::sort(s.begin(), s.end());
        return s;
    };
    return norm(a) == norm(b);
}''',
        'go': r'''func AreAnagrams(a, b string) bool {
    norm := func(s string) string {
        runes := []rune{}
        for _, r := range s {
            if unicode.IsLetter(r) || unicode.IsDigit(r) {
                runes = append(runes, unicode.ToLower(r))
            }
        }
        sort.Slice(runes, func(i, j int) bool { return runes[i] < runes[j] })
        return string(runes)
    }
    return norm(a) == norm(b)
}''',
        'rust': r'''fn are_anagrams(a: &str, b: &str) -> bool {
    let norm = |s: &str| -> Vec<char> {
        let mut v: Vec<char> = s
            .chars()
            .filter(|c| c.is_alphanumeric())
            .flat_map(|c| c.to_lowercase())
            .collect();
        v.sort_unstable();
        v
    };
    norm(a) == norm(b)
}''',
    },
    'most_frequent': {
        'python': r'''from collections import Counter

def most_frequent(items: list) -> object:
    if not items:
        return None
    counts = Counter(items)
    return counts.most_common(1)[0][0]

# Example:
print(most_frequent([1, 3, 2, 3, 4, 3, 1]))  # 3

# Full ranking:
def frequency_ranking(items: list):
    return Counter(items).most_common()''',
        'javascript': r'''function mostFrequent(items) {
    if (items.length === 0) return undefined;
    const counts = new Map();
    for (const item of items) {
        counts.set(item, (counts.get(item) || 0) + 1);
    }
    let best, bestCount = 0;
    for (const [item, count] of counts) {
        if (count > bestCount) {
            best = item;
            bestCount = count;
        }
    }
    return best;
}''',
        'java': r'''public static <T> T mostFrequent(List<T> items) {
    Map<T, Long> counts = items.stream()
        .collect(Collectors.groupingBy(Function.identity(), Collectors.counting()));
    return counts.entrySet().stream()
        .max(Map.Entry.comparingByValue())
        .map(Map.Entry::getKey)
        .orElse(null);
}''',
        'c++': r'''#include <unordered_map>

int mostFrequent(const std::vector<int>& items) {
    std::unordered_map<int, int> counts;
    for (int x : items) counts[x]++;
    int best = 0, bestCount = 0;
    for (auto& [x, c] : counts) {
        if (c > bestCount) {
            best = x;
            bestCount = c;
        }
    }
    return best;
}''',
        'go': r'''func MostFrequent(items []int) (int, bool) {
    counts := map[int]int{}
    for _, x := range items {
        counts[x]++
    }
    best, bestCount := 0, 0
    for x, c := range counts {
        if c > bestCount {
            best, bestCount = x, c
        }
    }
    return best, bestCount > 0
}''',
        'rust': r'''use std::collections::HashMap;

fn most_frequent(items: &[i32]) -> Option<i32> {
    let mut counts: HashMap<i32, usize> = HashMap::new();
    for &x in items {
        *counts.entry(x).or_insert(0) += 1;
    }
    counts.into_iter().max_by_key(|(_, c)| *c).map(|(x, _)| x)
}''',
    },
    'count_occurrences': {
        'python': r'''from collections import Counter

def count_occurrences(items: list) -> dict:
    return dict(Counter(items))

# Example:
print(count_occurrences(['a', 'b', 'a', 'c', 'a', 'b']))
# {'a': 3, 'b': 2, 'c': 1}

# Word frequency in a text:
text = "the cat and the dog and the bird"
word_counts = Counter(text.lower().split())
print(word_counts.most_common(3))''',
        'javascript': r'''function countOccurrences(items) {
    const counts = {};
    for (const item of items) {
        counts[item] = (counts[item] || 0) + 1;
    }
    return counts;
}

// Example:
console.log(countOccurrences(['a', 'b', 'a', 'c', 'a', 'b']));
// { a: 3, b: 2, c: 1 }''',
        'java': r'''public static Map<String, Long> countOccurrences(List<String> items) {
    return items.stream()
        .collect(Collectors.groupingBy(Function.identity(), Collectors.counting()));
}''',
        'c++': r'''std::unordered_map<std::string, int> countOccurrences(
    const std::vector<std::string>& items) {
    std::unordered_map<std::string, int> counts;
    for (const auto& s : items) counts[s]++;
    return counts;
}''',
        'go': r'''func CountOccurrences(items []string) map[string]int {
    counts := map[string]int{}
    for _, s := range items {
        counts[s]++
    }
    return counts
}''',
        'rust': r'''use std::collections::HashMap;

fn count_occurrences(items: &[&str]) -> HashMap<&str, usize> {
    let mut counts = HashMap::new();
    for &s in items {
        *counts.entry(s).or_insert(0) += 1;
    }
    counts
}''',
    },
    'for_loop': {
        'python': r'''# Loop over a range:
for i in range(5):
    print(i)        # 0 1 2 3 4

# Loop over a collection:
for item in ['a', 'b', 'c']:
    print(item)

# With index (enumerate):
for idx, item in enumerate(['a', 'b', 'c']):
    print(idx, item)

# Range with start and step:
for i in range(1, 10, 2):
    print(i)        # 1 3 5 7 9''',
        'javascript': r'''// Classic for loop (with index):
for (let i = 0; i < 5; i++) {
    console.log(i);
}

// for...of over an array:
for (const item of ['a', 'b', 'c']) {
    console.log(item);
}

// forEach (no break/continue):
['a', 'b', 'c'].forEach(item => console.log(item));

// With index:
['a', 'b', 'c'].forEach((item, idx) => console.log(idx, item));''',
        'java': r'''// Classic loop:
for (int i = 0; i < 5; i++) {
    System.out.println(i);
}

// Enhanced for (for-each) over an array:
String[] names = {"a", "b", "c"};
for (String name : names) {
    System.out.println(name);
}

// Over a List:
List<String> list = List.of("a", "b", "c");
for (String s : list) {
    System.out.println(s);
}''',
        'c++': r'''// Classic loop:
for (int i = 0; i < 5; i++) {
    std::cout << i << "\n";
}

// Range-based for (C++11+):
std::vector<std::string> names = {"a", "b", "c"};
for (const auto& name : names) {
    std::cout << name << "\n";
}

// With index:
for (size_t i = 0; i < names.size(); i++) {
    std::cout << i << " " << names[i] << "\n";
}''',
        'go': r'''// Classic loop:
for i := 0; i < 5; i++ {
    fmt.Println(i)
}

// Over a slice (index + value):
names := []string{"a", "b", "c"}
for i, name := range names {
    fmt.Println(i, name)
}

// While-style (Go has no while keyword):
n := 0
for n < 5 {
    n++
}''',
        'rust': r'''// Classic loop:
for i in 0..5 {
    println!("{i}");
}

// Over a vector:
let names = vec!["a", "b", "c"];
for name in &names {
    println!("{name}");
}

// With index (enumerate):
for (i, name) in names.iter().enumerate() {
    println!("{i} {name}");
}''',
    },
    'backup_dir': {
        'python': r'''#!/usr/bin/env python3
"""Back up a directory: timestamped copy, skipping junk."""
import os
import shutil
import sys
from datetime import datetime


def backup(source: str, dest_root: str = "backups") -> str:
    if not os.path.isdir(source):
        raise ValueError(f"not a directory: {source}")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = os.path.basename(os.path.normpath(source)) or "backup"
    dest = os.path.join(dest_root, f"{name}-{stamp}")
    os.makedirs(dest_root, exist_ok=True)
    shutil.copytree(
        source, dest,
        ignore=shutil.ignore_patterns("__pycache__", ".git", "node_modules",
                                      "*.pyc", ".DS_Store"),
    )
    return dest


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python3 backup.py <directory> [dest-root]")
        sys.exit(1)
    print("backed up to", backup(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "backups"))

# Example:
# backup("my_project", "backups")  ->  backups/my_project-20260403-153000''',
        'bash': r'''#!/usr/bin/env bash
# Back up a directory with a timestamp, skipping common junk.
set -euo pipefail

SOURCE="${1:?usage: $0 <directory> [dest-root]}"
DEST_ROOT="${2:-backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"
NAME="$(basename "$SOURCE")"
DEST="$DEST_ROOT/$NAME-$STAMP"

mkdir -p "$DEST_ROOT"
rsync -a --exclude node_modules --exclude .git --exclude __pycache__ \\
    --exclude '*.pyc' --exclude .DS_Store "$SOURCE/" "$DEST/"
echo "backed up to $DEST"''',
    },
    'comment_syntax': {
        'python': r'''# Single-line comment

"""
Multi-line string used as a docstring.
PEP 8: use # for real comments; """ for documentation.
"""

def add(a, b):
    """Return the sum of a and b."""
    return a + b''',
        'javascript': r'''// Single-line comment

/*
 * Multi-line comment
 */

// JSDoc for functions:
/**
 * Adds two numbers.
 * @param {number} a
 * @param {number} b
 * @returns {number}
 */
function add(a, b) {
    return a + b;
}''',
        'java': r'''// Single-line comment

/* Multi-line comment */

/** Javadoc comment (used to generate API docs) */
public static int add(int a, int b) {
    return a + b;
}''',
        'c++': r'''// Single-line comment

/* Multi-line comment */

/// Doxygen comment for documentation
int add(int a, int b) {
    return a + b;
}''',
        'c#': r'''// Single-line comment

/* Multi-line comment */

/// XML doc comment
static int Add(int a, int b) {
    return a + b;
}''',
        'go': r'''// Single-line comment

/* Multi-line comment */

// Doc comment directly above an exported name:
// Add returns the sum of a and b.
func Add(a, b int) int {
    return a + b
}''',
        'rust': r'''// Single-line comment

/* Multi-line comment */

/// Doc comment (rendered by rustdoc)
fn add(a: i32, b: i32) -> i32 {
    a + b
}''',
    },
    'array_contains': {
        'javascript': r'''const arr = ['apple', 'banana', 'cherry'];

// includes() — strict equality, works with NaN:
arr.includes('banana');   // true
arr.includes('pear');     // false

// indexOf() — returns the index or -1:
arr.indexOf('banana');    // 1
arr.indexOf('pear');      // -1

// some() — custom predicate:
arr.some(s => s.length > 6);   // true

// Fast repeated checks — use a Set:
const set = new Set(arr);
set.has('banana');        // true, O(1)''',
        'python': r'''items = ['apple', 'banana', 'cherry']

# 'in' operator (works on any iterable):
'banana' in items   # True
'pear' in items     # False

# index() raises ValueError when missing:
items.index('banana')   # 1

# Fast repeated checks — use a set:
seen = set(items)
'banana' in seen   # True, O(1)''',
    },
    'string_to_number': {
        'javascript': r'''// Number() — strict; returns NaN for non-numeric strings:
Number('42');      // 42
Number('42px');    // NaN

// parseInt() — reads a prefix and ignores the rest:
parseInt('42px');  // 42
parseInt('0x10');  // 16  (hex)

// Unary + (same as Number):
+'42';             // 42

// parseFloat() for decimals:
parseFloat('3.14');  // 3.14

// Robust pattern:
const num = Number(str);
if (Number.isNaN(num)) {
    // handle invalid input
}''',
        'python': r'''# int() / float() — strict; raise ValueError on bad input:
int('42')      # 42
float('3.14')  # 3.14

# int() accepts base 0/2/8/16 prefixes:
int('0x10', 0)  # 16
int('101', 2)   # 5

# Handle failures explicitly:
try:
    num = int(user_input)
except ValueError:
    print('not a number')''',
    },
    'rename_file': {
        'python': r'''import os
from pathlib import Path

# os.rename (files and directories):
os.rename('old.txt', 'new.txt')

# Path.rename (nicer API):
Path('old.txt').rename('new.txt')

# Move across directories:
os.rename('data/tmp.txt', 'archive/2026/tmp.txt')

# Handle errors:
if os.path.exists('old.txt'):
    os.rename('old.txt', 'new.txt')
else:
    print('source not found')''',
        'javascript': r'''const fs = require('fs');

// Rename (sync):
fs.renameSync('old.txt', 'new.txt');

// Rename (async):
await fs.promises.rename('old.txt', 'new.txt');

// With error handling:
try {
    await fs.promises.rename('old.txt', 'new.txt');
} catch (err) {
    console.error('rename failed:', err.message);
}''',
        'go': r'''import "os"

// os.Rename works for files and directories.
// It only fails across filesystems — use a copy+delete for that.
err := os.Rename("old.txt", "new.txt")
if err != nil {
    log.Fatal(err)
}''',
        'bash': r'''# Rename (or move) a file:
mv old.txt new.txt

# Move to another directory:
mv file.txt archive/file.txt

# Rename a directory:
mv old-dir new-dir

# Overwrite without prompting:
mv -f old.txt new.txt

# Move multiple files into a directory:
mv *.log logs/''',
    },
    'pip_install': {
        'bash': r'''# Install a package:
pip install requests

# Version-pinned (recommended for reproducibility):
pip install "requests==2.31.0"

# Install everything from a requirements file:
pip install -r requirements.txt

# Upgrade an installed package:
pip install --upgrade requests

# Best practice — install into a virtual environment first:
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install requests

# Snapshot current packages:
pip freeze > requirements.txt''',
    },
    'npm_install': {
        'bash': r'''# Install a package (saved to dependencies by default):
npm install express

# Dev-only dependency (build/test tooling):
npm install -D jest

# Version-pinned:
npm install express@4.19.2

# Install everything from package.json + lockfile:
npm install
npm ci          # clean, reproducible install (CI/deploys)

# Global install (CLI tools):
npm install -g typescript

# Uninstall:
npm uninstall express''',
    },
    'sys_disk': {
        'bash': r'''# Filesystem-level disk usage (human-readable):
df -h

# Per-directory usage from the current folder:
du -sh * | sort -h

# Biggest directories two levels deep (GNU/Linux):
du -h --max-depth=2 . | sort -rh | head -20
# macOS: du -h -d 2 . | sort -rh | head -20

# Which mount is full?
df -h | awk 'NR==1 || $5 ~ /^9[0-9]%|100%/'   # partitions at 90%+''',
    },
    'sys_mem': {
        'bash': r'''# Overview (total / used / available):
free -h

# Live view (press q to quit):
top
htop          # nicer, if installed

# Processes sorted by memory use:
ps aux --sort=-%mem | head -15

# Just the top memory consumer:
ps aux --sort=-%mem | head -2''',
    },
    'sys_kill': {
        'bash': r'''# 1. Find the process (PID):
ps aux | grep myapp
pgrep -f myapp

# 2. Kill gracefully (SIGTERM — lets it clean up):
kill 12345

# 3. Force kill (SIGKILL — cannot be caught):
kill -9 12345

# Kill by name (all matching processes):
pkill -f myapp

# Verify it's gone:
ps aux | grep myapp || echo 'process stopped'   # note: grep may match itself''',
    },
    'sys_port': {
        'bash': r'''# Which process is listening on port 8080?
sudo lsof -i :8080

# Modern alternative (no sudo needed for your own processes):
ss -tulpn | grep 8080

# Older systems:
netstat -tulpn | grep 8080

# Free the port (use the PID from the output above):
kill -9 <pid>

# List everything listening:
ss -tulpn''',
    },
    'sys_large_files': {
        'bash': r'''# Files larger than 100 MB in the current tree:
find . -type f -size +100M -exec ls -lh {} \;

# Top 10 largest files (GNU find):
find . -type f -printf '%s %p\n' | sort -rn | head -10
# macOS: find . -type f -exec ls -lh {} \; | awk '{print $5, $9}' | sort -rn | head -10

# Biggest directories:
du -sh */ | sort -rh | head -10''',
    },
    'dedup': {
        'python': r'''def dedup(items: list) -> list:
    """Remove duplicates while preserving first-occurrence order."""
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result

# Example:
print(dedup([3, 1, 3, 2, 1, 4, 3]))  # [3, 1, 2, 4]
# Order doesn't matter?  list(set(items))''',
        'javascript': r'''function dedup(items) {
    return [...new Set(items)];
}

// Example:
console.log(dedup([3, 1, 3, 2, 1, 4, 3]));  // [3, 1, 2, 4]''',
        'java': r'''public static List<Integer> dedup(List<Integer> items) {
    return new ArrayList<>(new LinkedHashSet<>(items));  // preserves order
}''',
        'c++': r'''#include <unordered_set>

std::vector<int> dedup(const std::vector<int>& items) {
    std::unordered_set<int> seen;
    std::vector<int> result;
    for (int x : items) {
        if (seen.insert(x).second) result.push_back(x);
    }
    return result;
}''',
        'go': r'''func Dedup(items []int) []int {
    seen := map[int]bool{}
    result := []int{}
    for _, x := range items {
        if !seen[x] {
            seen[x] = true
            result = append(result, x)
        }
    }
    return result
}''',
        'rust': r'''use std::collections::HashSet;

fn dedup(items: &[i32]) -> Vec<i32> {
    let mut seen = HashSet::new();
    items.iter().copied().filter(|x| seen.insert(*x)).collect()
}''',
    },
    'flatten': {
        'python': r'''def flatten(nested: list) -> list:
    """Flatten arbitrarily nested lists into a single flat list."""
    result = []
    stack = list(reversed(nested))
    while stack:
        item = stack.pop()
        if isinstance(item, list):
            stack.extend(reversed(item))
        else:
            result.append(item)
    return result

# Example:
print(flatten([1, [2, [3, [4]], 5]]))  # [1, 2, 3, 4, 5]
# Shallow (one level only): [x for sub in nested for x in sub]''',
        'javascript': r'''function flatten(nested) {
    const result = [];
    const stack = [...nested].reverse();
    while (stack.length) {
        const item = stack.pop();
        if (Array.isArray(item)) stack.push(...[...item].reverse());
        else result.push(item);
    }
    return result;
}

// Example:
console.log(flatten([1, [2, [3, [4]], 5]]));  // [1, 2, 3, 4, 5]
// One level: [].concat(...nested)   Arbitrary depth: nested.flat(Infinity)''',
        'java': r'''public static List<Object> flatten(List<?> nested) {
    List<Object> result = new ArrayList<>();
    for (Object item : nested) {
        if (item instanceof List<?> list) result.addAll(flatten(list));
        else result.add(item);
    }
    return result;
}''',
        'c++': r'''// C++ has no built-in nested-list type; use a variant or recursion over
// std::vector<std::variant<int, std::vector<...>>>. For the common case of
// flattening a vector of vectors:
std::vector<int> flatten(const std::vector<std::vector<int>>& nested) {
    std::vector<int> result;
    for (const auto& v : nested) {
        result.insert(result.end(), v.begin(), v.end());
    }
    return result;
}''',
        'go': r'''// Flatten a [][]int (one level). For arbitrary nesting use a recursive
// function over []interface{}.
func Flatten(nested [][]int) []int {
    result := []int{}
    for _, v := range nested {
        result = append(result, v...)
    }
    return result
}''',
        'rust': r'''// Flatten a Vec<Vec<T>> (one level). For arbitrary nesting use an enum.
fn flatten(nested: Vec<Vec<i32>>) -> Vec<i32> {
    nested.into_iter().flatten().collect()
}''',
    },
    'sum_list': {
        'python': r'''def sum_and_average(numbers: list[float]) -> tuple[float, float]:
    if not numbers:
        return 0.0, 0.0
    total = sum(numbers)
    return total, total / len(numbers)

# Example:
nums = [10, 20, 30, 40]
total, avg = sum_and_average(nums)
print(f"sum={total}, average={avg}")  # sum=100, average=25.0
# Built-ins: sum(nums), and statistics.mean(nums)''',
        'javascript': r'''function sumAndAverage(numbers) {
    if (numbers.length === 0) return { sum: 0, average: 0 };
    const sum = numbers.reduce((acc, n) => acc + n, 0);
    return { sum, average: sum / numbers.length };
}

// Example:
console.log(sumAndAverage([10, 20, 30, 40]));
// { sum: 100, average: 25 }''',
        'java': r'''public static double[] sumAndAverage(int[] numbers) {
    if (numbers.length == 0) return new double[]{0, 0};
    long sum = 0;
    for (int n : numbers) sum += n;
    return new double[]{sum, (double) sum / numbers.length};
}''',
        'c++': r'''std::pair<long long, double> sumAndAverage(
    const std::vector<int>& numbers) {
    if (numbers.empty()) return {0, 0};
    long long sum = std::accumulate(numbers.begin(), numbers.end(), 0LL);
    return {sum, (double) sum / numbers.size()};
}''',
        'go': r'''func SumAndAverage(numbers []int) (int, float64) {
    if len(numbers) == 0 {
        return 0, 0
    }
    sum := 0
    for _, n := range numbers {
        sum += n
    }
    return sum, float64(sum) / float64(len(numbers))
}''',
        'rust': r'''fn sum_and_average(numbers: &[i32]) -> (i32, f64) {
    if numbers.is_empty() {
        return (0, 0.0);
    }
    let sum: i32 = numbers.iter().sum();
    (sum, sum as f64 / numbers.len() as f64)
}''',
    },
    'two_sum': {
        'python': r'''def two_sum(nums: list[int], target: int) -> list[int]:
    """Return the indices of the two numbers that add up to target."""
    seen = {}  # value -> index
    for i, num in enumerate(nums):
        complement = target - num
        if complement in seen:
            return [seen[complement], i]
        seen[num] = i
    return []  # no solution

# Example:
print(two_sum([2, 7, 11, 15], 9))  # [0, 1]''',
        'javascript': r'''function twoSum(nums, target) {
    const seen = new Map();  // value -> index
    for (let i = 0; i < nums.length; i++) {
        const complement = target - nums[i];
        if (seen.has(complement)) return [seen.get(complement), i];
        seen.set(nums[i], i);
    }
    return [];
}''',
        'java': r'''public static int[] twoSum(int[] nums, int target) {
    Map<Integer, Integer> seen = new HashMap<>();
    for (int i = 0; i < nums.length; i++) {
        int complement = target - nums[i];
        if (seen.containsKey(complement)) {
            return new int[]{seen.get(complement), i};
        }
        seen.put(nums[i], i);
    }
    return new int[]{};
}''',
        'c++': r'''#include <unordered_map>

std::vector<int> twoSum(const std::vector<int>& nums, int target) {
    std::unordered_map<int, int> seen;  // value -> index
    for (int i = 0; i < (int) nums.size(); i++) {
        int complement = target - nums[i];
        if (seen.count(complement)) return {seen[complement], i};
        seen[nums[i]] = i;
    }
    return {};
}''',
        'go': r'''func TwoSum(nums []int, target int) []int {
    seen := map[int]int{}  // value -> index
    for i, num := range nums {
        if j, ok := seen[target-num]; ok {
            return []int{j, i}
        }
        seen[num] = i
    }
    return nil
}''',
        'rust': r'''use std::collections::HashMap;

fn two_sum(nums: &[i32], target: i32) -> Option<(usize, usize)> {
    let mut seen = HashMap::new();
    for (i, &num) in nums.iter().enumerate() {
        if let Some(&j) = seen.get(&(target - num)) {
            return Some((j, i));
        }
        seen.insert(num, i);
    }
    None
}''',
    },
    'linked_list': {
        'python': r'''class ListNode:
    def __init__(self, val=0, next=None):
        self.val = val
        self.next = next


def reverse_list(head: ListNode) -> ListNode:
    """Reverse a singly linked list in place (iterative)."""
    prev, curr = None, head
    while curr:
        nxt = curr.next      # save next before rewiring
        curr.next = prev
        prev, curr = curr, nxt
    return prev              # new head

# Example: 1 -> 2 -> 3 -> None  becomes  3 -> 2 -> 1 -> None
def build_list(values):
    head = None
    for v in reversed(values):
        head = ListNode(v, head)
    return head

head = build_list([1, 2, 3])
reversed_head = reverse_list(head)
# walk it:
while reversed_head:
    print(reversed_head.val, end=" ")
    reversed_head = reversed_head.next
# prints: 3 2 1''',
        'javascript': r'''class ListNode {
    constructor(val, next = null) {
        this.val = val;
        this.next = next;
    }
}

function reverseList(head) {
    let prev = null, curr = head;
    while (curr) {
        const next = curr.next;   // save next before rewiring
        curr.next = prev;
        prev = curr;
        curr = next;
    }
    return prev;   // new head
}''',
        'java': r'''public class ListNode {
    int val;
    ListNode next;
    ListNode(int val) { this.val = val; }
}

public static ListNode reverseList(ListNode head) {
    ListNode prev = null, curr = head;
    while (curr != null) {
        ListNode next = curr.next;  // save next before rewiring
        curr.next = prev;
        prev = curr;
        curr = next;
    }
    return prev;  // new head
}''',
        'c++': r'''struct ListNode {
    int val;
    ListNode* next;
    ListNode(int v) : val(v), next(nullptr) {}
};

ListNode* reverseList(ListNode* head) {
    ListNode* prev = nullptr;
    ListNode* curr = head;
    while (curr) {
        ListNode* next = curr->next;  // save next before rewiring
        curr->next = prev;
        prev = curr;
        curr = next;
    }
    return prev;  // new head
}''',
        'go': r'''type ListNode struct {
    Val  int
    Next *ListNode
}

func ReverseList(head *ListNode) *ListNode {
    var prev *ListNode
    curr := head
    for curr != nil {
        next := curr.Next // save next before rewiring
        curr.Next = prev
        prev = curr
        curr = next
    }
    return prev // new head
}''',
        'rust': r'''#[derive(Debug)]
struct ListNode {
    val: i32,
    next: Option<Box<ListNode>>,
}

fn reverse_list(mut head: Option<Box<ListNode>>) -> Option<Box<ListNode>> {
    let mut prev = None;
    while let Some(mut node) = head.take() {
        let next = node.next.take(); // save next before rewiring
        node.next = prev;
        prev = Some(node);
        head = next;
    }
    prev
}''',
    },
    'bst': {
        'python': r'''class TreeNode:
    def __init__(self, val=0, left=None, right=None):
        self.val = val
        self.left = left
        self.right = right


class BinarySearchTree:
    def __init__(self):
        self.root = None

    def insert(self, val: int) -> None:
        if not self.root:
            self.root = TreeNode(val)
            return
        node = self.root
        while True:
            if val < node.val:
                if node.left is None:
                    node.left = TreeNode(val)
                    return
                node = node.left
            else:
                if node.right is None:
                    node.right = TreeNode(val)
                    return
                node = node.right

    def search(self, val: int) -> bool:
        node = self.root
        while node:
            if node.val == val:
                return True
            node = node.left if val < node.val else node.right
        return False

    def inorder(self) -> list[int]:
        """Sorted order traversal."""
        result = []

        def visit(node):
            if not node:
                return
            visit(node.left)
            result.append(node.val)
            visit(node.right)

        visit(self.root)
        return result

# Example:
bst = BinarySearchTree()
for v in (5, 3, 7, 1, 4, 6, 8):
    bst.insert(v)
print(bst.search(4))     # True
print(bst.search(9))     # False
print(bst.inorder())     # [1, 3, 4, 5, 6, 7, 8]''',
        'javascript': r'''class TreeNode {
    constructor(val) {
        this.val = val;
        this.left = null;
        this.right = null;
    }
}

class BinarySearchTree {
    constructor() {
        this.root = null;
    }

    insert(val) {
        if (!this.root) {
            this.root = new TreeNode(val);
            return;
        }
        let node = this.root;
        while (true) {
            if (val < node.val) {
                if (!node.left) { node.left = new TreeNode(val); return; }
                node = node.left;
            } else {
                if (!node.right) { node.right = new TreeNode(val); return; }
                node = node.right;
            }
        }
    }

    search(val) {
        let node = this.root;
        while (node) {
            if (node.val === val) return true;
            node = val < node.val ? node.left : node.right;
        }
        return false;
    }

    inorder() {
        const result = [];
        const visit = (node) => {
            if (!node) return;
            visit(node.left);
            result.push(node.val);
            visit(node.right);
        };
        visit(this.root);
        return result;
    }
}''',
        'java': r'''class TreeNode {
    int val;
    TreeNode left, right;
    TreeNode(int val) { this.val = val; }
}

class BinarySearchTree {
    TreeNode root;

    void insert(int val) {
        root = insertRec(root, val);
    }

    private TreeNode insertRec(TreeNode node, int val) {
        if (node == null) return new TreeNode(val);
        if (val < node.val) node.left = insertRec(node.left, val);
        else node.right = insertRec(node.right, val);
        return node;
    }

    boolean search(int val) {
        TreeNode node = root;
        while (node != null) {
            if (node.val == val) return true;
            node = val < node.val ? node.left : node.right;
        }
        return false;
    }

    List<Integer> inorder() {
        List<Integer> result = new ArrayList<>();
        inorderRec(root, result);
        return result;
    }

    private void inorderRec(TreeNode node, List<Integer> result) {
        if (node == null) return;
        inorderRec(node.left, result);
        result.add(node.val);
        inorderRec(node.right, result);
    }
}''',
        'c++': r'''struct TreeNode {
    int val;
    TreeNode* left;
    TreeNode* right;
    TreeNode(int v) : val(v), left(nullptr), right(nullptr) {}
};

class BinarySearchTree {
public:
    TreeNode* root = nullptr;

    void insert(int val) { root = insertRec(root, val); }

    bool search(int val) const {
        TreeNode* node = root;
        while (node) {
            if (node->val == val) return true;
            node = val < node->val ? node->left : node->right;
        }
        return false;
    }

    std::vector<int> inorder() const {
        std::vector<int> result;
        inorderRec(root, result);
        return result;
    }

private:
    TreeNode* insertRec(TreeNode* node, int val) {
        if (!node) return new TreeNode(val);
        if (val < node->val) node->left = insertRec(node->left, val);
        else node->right = insertRec(node->right, val);
        return node;
    }

    void inorderRec(TreeNode* node, std::vector<int>& out) const {
        if (!node) return;
        inorderRec(node->left, out);
        out.push_back(node->val);
        inorderRec(node->right, out);
    }
};''',
        'go': r'''type TreeNode struct {
    Val   int
    Left  *TreeNode
    Right *TreeNode
}

type BST struct{ Root *TreeNode }

func (t *BST) Insert(val int) {
    t.Root = insertRec(t.Root, val)
}

func insertRec(node *TreeNode, val int) *TreeNode {
    if node == nil {
        return &TreeNode{Val: val}
    }
    if val < node.Val {
        node.Left = insertRec(node.Left, val)
    } else {
        node.Right = insertRec(node.Right, val)
    }
    return node
}

func (t *BST) Search(val int) bool {
    node := t.Root
    for node != nil {
        if node.Val == val {
            return true
        }
        if val < node.Val {
            node = node.Left
        } else {
            node = node.Right
        }
    }
    return false
}

func (t *BST) Inorder() []int {
    out := []int{}
    var visit func(*TreeNode)
    visit = func(n *TreeNode) {
        if n == nil {
            return
        }
        visit(n.Left)
        out = append(out, n.Val)
        visit(n.Right)
    }
    visit(t.Root)
    return out
}''',
        'rust': r'''#[derive(Debug)]
struct TreeNode {
    val: i32,
    left: Option<Box<TreeNode>>,
    right: Option<Box<TreeNode>>,
}

impl TreeNode {
    fn new(val: i32) -> Self {
        TreeNode { val, left: None, right: None }
    }
}

struct BST {
    root: Option<Box<TreeNode>>,
}

impl BST {
    fn new() -> Self {
        BST { root: None }
    }

    fn insert(&mut self, val: i32) {
        self.root = Self::insert_rec(self.root.take(), val);
    }

    fn insert_rec(node: Option<Box<TreeNode>>, val: i32) -> Option<Box<TreeNode>> {
        match node {
            None => Some(Box::new(TreeNode::new(val))),
            Some(mut n) => {
                if val < n.val {
                    n.left = Self::insert_rec(n.left.take(), val);
                } else {
                    n.right = Self::insert_rec(n.right.take(), val);
                }
                Some(n)
            }
        }
    }

    fn search(&self, val: i32) -> bool {
        let mut node = self.root.as_ref();
        while let Some(n) = node {
            if n.val == val {
                return true;
            }
            node = if val < n.val { n.left.as_ref() } else { n.right.as_ref() };
        }
        false
    }
}''',
    },
    'graph_traversal': {
        'python': r'''from collections import deque

# Adjacency list: {node: [neighbors]}
graph = {
    'A': ['B', 'C'],
    'B': ['A', 'D', 'E'],
    'C': ['A', 'F'],
    'D': ['B'],
    'E': ['B', 'F'],
    'F': ['C', 'E'],
}


def bfs(start: str) -> list[str]:
    """Breadth-first search — shortest path in unweighted graphs."""
    visited, queue = {start}, deque([start])
    order = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for nbr in graph.get(node, []):
            if nbr not in visited:
                visited.add(nbr)
                queue.append(nbr)
    return order


def dfs(start: str) -> list[str]:
    """Depth-first search — connectivity and cycle detection."""
    visited, stack = set(), [start]
    order = []
    while stack:
        node = stack.pop()
        if node in visited:
            continue
        visited.add(node)
        order.append(node)
        for nbr in reversed(graph.get(node, [])):
            if nbr not in visited:
                stack.append(nbr)
    return order

print(bfs('A'))  # ['A', 'B', 'C', 'D', 'E', 'F']
print(dfs('A'))  # ['A', 'B', 'D', 'E', 'F', 'C']''',
        'javascript': r'''// Adjacency list: { node: [neighbors] }
const graph = {
    A: ['B', 'C'],
    B: ['A', 'D', 'E'],
    C: ['A', 'F'],
    D: ['B'],
    E: ['B', 'F'],
    F: ['C', 'E'],
};

function bfs(start) {
    const visited = new Set([start]);
    const queue = [start];
    const order = [];
    while (queue.length) {
        const node = queue.shift();
        order.push(node);
        for (const nbr of graph[node] || []) {
            if (!visited.has(nbr)) {
                visited.add(nbr);
                queue.push(nbr);
            }
        }
    }
    return order;
}

function dfs(start) {
    const visited = new Set();
    const stack = [start];
    const order = [];
    while (stack.length) {
        const node = stack.pop();
        if (visited.has(node)) continue;
        visited.add(node);
        order.push(node);
        for (const nbr of [...(graph[node] || [])].reverse()) {
            if (!visited.has(nbr)) stack.push(nbr);
        }
    }
    return order;
}

console.log(bfs('A'));  // ['A', 'B', 'C', 'D', 'E', 'F']
console.log(dfs('A'));  // ['A', 'B', 'D', 'E', 'F', 'C']''',
    },
    # ─────────────────────────── regex ────────────────────────────────
    'regex_email': {
        'python': r'''import re

EMAIL_RE = re.compile(r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')

def is_valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email))

# Examples:
print(is_valid_email('user@example.com'))   # True
print(is_valid_email('user.name+tag@gmail.com'))  # True
print(is_valid_email('not-an-email'))       # False
print(is_valid_email('a@b'))                # False (no TLD)''',
        'javascript': r'''function isValidEmail(email) {
    return /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/.test(email);
}

// Examples:
console.log(isValidEmail('user@example.com'));        // true
console.log(isValidEmail('user.name+tag@gmail.com')); // true
console.log(isValidEmail('not-an-email'));            // false''',
        'java': r'''private static final Pattern EMAIL_RE =
    Pattern.compile("^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$");

public static boolean isValidEmail(String email) {
    return EMAIL_RE.matcher(email).matches();
}''',
        'c++': r'''#include <regex>

bool isValidEmail(const std::string& email) {
    static const std::regex re(
        R"(^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$)");
    return std::regex_match(email, re);
}''',
        'go': r'''import "regexp"

var emailRe = regexp.MustCompile(`^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$`)

func IsValidEmail(email string) bool {
    return emailRe.MatchString(email)
}''',
        'rust': r'''use regex::Regex;

fn is_valid_email(email: &str) -> bool {
    let re = Regex::new(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$").unwrap();
    re.is_match(email)
}''',
    },
    'regex_phone': {
        'python': r'''import re

# US-style phone numbers: (555) 123-4567, 555-123-4567, +1 555 123 4567
PHONE_RE = re.compile(
    r'^\+?1?\s*(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}$'
)

def is_valid_phone(phone: str) -> bool:
    return bool(PHONE_RE.match(phone.strip()))

# Examples:
for p in ('(555) 123-4567', '555-123-4567', '+1 555 123 4567', '12345'):
    print(p, '->', is_valid_phone(p))''',
        'javascript': r'''function isValidPhone(phone) {
    // US-style: (555) 123-4567, 555-123-4567, +1 555 123 4567
    return /^\+?1?\s*(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}$/.test(phone.trim());
}

// Examples:
['(555) 123-4567', '555-123-4567', '+1 555 123 4567', '12345']
    .forEach(p => console.log(p, '->', isValidPhone(p)));''',
        'java': r'''private static final Pattern PHONE_RE = Pattern.compile(
    "^\\+?1?\\s*(?:\\(\\d{3}\\)|\\d{3})[\\s.-]?\\d{3}[\\s.-]?\\d{4}$");

public static boolean isValidPhone(String phone) {
    return PHONE_RE.matcher(phone.trim()).matches();
}''',
        'c++': r'''#include <regex>

bool isValidPhone(const std::string& phone) {
    static const std::regex re(
        R"(^\+?1?\s*(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}$)");
    return std::regex_match(phone, re);
}''',
        'go': r'''import "regexp"

var phoneRe = regexp.MustCompile(`^\+?1?\s*(?:\(\d{3}\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}$`)

func IsValidPhone(phone string) bool {
    return phoneRe.MatchString(phone)
}''',
    },
    'regex_password': {
        'python': r'''import re

def password_strength(pw: str) -> dict:
    checks = {
        'length >= 8': len(pw) >= 8,
        'uppercase': bool(re.search(r'[A-Z]', pw)),
        'lowercase': bool(re.search(r'[a-z]', pw)),
        'digit': bool(re.search(r'\d', pw)),
        'special': bool(re.search(r'[^A-Za-z0-9]', pw)),
    }
    return checks

def is_strong_password(pw: str) -> bool:
    return all(password_strength(pw).values())

# Example:
pw = 'Tr0ub4dor&3'
print(is_strong_password(pw))   # True
print(password_strength(pw))''',
        'javascript': r'''function passwordStrength(pw) {
    return {
        'length >= 8': pw.length >= 8,
        uppercase: /[A-Z]/.test(pw),
        lowercase: /[a-z]/.test(pw),
        digit: /\d/.test(pw),
        special: /[^A-Za-z0-9]/.test(pw),
    };
}

function isStrongPassword(pw) {
    return Object.values(passwordStrength(pw)).every(Boolean);
}

// Example:
console.log(isStrongPassword('Tr0ub4dor&3'));  // true''',
        'java': r'''public static boolean isStrongPassword(String pw) {
    return pw.length() >= 8
        && pw.matches(".*[A-Z].*")
        && pw.matches(".*[a-z].*")
        && pw.matches(".*\\d.*")
        && pw.matches(".*[^A-Za-z0-9].*");
}''',
        'c++': r'''#include <regex>

bool isStrongPassword(const std::string& pw) {
    return pw.size() >= 8
        && std::regex_search(pw, std::regex(R"([A-Z])"))
        && std::regex_search(pw, std::regex(R"([a-z])"))
        && std::regex_search(pw, std::regex(R"(\d)"))
        && std::regex_search(pw, std::regex(R"([^A-Za-z0-9])"));
}''',
        'go': r'''import "regexp"

func IsStrongPassword(pw string) bool {
    upper := regexp.MustCompile(`[A-Z]`).MatchString(pw)
    lower := regexp.MustCompile(`[a-z]`).MatchString(pw)
    digit := regexp.MustCompile(`\d`).MatchString(pw)
    special := regexp.MustCompile(`[^A-Za-z0-9]`).MatchString(pw)
    return len(pw) >= 8 && upper && lower && digit && special
}''',
    },
    'regex_url': {
        'python': r'''import re

URL_RE = re.compile(
    r'^(?:https?|ftp)://'
    r'[A-Za-z0-9.-]+'                 # host
    r'(?::\d+)?'                      # optional port
    r'(?:/[^\s]*)?$'                  # optional path
)

def is_valid_url(url: str) -> bool:
    return bool(URL_RE.match(url))

# Examples:
print(is_valid_url('https://example.com/path?q=1'))  # True
print(is_valid_url('example.com'))                    # False (no scheme)''',
        'javascript': r'''function isValidUrl(url) {
    try {
        const u = new URL(url);
        return u.protocol === 'http:' || u.protocol === 'https:';
    } catch {
        return false;
    }
}

// Examples:
console.log(isValidUrl('https://example.com/path?q=1'));  // true
console.log(isValidUrl('example.com'));                   // false''',
        'java': r'''public static boolean isValidUrl(String url) {
    try {
        java.net.URI uri = new java.net.URI(url);
        String scheme = uri.getScheme();
        return "http".equals(scheme) || "https".equals(scheme);
    } catch (Exception e) {
        return false;
    }
}''',
        'go': r'''import "net/url"

func IsValidUrl(raw string) bool {
    u, err := url.Parse(raw)
    return err == nil && (u.Scheme == "http" || u.Scheme == "https")
}''',
        'rust': r'''fn is_valid_url(raw: &str) -> bool {
    match url::Url::parse(raw) {
        Ok(u) => matches!(u.scheme(), "http" | "https"),
        Err(_) => false,
    }
}''',
    },
    'extract_emails': {
        'python': r'''import re

EMAIL_RE = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')

def extract_emails(text: str) -> list[str]:
    return EMAIL_RE.findall(text)

# Example:
text = "Contact alice@example.com or bob.smith+news@company.co.uk for help."
print(extract_emails(text))
# ['alice@example.com', 'bob.smith+news@company.co.uk']''',
        'javascript': r'''function extractEmails(text) {
    const re = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g;
    return text.match(re) || [];
}

// Example:
const text = "Contact alice@example.com or bob.smith+news@company.co.uk for help.";
console.log(extractEmails(text));''',
        'java': r'''private static final Pattern EMAIL_RE =
    Pattern.compile("[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}");

public static List<String> extractEmails(String text) {
    List<String> out = new ArrayList<>();
    Matcher m = EMAIL_RE.matcher(text);
    while (m.find()) out.add(m.group());
    return out;
}''',
        'go': r'''import "regexp"

var emailRe = regexp.MustCompile(`[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}`)

func ExtractEmails(text string) []string {
    return emailRe.FindAllString(text, -1)
}''',
    },
    # ─────────────────────────── IO / data ────────────────────────────
    'read_csv': {
        'python': r'''import csv

def read_csv(filename: str) -> list[dict]:
    """Read a CSV file into a list of row dictionaries."""
    with open(filename, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))

# Example:
rows = read_csv('data.csv')
for row in rows[:3]:
    print(row)

# Using pandas (for analysis/filtering/grouping):
# import pandas as pd
# df = pd.read_csv('data.csv')
# print(df.head())
# print(df.groupby('category')['amount'].sum())''',
        'javascript': r'''const fs = require('fs');

function readCsv(filename) {
    const text = fs.readFileSync(filename, 'utf8');
    const lines = text.trim().split('\\n');
    const headers = lines[0].split(',');
    return lines.slice(1).map(line => {
        const values = line.split(',');
        return Object.fromEntries(headers.map((h, i) => [h, values[i]]));
    });
}

// Note: this simple splitter breaks on quoted fields with embedded commas.
// For robust parsing use a library like csv-parse. Browser version with
// <input type="file">: use PapaParse.''',
        'go': r'''import (
    "encoding/csv"
    "os"
)

func ReadCsv(filename string) ([][]string, error) {
    f, err := os.Open(filename)
    if err != nil {
        return nil, err
    }
    defer f.Close()
    r := csv.NewReader(f)
    r.FieldsPerRecord = -1 // allow ragged rows
    return r.ReadAll()
}''',
    },
    'write_csv': {
        'python': r'''import csv

def write_csv(filename: str, headers: list[str], rows: list[list]) -> None:
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

# Example:
write_csv('out.csv', ['name', 'age'], [['Alice', 30], ['Bob', 25]])''',
        'javascript': r'''const fs = require('fs');

function writeCsv(filename, headers, rows) {
    const lines = [headers.join(','), ...rows.map(r => r.join(','))];
    fs.writeFileSync(filename, lines.join('\\n') + '\\n');
}

// Note: join(',') breaks on fields containing commas/quotes/newlines.
// Use a library like csv-stringify for robust escaping.''',
        'go': r'''import (
    "encoding/csv"
    "os"
)

func WriteCsv(filename string, headers []string, rows [][]string) error {
    f, err := os.Create(filename)
    if err != nil {
        return err
    }
    defer f.Close()
    w := csv.NewWriter(f)
    if err := w.Write(headers); err != nil {
        return err
    }
    if err := w.WriteAll(rows); err != nil {
        return err
    }
    w.Flush()
    return w.Error()
}''',
    },
    'read_file': {
        'python': r'''# Read the whole file:
with open('file.txt', encoding='utf-8') as f:
    content = f.read()

# Read line by line (memory-friendly for large files):
with open('file.txt', encoding='utf-8') as f:
    for line in f:
        print(line.rstrip())  # rstrip removes the trailing newline

# Read into a list of lines:
with open('file.txt', encoding='utf-8') as f:
    lines = f.readlines()''',
        'javascript': r'''const fs = require('fs');

// Synchronous (fine for scripts):
const content = fs.readFileSync('file.txt', 'utf8');
const lines = content.split('\\n');

// Asynchronous (preferred in servers):
fs.readFile('file.txt', 'utf8', (err, data) => {
    if (err) throw err;
    console.log(data);
});

// Promise-based:
const data = await fs.promises.readFile('file.txt', 'utf8');''',
        'go': r'''import (
    "bufio"
    "os"
)

// Whole file:
data, err := os.ReadFile("file.txt")
if err != nil {
    log.Fatal(err)
}

// Line by line:
f, err := os.Open("file.txt")
if err != nil {
    log.Fatal(err)
}
defer f.Close()
scanner := bufio.NewScanner(f)
for scanner.Scan() {
    fmt.Println(scanner.Text())
}
if err := scanner.Err(); err != nil {
    log.Fatal(err)
}''',
        'rust': r'''use std::fs;

fn main() -> std::io::Result<()> {
    // Whole file:
    let content = fs::read_to_string("file.txt")?;
    println!("{content}");

    // Line by line:
    for line in content.lines() {
        println!("{line}");
    }
    Ok(())
}''',
    },
    'write_file': {
        'python': r'''# Overwrite (creates the file if it doesn't exist):
with open('out.txt', 'w', encoding='utf-8') as f:
    f.write('Hello, world!\\n')

# Append:
with open('out.txt', 'a', encoding='utf-8') as f:
    f.write('More lines\\n')

# Write multiple lines:
with open('out.txt', 'w', encoding='utf-8') as f:
    f.writelines(['line 1\\n', 'line 2\\n'])''',
        'javascript': r'''const fs = require('fs');

// Overwrite:
fs.writeFileSync('out.txt', 'Hello, world!\\n');

// Append:
fs.appendFileSync('out.txt', 'More lines\\n');

// Asynchronous:
await fs.promises.writeFile('out.txt', 'Hello, world!\\n');''',
        'go': r'''import "os"

// Overwrite:
err := os.WriteFile("out.txt", []byte("Hello, world!\\n"), 0644)
if err != nil {
    log.Fatal(err)
}

// Append:
f, err := os.OpenFile("out.txt", os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
if err != nil {
    log.Fatal(err)
}
defer f.Close()
if _, err := f.WriteString("More lines\\n"); err != nil {
    log.Fatal(err)
}''',
        'rust': r'''use std::fs::OpenOptions;
use std::io::Write;

fn main() -> std::io::Result<()> {
    // Overwrite:
    fs::write("out.txt", "Hello, world!\\n")?;

    // Append:
    let mut f = OpenOptions::new().append(true).open("out.txt")?;
    writeln!(f, "More lines")?;
    Ok(())
}''',
    },
    'read_json': {
        'python': r'''import json

def read_json(filename: str):
    with open(filename, encoding='utf-8') as f:
        return json.load(f)

# Example:
data = read_json('config.json')
print(data.get('name'))

# Parse a JSON string:
obj = json.loads('{"key": "value"}')
print(obj['key'])  # value''',
        'javascript': r'''const fs = require('fs');

// Node.js — read a JSON file:
const data = JSON.parse(fs.readFileSync('config.json', 'utf8'));
console.log(data.name);

// Browser — fetch + parse:
const obj = await fetch('/config.json').then(r => r.json());

// Parse a JSON string:
const parsed = JSON.parse('{"key": "value"}');''',
        'go': r'''import (
    "encoding/json"
    "os"
)

type Config struct {
    Name string `json:"name"`
}

func ReadJson(filename string) (*Config, error) {
    data, err := os.ReadFile(filename)
    if err != nil {
        return nil, err
    }
    var cfg Config
    if err := json.Unmarshal(data, &cfg); err != nil {
        return nil, err
    }
    return &cfg, nil
}''',
        'rust': r'''use serde::{Deserialize, Serialize};

#[derive(Deserialize)]
struct Config {
    name: String,
}

fn main() -> std::io::Result<()> {
    let data = std::fs::read_to_string("config.json")?;
    let cfg: Config = serde_json::from_str(&data)?;
    println!("{}", cfg.name);
    Ok(())
}
// Add to Cargo.toml: serde = { version = "1", features = ["derive"] }, serde_json = "1"''',
    },
    'write_json': {
        'python': r'''import json

data = {'name': 'Alice', 'age': 30, 'tags': ['admin', 'user']}

# Pretty-printed to a file (human-readable):
with open('out.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

# To a string:
text = json.dumps(data, indent=2)''',
        'javascript': r'''const fs = require('fs');

const data = { name: 'Alice', age: 30, tags: ['admin', 'user'] };

// Node.js:
fs.writeFileSync('out.json', JSON.stringify(data, null, 2) + '\\n');

// Browser — send JSON to a server:
await fetch('/api/users', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
});''',
        'go': r'''import (
    "encoding/json"
    "os"
)

type User struct {
    Name string   `json:"name"`
    Age  int      `json:"age"`
    Tags []string `json:"tags"`
}

func WriteJson(filename string, u User) error {
    data, err := json.MarshalIndent(u, "", "  ")
    if err != nil {
        return err
    }
    return os.WriteFile(filename, data, 0644)
}''',
    },
    'http_get': {
        'python': r'''import urllib.request
import json

def http_get(url: str, timeout: int = 10) -> dict:
    req = urllib.request.Request(url, headers={'User-Agent': 'cos/1.0'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())

# Example (JSONPlaceholder):
data = http_get('https://jsonplaceholder.typicode.com/users/1')
print(data['name'])

# With the `requests` library (nicer API):
# import requests
# resp = requests.get(url, timeout=10)
# resp.raise_for_status()
# data = resp.json()''',
        'javascript': r'''// Browser (and Node.js 18+): fetch API
async function httpGet(url) {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return resp.json();
}

// Node.js with axios:
// const axios = require('axios');
// const { data } = await axios.get(url);
// console.log(data);

// Node.js with the built-in https module (no dependencies):
// const https = require('https');
// https.get(url, (res) => {
//   let body = '';
//   res.on('data', (c) => (body += c));
//   res.on('end', () => console.log(JSON.parse(body)));
// });''',
        'go': r'''import (
    "encoding/json"
    "io"
    "net/http"
)

func HttpGet(url string, target any) error {
    resp, err := http.Get(url)
    if err != nil {
        return err
    }
    defer resp.Body.Close()
    body, err := io.ReadAll(resp.Body)
    if err != nil {
        return err
    }
    return json.Unmarshal(body, target)
}

// Example:
// var user struct{ Name string `json:"name"` }
// if err := HttpGet("https://jsonplaceholder.typicode.com/users/1", &user); err != nil {
//     log.Fatal(err)
// }
// fmt.Println(user.Name)''',
        'rust': r'''// Using reqwest (add to Cargo.toml: reqwest = { version = "0.12", features = ["json"] })
#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let resp = reqwest::get("https://jsonplaceholder.typicode.com/users/1")
        .await?
        .json::<serde_json::Value>()
        .await?;
    println!("{}", resp["name"]);
    Ok(())
}''',
        'bash': r'''# curl
curl -s https://jsonplaceholder.typicode.com/users/1

# curl + jq to extract a field:
curl -s https://jsonplaceholder.typicode.com/users/1 | jq ".name"''',
    },
    'http_post': {
        'python': r'''import urllib.request
import json

def http_post(url: str, payload: dict, timeout: int = 10) -> dict:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={'Content-Type': 'application/json', 'User-Agent': 'cos/1.0'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())

# Example:
print(http_post('https://jsonplaceholder.typicode.com/posts',
                {'title': 'hi', 'body': 'there', 'userId': 1}))

# With `requests`:
# import requests
# resp = requests.post(url, json=payload, timeout=10)
# resp.raise_for_status()
# print(resp.json())''',
        'javascript': r'''// Browser and Node.js 18+: fetch API
async function httpPost(url, payload) {
    const resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return resp.json();
}

// axios:
// const { data } = await axios.post(url, payload);''',
        'go': r'''import (
    "bytes"
    "encoding/json"
    "io"
    "net/http"
)

func HttpPost(url string, payload any, target any) error {
    body, err := json.Marshal(payload)
    if err != nil {
        return err
    }
    resp, err := http.Post(url, "application/json", bytes.NewReader(body))
    if err != nil {
        return err
    }
    defer resp.Body.Close()
    data, err := io.ReadAll(resp.Body)
    if err != nil {
        return err
    }
    return json.Unmarshal(data, target)
}''',
        'bash': r'''# curl POST with a JSON body:
curl -s -X POST https://jsonplaceholder.typicode.com/posts \
  -H 'Content-Type: application/json' \
  -d "{\"title\": \"hi\", \"body\": \"there\", \"userId\": 1}"'''
    },
    'web_scrape': {
        'python': r'''import re
import urllib.request

def fetch_page(url: str) -> str:
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode('utf-8', errors='replace')

def extract_links(html: str) -> list[str]:
    return re.findall(r'href=["\']([^"\']+)["\']', html)

def extract_titles(html: str) -> list[str]:
    # <h1>..</h1> .. <h3>..</h3>
    return re.findall(r'<h[1-3][^>]*>(.*?)</h[1-3]>', html, re.S)

# Example:
html = fetch_page('https://example.com')
print(extract_titles(html)[:5])
print(extract_links(html)[:5])

# For serious scraping use requests + BeautifulSoup:
# from bs4 import BeautifulSoup
# soup = BeautifulSoup(html, 'html.parser')
# print(soup.title.text)''',
    },
    'fetch_table': {
        'python': r'''import urllib.request
import json
import html

def fetch_data(url: str) -> list[dict]:
    req = urllib.request.Request(url, headers={'User-Agent': 'cos/1.0'})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())

def render_table(rows: list[dict]) -> str:
    if not rows:
        return "<p>No data.</p>"
    headers = list(rows[0].keys())
    out = ["<table border='1'>", "<thead><tr>"]
    out += [f"<th>{html.escape(str(h))}</th>" for h in headers]
    out.append("</tr></thead><tbody>")
    for row in rows:
        out.append("<tr>")
        out += [f"<td>{html.escape(str(row.get(h, '')))}</td>" for h in headers]
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)

# Example: fetch users and render an HTML table
users = fetch_data('https://jsonplaceholder.typicode.com/users')
print(render_table(users[:5]))''',
        'javascript': r'''async function fetchAndRenderTable(url, containerId) {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const rows = await resp.json();

    const container = document.getElementById(containerId);
    const table = document.createElement('table');
    const thead = document.createElement('thead');

    const headers = Object.keys(rows[0] || {});
    const tr = document.createElement('tr');
    headers.forEach(h => {
        const th = document.createElement('th');
        th.textContent = h;   // textContent, not innerHTML — avoids XSS
        tr.appendChild(th);
    });
    thead.appendChild(tr);
    table.appendChild(thead);

    const tbody = document.createElement('tbody');
    rows.forEach(row => {
        const tr = document.createElement('tr');
        headers.forEach(h => {
            const td = document.createElement('td');
            td.textContent = row[h] ?? '';
            tr.appendChild(td);
        });
        tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    container.appendChild(table);
}

// Example:
// await fetchAndRenderTable('https://jsonplaceholder.typicode.com/users', 'app');''',
    },
    'express_api': {
        'javascript': r'''const express = require('express');

const app = express();
app.use(express.json());   // parse JSON request bodies

const items = [
    { id: 1, name: 'first' },
    { id: 2, name: 'second' },
];

// GET /api/items — list
app.get('/api/items', (req, res) => {
    res.json(items);
});

// GET /api/items/:id — one item
app.get('/api/items/:id', (req, res) => {
    const item = items.find(i => i.id === Number(req.params.id));
    if (!item) return res.status(404).json({ error: 'Not found' });
    res.json(item);
});

// POST /api/items — create
app.post('/api/items', (req, res) => {
    const item = { id: items.length + 1, name: req.body.name };
    items.push(item);
    res.status(201).json(item);
});

// DELETE /api/items/:id
app.delete('/api/items/:id', (req, res) => {
    const idx = items.findIndex(i => i.id === Number(req.params.id));
    if (idx === -1) return res.status(404).json({ error: 'Not found' });
    items.splice(idx, 1);
    res.status(204).end();
});

app.listen(3000, () => console.log('API listening on http://localhost:3000'));''',
    },
    'flask_api': {
        'python': r'''from flask import Flask, jsonify, request

app = Flask(__name__)

items = [
    {'id': 1, 'name': 'first'},
    {'id': 2, 'name': 'second'},
]


@app.get('/api/items')
def list_items():
    return jsonify(items)


@app.get('/api/items/<int:item_id>')
def get_item(item_id):
    item = next((i for i in items if i['id'] == item_id), None)
    if item is None:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(item)


@app.post('/api/items')
def create_item():
    data = request.get_json()
    if not data or 'name' not in data:
        return jsonify({'error': 'name is required'}), 400
    item = {'id': len(items) + 1, 'name': data['name']}
    items.append(item)
    return jsonify(item), 201


if __name__ == '__main__':
    app.run(debug=True)  # dev only — use gunicorn in production''',
    },
    # ─────────────────────────── SQL ───────────────────────────────────
    'sql_select': {
        'sql': r'''-- All columns (quick exploration only):
SELECT * FROM customers;

-- Specific columns, filtered and ordered:
SELECT id, name, email
FROM customers
WHERE country = 'US'
ORDER BY name ASC
LIMIT 100;''',
    },
    'sql_insert': {
        'sql': r'''-- Insert one row (parameterized — never concatenate user input):
INSERT INTO customers (name, email, country)
VALUES (?, ?, ?);

-- Insert multiple rows:
INSERT INTO customers (name, email, country)
VALUES
    ('Alice', 'alice@example.com', 'US'),
    ('Bob',   'bob@example.com',   'UK');

-- MySQL / SQLite placeholder style is ?; PostgreSQL uses $1, $2, $3.''',
    },
    'sql_update': {
        'sql': r'''-- Always scope with WHERE!
UPDATE customers
SET email = 'new@example.com'
WHERE id = 42;

-- Update multiple columns:
UPDATE products
SET price = price * 1.1, updated_at = CURRENT_TIMESTAMP
WHERE category = 'books';''',
    },
    'sql_delete': {
        'sql': r'''-- Always scope with WHERE — a bare DELETE empties the table!
DELETE FROM customers
WHERE id = 42
  AND email = 'old@example.com';   -- double-check with SELECT first

-- Delete all rows but keep the table:
DELETE FROM customers;''',
    },
    'sql_join': {
        'sql': r'''-- Orders with their customer names:
SELECT o.id AS order_id, c.name AS customer, o.total
FROM orders o
INNER JOIN customers c ON o.customer_id = c.id
ORDER BY o.id;

-- LEFT JOIN keeps orders even when the customer was deleted:
SELECT o.id, c.name
FROM orders o
LEFT JOIN customers c ON o.customer_id = c.id;''',
    },
    'sql_group_by': {
        'sql': r'''-- Count per group:
SELECT country, COUNT(*) AS customer_count
FROM customers
GROUP BY country
ORDER BY customer_count DESC;

-- Sum / average per group:
SELECT category, SUM(amount) AS total, AVG(amount) AS avg_amount
FROM sales
GROUP BY category;

-- Groups with a minimum size (HAVING filters after grouping):
SELECT category, COUNT(*) AS n
FROM sales
GROUP BY category
HAVING n >= 10;''',
    },
    'sql_duplicates': {
        'sql': r'''-- Rows sharing the same key column(s) — the usual definition:
SELECT email, COUNT(*) AS n
FROM customers
GROUP BY email
HAVING COUNT(*) > 1;

-- Full-row duplicates (every column identical):
SELECT *
FROM customers
GROUP BY id, name, email, country   -- all columns
HAVING COUNT(*) > 1;

-- See the actual duplicate rows:
SELECT c.*
FROM customers c
JOIN (
    SELECT email
    FROM customers
    GROUP BY email
    HAVING COUNT(*) > 1
) d ON c.email = d.email
ORDER BY c.email;''',
    },
    'sql_create_table': {
        'sql': r'''CREATE TABLE customers (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,  -- MySQL: INT AUTO_INCREMENT
    name       TEXT    NOT NULL,                   -- MySQL: VARCHAR(255)
    email      TEXT    UNIQUE NOT NULL,
    country    TEXT    DEFAULT 'US',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);''',
    },
    'sql_aggregate': {
        'sql': r'''SELECT
    COUNT(*)                 AS total_rows,
    COUNT(email)             AS emails_not_null,   -- ignores NULLs
    COUNT(DISTINCT country)  AS distinct_countries,
    SUM(amount)              AS total,
    AVG(amount)              AS average,
    MIN(amount)              AS min_amount,
    MAX(amount)              AS max_amount
FROM sales;''',
    },
    # ─────────────────────────── git / bash ────────────────────────────
    'git_undo': {
        'bash': r'''# ── Not pushed yet — safe to rewrite history ──────────────────
# Undo the last commit but KEEP the changes staged:
git reset --soft HEAD~1

# Undo the last commit and keep changes in the working tree (unstaged):
git reset --mixed HEAD~1      # this is the default for `git reset HEAD~1`

# Undo the last commit and DISCARD the changes entirely:
git reset --hard HEAD~1       # ⚠️ destructive — unrecoverable without reflog

# ── Already pushed — never rewrite shared history ──────────────────
# Add a new commit that reverses the last commit (safe to push):
git revert HEAD

# Revert a specific commit by hash:
git revert <commit-hash>

# ── Fix just the message of the last commit ─────────────────────────
git commit --amend -m "new message"

# ── Oops, forgot a file in the last commit ─────────────────────────
git add forgotten-file.txt
git commit --amend --no-edit

# Anything lost? Check the reflog — it records every HEAD move for ~90 days:
git reflog''',
    },
    'git_commit': {
        'bash': r'''# See what changed before committing:
git status
git diff

# Stage specific files (or `git add .` for everything):
git add src/main.py tests/test_main.py

# Commit with a message (imperative mood, under 50 chars is a good habit):
git commit -m "Fix null pointer in user lookup"

# Verify:
git log --oneline -5''',
    },
    'git_branch': {
        'bash': r'''# Create a new branch and switch to it:
git checkout -b feature/login
# or: git switch -c feature/login

# List branches (* marks the current one):
git branch

# Switch branches:
git checkout main
# or: git switch main

# Merge a branch into the current branch:
git checkout main
git merge feature/login

# Delete a merged branch:
git branch -d feature/login

# Push the new branch to the remote:
git push -u origin feature/login''',
    },
    'git_stash': {
        'bash': r'''# Save uncommitted changes and clean the working tree:
git stash            # `git stash push -m "wip"` to label it

# See stashes:
git stash list

# Restore the latest stash and remove it:
git stash pop

# Restore without removing (keeps it for later):
git stash apply

# Drop a specific stash:
git stash drop stash@{0}

# Stash including untracked files:
git stash -u''',
    },
    'git_log': {
        'bash': r'''# Compact history (one line per commit):
git log --oneline

# With branch topology:
git log --oneline --graph --all

# Last 10 commits with diffs:
git log -p -10

# Commits by a specific author:
git log --author="alice"

# Commits touching a file:
git log --oneline -- src/main.py

# Search commit messages for a phrase:
git log --grep="fix" --oneline''',
    },
    'bash_file_ops': {
        'bash': r'''# List files (ls) / search (find):
ls -la
find . -name "*.py" -type f

# Search inside file contents:
grep -r "TODO" src/
grep -n "def main" main.py

# Copy / move / delete:
cp file.txt backup.txt
mv old.txt new.txt
rm file.txt            # ⚠️ no trash can — deletes permanently
rm -r directory/

# Permissions (octal: r=4, w=2, x=1):
chmod 755 script.sh     # rwxr-xr-x
chmod +x script.sh      # make executable
chown user:group file.txt

# Show file contents:
cat file.txt
less file.txt           # scrollable''',
    },
    'bash_curl': {
        'bash': r'''# GET (silent, show response body):
curl -s https://api.example.com/users

# GET with a query parameter:
curl -s "https://api.example.com/users?page=2"

# Show response headers too:
curl -si https://api.example.com/users

# POST JSON:
curl -s -X POST https://api.example.com/users \
  -H 'Content-Type: application/json' \
  -d "{\"name\": \"Alice\"}"

# Download to a file:
curl -s -o page.html https://example.com/

# Follow redirects:
curl -sL https://example.com

# Pretty-print JSON with jq:
curl -s https://api.example.com/users | jq .''',
    },
    # ──────────────────────── data munging ───────────────────────────────
    'chunk_list': {
        'python': r'''def chunk(lst: list, size: int) -> list[list]:
    """Split a list into consecutive chunks of the given size."""
    if size <= 0:
        raise ValueError('chunk size must be positive')
    return [lst[i:i + size] for i in range(0, len(lst), size)]

# Example:
print(chunk([1, 2, 3, 4, 5, 6, 7], 3))  # [[1, 2, 3], [4, 5, 6], [7]]''',
        'javascript': r'''function chunk(arr, size) {
  if (size <= 0) throw new Error('chunk size must be positive');
  const out = [];
  for (let i = 0; i < arr.length; i += size) {
    out.push(arr.slice(i, i + size));
  }
  return out;
}

// Example:
console.log(chunk([1, 2, 3, 4, 5, 6, 7], 3));  // [[1, 2, 3], [4, 5, 6], [7]]''',
        'go': r'''// Chunk splits a slice into consecutive slices of the given size.
func Chunk[T any](items []T, size int) [][]T {
	if size <= 0 {
		panic("chunk size must be positive")
	}
	var out [][]T
	for i := 0; i < len(items); i += size {
		end := i + size
		if end > len(items) {
			end = len(items)
		}
		out = append(out, items[i:end])
	}
	return out
}

// Example:
// fmt.Println(Chunk([]int{1, 2, 3, 4, 5, 6, 7}, 3)) // [[1 2 3] [4 5 6] [7]]''',
        'rust': r'''// Chunk splits a slice into consecutive slices of the given size.
fn chunk<T: Clone>(items: Vec<T>, size: usize) -> Vec<Vec<T>> {
    items.chunks(size).map(|c| c.to_vec()).collect()
}

// Example:
// println!("{:?}", chunk(vec![1, 2, 3, 4, 5, 6, 7], 3)); // [[1, 2, 3], [4, 5, 6], [7]]''',
    },
    'transpose_matrix': {
        'python': r'''def transpose(matrix: list[list]) -> list[list]:
    """Transpose an m x n matrix (rows become columns)."""
    if not matrix:
        return []
    return [list(col) for col in zip(*matrix)]

# Example:
print(transpose([[1, 2, 3], [4, 5, 6]]))
# [[1, 4], [2, 5], [3, 6]]''',
        'javascript': r'''function transpose(matrix) {
  if (matrix.length === 0) return [];
  return matrix[0].map((_, col) => matrix.map(row => row[col]));
}

// Example:
console.log(transpose([[1, 2, 3], [4, 5, 6]]));
// [[1, 4], [2, 5], [3, 6]]''',
        'go': r'''// Transpose turns an m x n matrix into n x m (rows become columns).
func Transpose[T any](m [][]T) [][]T {
	if len(m) == 0 {
		return nil
	}
	rows, cols := len(m), len(m[0])
	out := make([][]T, cols)
	for c := 0; c < cols; c++ {
		out[c] = make([]T, rows)
		for r := 0; r < rows; r++ {
			out[c][r] = m[r][c]
		}
	}
	return out
}

// Example:
// fmt.Println(Transpose([][]int{{1, 2, 3}, {4, 5, 6}})) // [[1 4] [2 5] [3 6]]''',
        'rust': r'''// Transpose turns an m x n matrix into n x m (rows become columns).
fn transpose<T: Clone>(m: Vec<Vec<T>>) -> Vec<Vec<T>> {
	if m.is_empty() {
		return vec![]
	}
	(0..m[0].len()).map(|c| m.iter().map(|row| row[c].clone()).collect()).collect()
}

// Example:
// println!("{:?}", transpose(vec![vec![1, 2, 3], vec![4, 5, 6]])); // [[1, 4], [2, 5], [3, 6]]''',
    },
    'count_words': {
        'python': r'''def count_words(text: str) -> dict[str, int]:
    """Return {word: count} for every word in the text."""
    counts: dict[str, int] = {}
    for word in text.lower().split():
        counts[word] = counts.get(word, 0) + 1
    return counts

# Punctuation-aware version:
def count_words_clean(text: str) -> dict[str, int]:
    import re
    words = re.findall(r'\b[\w\']+\b', text.lower())
    return {w: words.count(w) for w in set(words)}

# Example:
print(count_words("the cat and the dog and the bird"))
# {'the': 3, 'cat': 1, 'and': 2, 'dog': 1, 'bird': 1}''',
        'javascript': r'''function countWords(text) {
  const counts = {};
  for (const word of text.toLowerCase().split(/\s+/)) {
    if (word) counts[word] = (counts[word] || 0) + 1;
  }
  return counts;
}

# Example:
console.log(countWords('the cat and the dog and the bird'));
// { the: 3, cat: 1, and: 2, dog: 1, bird: 1 }''',
        'go': r'''// CountWords returns {word: count} for a text (whitespace-split, lowercase).
func CountWords(text string) map[string]int {
	counts := make(map[string]int)
	for _, w := range strings.Fields(strings.ToLower(text)) {
		counts[w]++
	}
	return counts
}

// Example:
// fmt.Println(CountWords("the cat and the dog and the bird")) // map[and:2 bird:1 cat:1 dog:1 the:3]''',
        'rust': r'''// CountWords returns {word: count} for a text (whitespace-split, lowercase).
use std::collections::HashMap;

fn count_words(text: &str) -> HashMap<String, usize> {
	let mut counts = HashMap::new();
	for w in text.to_lowercase().split_whitespace() {
		*counts.entry(w.to_string()).or_insert(0) += 1;
	}
	counts
}

// Example:
// println!("{:?}", count_words("the cat and the dog and the bird"));''',
    },
    'slugify': {
        'python': r'''import re

def slugify(text: str) -> str:
    """Turn any text into a URL-friendly slug."""
    s = text.lower()
    s = re.sub(r'[^a-z0-9]+', '-', s)   # non-alphanumerics -> dashes
    s = re.sub(r'-+', '-', s)           # collapse runs of dashes
    return s.strip('-')

# Examples:
print(slugify('Hello, World!'))       # hello-world
print(slugify('  Top 10  Recipes  ')) # top-10-recipes''',
        'javascript': r'''function slugify(text) {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')   // non-alphanumerics -> dashes
    .replace(/-+/g, '-')           // collapse runs of dashes
    .replace(/^-+|-+$/g, '');      // strip edge dashes
}

// Examples:
console.log(slugify('Hello, World!'));        // hello-world
console.log(slugify('  Top 10  Recipes  '));  // top-10-recipes''',
        'go': r'''// Slugify turns any text into a URL-friendly slug.
func Slugify(text string) string {
	var re = regexp.MustCompile(`[^a-z0-9]+`)
	s := strings.ToLower(text)
	s = re.ReplaceAllString(s, "-")
	s = strings.Trim(s, "-")
	return s
}

// Example:
// fmt.Println(Slugify("Hello, World!"))       // hello-world
// fmt.Println(Slugify("  Top 10  Recipes  ")) // top-10-recipes''',
        'rust': r'''// Slugify turns any text into a URL-friendly slug.
fn slugify(text: &str) -> String {
	let s: String = text
		.to_lowercase()
		.chars()
		.map(|c| if c.is_alphanumeric() { c } else { '-' })
		.collect();
	let s = s.split('-').filter(|p| !p.is_empty()).collect::<Vec<_>>().join("-");
	s
}

// Example:
// println!("{}", slugify("Hello, World!"));  // hello-world''',
    },
    'caesar_cipher': {
        'python': r'''def caesar_shift(text: str, shift: int) -> str:
    """Shift each letter by `shift` places (wraps around the alphabet)."""
    out = []
    for ch in text:
        if 'a' <= ch <= 'z':
            out.append(chr((ord(ch) - ord('a') + shift) % 26 + ord('a')))
        elif 'A' <= ch <= 'Z':
            out.append(chr((ord(ch) - ord('A') + shift) % 26 + ord('A')))
        else:
            out.append(ch)
    return ''.join(out)

# Examples:
print(caesar_shift('Hello, World!', 3))   # Khoor, Zruog!
print(caesar_shift('Khoor!', -3))         # Hello!''',
        'javascript': r'''function caesarShift(text, shift) {
  return text.replace(/[a-zA-Z]/g, (ch) => {
    const base = ch === ch.toLowerCase() ? 97 : 65; // 'a' or 'A'
    return String.fromCharCode(((ch.charCodeAt(0) - base + shift) % 26 + 26) % 26 + base);
  });
}

// Examples:
console.log(caesarShift('Hello, World!', 3));  // Khoor, Zruog!
console.log(caesarShift('Khoor!', -3));        // Hello!''',
        'go': r'''// CaesarShift shifts each letter by n places, wrapping around the alphabet.
func CaesarShift(text string, n int) string {
	out := []byte(text)
	for i, ch := range out {
		switch {
		case ch >= 'a' && ch <= 'z':
			out[i] = byte('a' + (ch-'a'+byte(n)%26+26)%26)
		case ch >= 'A' && ch <= 'Z':
			out[i] = byte('A' + (ch-'A'+byte(n)%26+26)%26)
		}
	}
	return string(out)
}

// Example:
// fmt.Println(CaesarShift("Hello, World!", 3)) // Khoor, Zruog!''',
        'rust': r'''// CaesarShift shifts each letter by n places, wrapping around the alphabet.
fn caesar_shift(text: &str, n: i32) -> String {
	text.chars()
		.map(|c| match c {
			'a'..='z' => ((c as i32 - 'a' as i32 + n).rem_euclid(26) + 'a' as i32) as u8 as char,
			'A'..='Z' => ((c as i32 - 'A' as i32 + n).rem_euclid(26) + 'A' as i32) as u8 as char,
			_ => c,
		})
		.collect()
}

// Example:
// println!("{}", caesar_shift("Hello, World!", 3)); // Khoor, Zruog!''',
    },
    'password_gen': {
        'python': r'''import secrets
import string

def generate_password(length: int = 16) -> str:
    """Cryptographically strong random password."""
    alphabet = string.ascii_letters + string.digits + string.punctuation
    if length < 8:
        raise ValueError('use at least 8 characters for a secure password')
    return ''.join(secrets.choice(alphabet) for _ in range(length))

# Example:
print(generate_password())  # e.g. 'k#9Fz!q2Lp@v7Xw$' — random every run''',
        'javascript': r'''function generatePassword(length = 16) {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' +
                   'abcdefghijklmnopqrstuvwxyz' +
                   '0123456789!@#$%^&*()_-+=<>?';
  if (length < 8) throw new Error('use at least 8 characters for a secure password');
  const bytes = new Uint32Array(length);
  crypto.getRandomValues(bytes);  // cryptographically secure
  return Array.from(bytes, (n) => alphabet[n % alphabet.length]).join('');
}

// Example:
console.log(generatePassword());  // random every run''',
    },
    'shuffle_list': {
        'python': r'''import random

def shuffle(items: list) -> list:
    """Fisher–Yates shuffle — every permutation equally likely."""
    arr = items[:]  # copy; shuffle in place if you want to mutate
    for i in range(len(arr) - 1, 0, -1):
        j = random.randrange(i + 1)
        arr[i], arr[j] = arr[j], arr[i]
    return arr

# Example:
print(shuffle([1, 2, 3, 4, 5]))  # e.g. [3, 1, 5, 2, 4] — random every run''',
        'javascript': r'''function shuffle(arr) {
  const a = arr.slice();  // copy; shuffle in place if you want to mutate
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

// Example:
console.log(shuffle([1, 2, 3, 4, 5]));  // random every run''',
        'go': r'''// Shuffle returns a random permutation of items (Fisher–Yates).
func Shuffle[T any](items []T, rnd *rand.Rand) []T {
	out := append([]T(nil), items...) // copy
	for i := len(out) - 1; i > 0; i-- {
		j := rnd.Intn(i + 1)
		out[i], out[j] = out[j], out[i]
	}
	return out
}

// Example:
// rnd := rand.New(rand.NewSource(time.Now().UnixNano()))
// fmt.Println(Shuffle([]int{1, 2, 3, 4, 5}, rnd))''',
        'rust': r'''// Shuffle returns a random permutation of items (Fisher–Yates).
fn shuffle<T: Clone>(mut items: Vec<T>, rng: &mut impl rand::Rng) -> Vec<T> {
	for i in (1..items.len()).rev() {
		let j = rng.gen_range(0..=i);
		items.swap(i, j);
	}
	items
}

// Requires the `rand` crate. Example:
// let mut rng = rand::thread_rng();
// println!("{:?}", shuffle(vec![1, 2, 3, 4, 5], &mut rng));''',
    },
    'memoize': {
        'python': r'''from functools import lru_cache

def memoize(func):
    """Cache results by positional arguments (unbounded)."""
    cache = {}
    def wrapper(*args):
        if args not in cache:
            cache[args] = func(*args)
        return cache[args]
    wrapper.cache = cache
    return wrapper

# Built-in alternative (preferred for production):
# from functools import lru_cache
# @lru_cache(maxsize=None)
# def fib(n): ...

# Example:
@memoize
def fib(n):
    return n if n < 2 else fib(n - 1) + fib(n - 2)

print(fib(40))  # 102334155 — instant thanks to the cache''',
        'javascript': r'''function memoize(fn) {
  const cache = new Map();
  return function (...args) {
    const key = JSON.stringify(args);
    if (!cache.has(key)) cache.set(key, fn(...args));
    return cache.get(key);
  };
}

// Example:
const fib = memoize(function fib(n) {
  return n < 2 ? n : fib(n - 1) + fib(n - 2);
});
console.log(fib(40));  // 102334155 — instant thanks to the cache''',
    },
    'retry_backoff': {
        'python': r'''import time
import random

def retry(func, attempts: int = 4, base_delay: float = 0.5, max_delay: float = 8.0):
    """Call func; retry with exponential backoff + jitter on any exception."""
    for attempt in range(attempts):
        try:
            return func()
        except Exception:
            if attempt == attempts - 1:
                raise
            delay = min(base_delay * (2 ** attempt), max_delay)
            time.sleep(delay / 2 + random.uniform(0, delay / 2))  # jitter
    raise RuntimeError('unreachable')

# Example (flaky network call):
def fetch():
    if random.random() < 0.5:
        raise ConnectionError('boom')
    return 'ok'

print(retry(fetch))  # eventually 'ok' unless it fails 4 times in a row''',
        'javascript': r'''async function retry(fn, { attempts = 4, baseDelay = 500, maxDelay = 8000 } = {}) {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  for (let attempt = 0; attempt < attempts; attempt++) {
    try {
      return await fn();
    } catch (err) {
      if (attempt === attempts - 1) throw err;
      const delay = Math.min(baseDelay * 2 ** attempt, maxDelay);
      await sleep(delay / 2 + Math.random() * delay / 2);  // jitter
    }
  }
}

// Example:
// await retry(fetchData, { attempts: 5 });''',
    },
    'json_pretty': {
        'python': r'''import json

def pretty_json(obj) -> str:
    """Serialize with 2-space indent, sorted keys for stable output."""
    return json.dumps(obj, indent=2, sort_keys=True)

# Example:
data = {'name': 'Ada', 'tags': ['math', 'computing'], 'active': True}
print(pretty_json(data))
# {
#   "active": true,
#   "name": "Ada",
#   "tags": [
#     "math",
#     "computing"
#   ]
# }''',
        'javascript': r'''function prettyJson(obj) {
  return JSON.stringify(obj, null, 2);
}

// Example:
const data = { name: 'Ada', tags: ['math', 'computing'], active: true };
console.log(prettyJson(data));
// {
//   "name": "Ada",
//   "tags": [
//     "math",
//     "computing"
//   ],
//   "active": true
// }''',
    },
}


# TypeScript templates: TS is a strict superset of JS, so any task without a
# dedicated TS template reuses the JavaScript implementation. The harness's
# signature parser accepts untyped function forms, so parameter alignment
# still works against TS signatures.
for _task, _langs in _CODE.items():
    if 'typescript' not in _langs and 'javascript' in _langs:
        _langs['typescript'] = _langs['javascript']


# ── Composition ────────────────────────────────────────────────────────────

def detect_task(query: str) -> Optional[str]:
    """Return the task id matching the query, or None."""
    q = query.lower().strip()
    for task_id, patterns in _TASK_PATTERNS:
        for pat in patterns:
            try:
                if re.search(pat, q):
                    return task_id
            except re.error:
                continue
    return None


def _lang_name(lang: str) -> str:
    display = {
        'python': 'Python', 'javascript': 'JavaScript', 'typescript': 'TypeScript',
        'java': 'Java', 'c++': 'C++', 'c': 'C', 'c#': 'C#', 'go': 'Go',
        'rust': 'Rust', 'ruby': 'Ruby', 'php': 'PHP', 'swift': 'Swift',
        'kotlin': 'Kotlin', 'sql': 'SQL', 'bash': 'bash', 'html': 'HTML',
        'css': 'CSS',
    }
    return display.get(lang, lang.title())


# ── Website generator (deterministic HTML/CSS) ──────────────────────────────
# "create a website for a taco shop" is a code task, not a knowledge lookup.
# The generator builds a single self-contained HTML file, with content chosen
# deterministically from the business type in the topic.

_WEB_TYPES = [
    # (keywords, tagline, accent, menu_heading, menu_items)
    ('taco', 'Fresh tacos, made to order.', '#e67e22', 'Menu', [
        'Carnitas — slow-braised pork',
        'Al Pastor — marinated pork, grilled pineapple',
        'Barbacoa — tender beef cheek',
        'Chorizo — house-made, crispy',
        'Fish — crispy, with lime crema',
        'Veggie — charred vegetables, queso fresco']),
    ('pizza', 'Wood-fired pizza, hand-stretched daily.', '#c0392b', 'Pizzas', [
        'Margherita — san marzano tomato, mozzarella, basil',
        'Pepperoni — double pepperoni, hot honey',
        'Quattro Formaggi — four cheeses, thyme',
        'Diavola — spicy salami, chili oil',
        'Veggie — roasted peppers, mushrooms, olives']),
    ('burger', 'House-ground patties on brioche.', '#8e44ad', 'Burgers', [
        'Classic Cheeseburger — cheddar, pickles, house sauce',
        'Smash Burger — caramelized edges, american cheese',
        'Bacon BBQ — smoked bacon, barbecue sauce',
        'Mushroom Swiss — sautéed mushrooms, swiss',
        'Veggie Burger — black bean patty, avocado']),
    ('sushi', 'Fresh fish, hand-rolled daily.', '#16a085', 'Rolls', [
        'California Roll — crab, avocado, cucumber',
        'Spicy Tuna Roll — tuna, chili mayo, scallion',
        'Salmon Avocado Roll — norwegian salmon, avocado',
        'Rainbow Roll — assorted fish over california',
        'Dragon Roll — eel, cucumber, avocado']),
    ('coffee', 'Small-batch roasted, brewed to order.', '#6d4c41', 'Drinks', [
        'Espresso', 'Cappuccino', 'Flat White', 'Cold Brew', 'Pour-Over',
        'Chai Latte']),
    ('bakery', 'Baked from scratch every morning.', '#d35400', 'Bakes', [
        'Sourdough Loaf', 'Croissants', 'Cinnamon Rolls', 'Bagels',
        'Seasonal Fruit Tart', 'Cookies']),
    ('ice cream', 'Small-batch churned daily.', '#2980b9', 'Flavors', [
        'Vanilla Bean', 'Chocolate Fudge', 'Strawberry', 'Mint Chip',
        'Salted Caramel', 'Seasonal Sorbet']),
    ('bar', 'Craft drinks, poured with care.', '#34495e', 'Drinks', [
        'House Cocktails', 'Local Draft Beer', 'Wine by the Glass',
        'Zero-Proof Cocktails', 'Bar Snacks']),
    ('restaurant', 'Seasonal plates, locally sourced.', '#7d3c98', 'Menu', [
        'Appetizers — daily small plates',
        'Mains — market fish, steaks, house pastas',
        'Desserts — made in-house',
        'Weekend Brunch']),
]

_WEB_STOP = re.compile(
    r'\b(?:create|make|build|design|generate|develop|craft|code|simple|'
    r'basic|minimal|modern|responsive|beautiful|static|personal|'
    r'professional|small|one-page|a|an|the|my|our|your|for|about|of|'
    r'please|website|web\s*site|web\s*page|site|landing\s*page|'
    r'homepage|home\s*page|portfolio)\b', re.IGNORECASE)


class _WebPlan:
    pass


def _extract_website_topic(query: str) -> str:
    """Pull the topic out of a website request ("taco shop")."""
    q = query.strip()
    # 1. "website for <topic>" / "page about <topic>"
    m = re.search(
        r'\b(?:website|web\s*site|web\s*page|landing\s*page|homepage|'
        r'home\s*page|portfolio|site)\b\s*(?:for|about|of|to\s+promote)?\s*'
        r'(?:a|an|the|my|our)?\s*(.+)$', q, re.IGNORECASE)
    if m:
        topic = _WEB_STOP.sub(' ', m.group(1))
        topic = re.sub(r'\s+', ' ', topic).strip(' .')
        if topic:
            return topic
    # 2. noun-first: "<topic> website" / "build a portfolio website" — the
    #    words before the site-type keyword are the topic.
    m2 = re.search(
        r'^(.*?)\s+(?:website|web\s*site|web\s*page|site|landing\s*page|'
        r'homepage|home\s*page|portfolio)\b', q, re.IGNORECASE)
    if m2:
        topic = _WEB_STOP.sub(' ', m2.group(1))
        topic = re.sub(r'\s+', ' ', topic).strip(' .')
        if topic:
            return topic
    # 3. the site type itself is the topic ("a portfolio")
    m3 = re.search(r'\b(?:portfolio|landing\s*page)\b', q, re.IGNORECASE)
    if m3:
        return m3.group(0).title()
    return 'Our Business'


def _website_plan(topic: str) -> dict:
    """Map a topic to a site plan (name, tagline, sections, accent)."""
    low = topic.lower()
    for kw, tagline, accent, menu_h, items in _WEB_TYPES:
        if kw in low:
            return {
                'name': topic.title(),
                'tagline': tagline,
                'accent': accent,
                'sections': [('Menu', items),
                             ('About',
                              [f"{topic.title()} started with one simple idea: do the basics right, every day.",
                               'Everything here is made fresh in-house.']),
                             ('Hours',
                              ['Mon–Fri: 11am – 9pm',
                               'Sat: 10am – 10pm',
                               'Sun: 10am – 8pm']),
                             ('Find Us',
                              ['123 Main Street',
                               '(555) 010-5555']),
                             ],
            }
    return {
        'name': topic.title(),
        'tagline': f'{topic.title()} — quality you can count on.',
        'accent': '#2c3e50',
        'sections': [('About',
                      [f"{topic.title()} serves our customers with care and consistency."],
                      ),
                     ('Hours',
                      ['Mon–Fri: 9am – 6pm', 'Sat: 10am – 4pm',
                       'Sun: closed']),
                     ('Contact',
                      ['123 Main Street', '(555) 010-5555',
                       'hello@example.com']),
                     ],
    }


def _website_html(plan: dict) -> str:
    """Render the plan as a single self-contained HTML file."""
    name = plan['name']
    accent = plan['accent']
    nav = '\n      '.join(
        f'<a href="#{re.sub(r"[^a-z0-9]+", "-", h.lower()).strip("-")}">{h}</a>'
        for h, _ in plan['sections'])
    secs = []
    for heading, items in plan['sections']:
        anchor = re.sub(r'[^a-z0-9]+', '-', heading.lower()).strip('-')
        lis = '\n        '.join(f'<li>{it}</li>' for it in items)
        secs.append(
            f'  <section id="{anchor}">\n'
            f'    <h2>{heading}</h2>\n'
            f'    <ul>\n        {lis}\n    </ul>\n'
            f'  </section>')
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{name}</title>
  <style>
    :root {{ --accent: {accent}; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: system-ui, -apple-system, sans-serif;
           color: #222; line-height: 1.6; }}
    header {{ display: flex; justify-content: space-between;
             align-items: center; padding: 1rem 2rem;
             border-bottom: 1px solid #eee; }}
    .brand {{ font-weight: 700; font-size: 1.2rem; }}
    nav a {{ margin-left: 1.2rem; color: #444; text-decoration: none; }}
    nav a:hover {{ color: var(--accent); }}
    .hero {{ background: var(--accent); color: #fff; text-align: center;
            padding: 4rem 2rem; }}
    .hero h1 {{ margin: 0 0 .5rem; font-size: 2.6rem; }}
    .hero p {{ margin: 0; font-size: 1.2rem; opacity: .95; }}
    main {{ max-width: 46rem; margin: 0 auto; padding: 2rem; }}
    section {{ margin-bottom: 2.5rem; }}
    h2 {{ color: var(--accent); border-bottom: 2px solid var(--accent);
         padding-bottom: .3rem; }}
    ul {{ padding-left: 1.2rem; }}
    li {{ margin: .35rem 0; }}
    footer {{ text-align: center; color: #888; padding: 1.5rem;
             border-top: 1px solid #eee; }}
    @media (max-width: 640px) {{
      header {{ flex-direction: column; gap: .5rem; }}
      nav a {{ margin: 0 .6rem; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="brand">{name}</div>
    <nav>
      {nav}
    </nav>
  </header>
  <main>
    <section class="hero">
      <h1>{name}</h1>
      <p>{plan['tagline']}</p>
    </section>
{chr(10).join(secs)}
  </main>
  <footer>© 2026 {name}</footer>
</body>
</html>'''


def _website_answer(query: str) -> str:
    """Full chat answer for a website-creation request."""
    topic = _extract_website_topic(query)
    plan = _website_plan(topic)
    html = _website_html(plan)
    slug = re.sub(r'[^a-z0-9]+', '-', plan['name'].lower()).strip('-')
    intro = (f"Here's a complete, self-contained website for {plan['name']} — "
             f"a single HTML file with embedded CSS. Save it as "
             f"`{slug}.html` and open it in any browser.")
    notes = ("Sample content only — swap in your real menu, hours, address, "
             "and photos. To publish, drop the file into a static host "
             "(GitHub Pages, Netlify) or ask me to add a contact form.")
    return f"{intro}\n\n```html\n{html}\n```\n\n{notes}"


def generate_code(query: str, lang: Optional[str] = None) -> Optional[str]:
    """Synthesize a complete answer (intro + code + notes) for a coding query.

    Args:
        query: the coding question.
        lang:  force a language (used for "now do the same in rust" style
               follow-ups); when None the language is detected from the query.

    Returns None when the query doesn't map to a known task + language combo.
    """
    if lang is None:
        lang = detect_language(query)
    task = detect_task(query)
    if task is None:
        return None
    if task == 'web_page':
        return _website_answer(query)

    code_templates = _CODE.get(task)
    if not code_templates:
        return None

    # Task-specific default languages: git/bash tasks are shell commands;
    # sql_* tasks are SQL; everything else defaults to Python when the query
    # doesn't name a language.
    if lang is None:
        if task.startswith('sql'):
            lang = 'sql'
        elif (task.startswith(('git', 'bash', 'sys'))
              or task in ('pip_install', 'npm_install')):
            lang = 'bash'
        else:
            lang = 'python'

    code = code_templates.get(lang)
    if code is None:
        # Task known but no template for the requested language: only
        # typescript→javascript is close enough to fall back to; otherwise
        # give up (never silently hand over the wrong language).
        if lang == 'typescript' and 'javascript' in code_templates:
            code = code_templates['javascript']
        else:
            return None

    intro = _TASK_INTRO.get(task, "Here's a {lang} snippet for that.")
    notes = _TASK_NOTES.get(task, '')
    display = _lang_name(lang)

    parts = [intro.format(lang=display)]
    parts.append(f"```{lang}\n{code}\n```")
    if notes:
        parts.append(notes)
    if lang == 'typescript':
        parts.append("Note: TypeScript and JavaScript share syntax — the code above runs in both, with type annotations you can add as needed.")
    if lang == 'python' and detect_language(query) is None and not task.startswith(('sql', 'git', 'bash')):
        parts.append("I assumed Python since you didn't name a language — tell me another language and I'll give you the same thing in it.")
    _detected = detect_language(query)
    if _detected and _detected != lang:
        parts.append(f"Here's the same thing in {display}.")
    return '\n\n'.join(parts)
