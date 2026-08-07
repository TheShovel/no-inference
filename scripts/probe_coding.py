#!/usr/bin/env python3
"""Probe battery: how well does COS handle realistic coding prompts?

Runs a large, curated battery of coding prompts (written the way a developer
asks an LLM) through the full engine pipeline (process_query) and the direct
synthesizer (generate_code), then reports which ones fail and why.

Usage:
    python3 scripts/probe_coding.py            # summary + failures
    python3 scripts/probe_coding.py --json     # machine-readable results
    python3 scripts/probe_coding.py --full     # print every response
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'src'))

from cos.engine import process_query, reset_conversation  # noqa: E402
from cos import code_gen  # noqa: E402

# Probes must not pollute the repo's persistent Wikipedia cache — route
# cache writes to a scratch file that disappears with the process.
import cos.engine as _engine  # noqa: E402
import tempfile as _tempfile  # noqa: E402
_engine._WIKI_CACHE_FILE = _engine.Path(_tempfile.mktemp(suffix='.json'))
_engine._WIKI_CACHE.clear()


# ── Battery: (query, expected_task_or_None, expected_lang_or_None, snippet) ──
# snippet must appear in the response (case-insensitive). task/lang are
# checked against detect_task / detect_language when not None.

BATTERY = [
    # ── algorithms ──────────────────────────────────────────────────────────
    ("write a python function that checks if a number is prime", "prime", "python", "def is_prime"),
    ("implement a function that returns the nth fibonacci number in python", "fibonacci", "python", "def fibonacci"),
    ("write a function to compute the factorial of a number in javascript", "factorial", "javascript", "function factorial"),
    ("fizzbuzz in rust", "fizzbuzz", "rust", "fn fizzbuzz"),
    ("write a python function that finds the gcd of two numbers", "gcd", "python", "def gcd"),
    ("implement binary search in python", "binary_search", "python", "def binary_search"),
    ("merge two sorted arrays into one sorted array in go", "merge_sorted", "go", "func MergeSorted"),
    ("how do i sort a list of numbers in python", "sort_list", "python", "sorted"),
    ("write a python function to check if a number is even", "is_even", "python", "def is_even"),
    ("write a python function that computes x raised to the power n", "power", "python", "def power"),
    # ── strings ─────────────────────────────────────────────────────────────
    ("write a python function that reverses a string", "reverse_string", "python", "def reverse_string"),
    ("reverse an array in javascript", "reverse_array", "javascript", ".reverse"),
    ("check if a string is a palindrome in python", "palindrome_string", "python", "def is_palindrome"),
    ("write a python function to check if two strings are anagrams", "anagram", "python", "def are_anagrams"),
    ("find the most frequent character in a string in python", "most_frequent", "python", "def most_frequent"),
    ("count how many times a substring appears in a string in javascript", "count_occurrences", "javascript", "countOccurrences"),
    ("get the length of a string in bash", "string_length", "bash", "${#"),
    ("write a python function to check if parentheses are balanced", "balanced_parens", "python", "def is_balanced"),
    ("convert a list to a comma separated string in python", "list_to_string", "python", "join"),
    ("split a string into a list in python", "string_to_list", "python", "split"),
    ("convert a string to uppercase in javascript", "string_case", "javascript", "toUpperCase"),
    ("trim whitespace from a string in python", "strip_whitespace", "python", "strip"),
    ("write a python function to slugify a title", "slugify", "python", "def slugify"),
    ("implement a caesar cipher in python", "caesar_cipher", "python", "def caesar"),
    # ── data structures ─────────────────────────────────────────────────────
    ("remove duplicates from a list in python", "dedup", "python", "set"),
    ("flatten a nested list in python", "flatten", "python", "def flatten"),
    ("sum all numbers from 1 to n in javascript", "sum_range", "javascript", "sum1ToN"),
    ("sum a list of numbers in python", "sum_list", "python", "sum"),
    ("solve two sum in python", "two_sum", "python", "def two_sum"),
    ("implement a binary search tree in python", "bst", "python", "TreeNode"),
    ("implement a linked list in javascript", "linked_list", "javascript", "ListNode"),
    ("write a python function for depth first search on a graph", "graph_traversal", "python", "def dfs"),
    ("find the intersection of two lists in python", "list_intersection", "python", "intersection"),
    ("compute the union of two lists in python", "list_union", "python", "union"),
    ("check if a list is empty in javascript", "list_empty", "javascript", ".length"),
    ("reverse a dictionary in python", "reverse_dict", "python", "def reverse_dict"),
    ("rotate a list to the right by k positions in python", "rotate_list", "python", "def rotate"),
    ("find the median of a list in python", "median", "python", "def median"),
    ("chunk a list into pieces of size n in python", "chunk_list", "python", "def chunk"),
    ("transpose a matrix in python", "transpose_matrix", "python", "def transpose"),
    ("count the number of words in a string in python", "count_words", "python", "def count_words"),
    ("shuffle a list randomly in python", "shuffle_list", "python", "shuffle"),
    # ── regex ───────────────────────────────────────────────────────────────
    ("regex to validate an email address in python", "regex_email", "python", "@"),
    ("regex to match a phone number in javascript", "regex_phone", "javascript", "\\d"),
    ("write a regex to validate a strong password in python", "regex_password", "python", "password"),
    ("regex to extract all urls from text in python", "regex_url", "python", "https"),
    ("extract all email addresses from a text in python", "extract_emails", "python", "findall"),
    ("regex to match an ip address in python", "regex_ip", "python", "ipv4"),
    # ── file / data I/O ─────────────────────────────────────────────────────
    ("read a csv file with python", "read_csv", "python", "DictReader"),
    ("write data to a csv file in python", "write_csv", "python", "csv.writer"),
    ("how do i read a file in python", "read_file", "python", "open("),
    ("write a string to a file in javascript", "write_file", "javascript", "writeFile"),
    ("read a json file in python", "read_json", "python", "json.load"),
    ("write a json file in python", "write_json", "python", "json.dump"),
    ("list all files in a directory in python", "list_files", "python", "listdir"),
    ("delete a file in python", "delete_file", "python", "os.remove"),
    ("copy a file in python", "copy_file", "python", "shutil.copy"),
    ("check if a file exists in bash", "file_exists", "bash", "-f"),
    ("get the current working directory in python", "cwd", "python", "getcwd"),
    ("zip a folder in python", "zip_folder", "python", "shutil.make_archive"),
    ("extract a zip file in python", "unzip", "python", "ZipFile"),
    ("pretty print json in python", "json_pretty", "python", "json.dumps"),
    # ── http / web ──────────────────────────────────────────────────────────
    ("make an http get request in python", "http_get", "python", "requests.get"),
    ("make a post request with json in javascript", "http_post", "javascript", "fetch"),
    ("check if a url is reachable in bash", "check_url", "bash", "curl"),
    ("send an email in python", "send_email", "python", "smtplib"),
    ("scrape a website with python", "web_scrape", "python", "BeautifulSoup"),
    ("parse an html table with python", "fetch_table", "python", "read_html"),
    ("create an express api server in node", "express_api", "javascript", "express"),
    ("create a flask api in python", "flask_api", "python", "Flask"),
    # ── sql ─────────────────────────────────────────────────────────────────
    ("select all rows from a table in sql", "sql_select", "sql", "SELECT"),
    ("insert a row in sql", "sql_insert", "sql", "INSERT"),
    ("update a row in sql", "sql_update", "sql", "UPDATE"),
    ("delete a row in sql", "sql_delete", "sql", "DELETE"),
    ("join two tables in sql", "sql_join", "sql", "JOIN"),
    ("group rows and count them in sql", "sql_group_by", "sql", "GROUP BY"),
    ("find duplicate rows in sql", "sql_duplicates", "sql", "GROUP BY"),
    ("create a table in sql", "sql_create_table", "sql", "CREATE TABLE"),
    ("get the average of a column in sql", "sql_aggregate", "sql", "AVG"),
    # ── sysadmin / bash ─────────────────────────────────────────────────────
    ("install a package with pip", "pip_install", "bash", "pip install"),
    ("install a package with npm", "npm_install", "bash", "npm install"),
    ("check disk usage in linux", "sys_disk", "bash", "df -h"),
    ("check memory usage in linux", "sys_mem", "bash", "free -h"),
    ("find what process is using port 8080", "sys_port", "bash", "lsof"),
    ("kill a process by name in linux", "sys_kill", "bash", "pkill"),
    ("find large files in linux", "sys_large_files", "bash", "find"),
    ("backup a directory in python", "backup_dir", "python", "backup"),
    ("write a bash script that takes command line arguments", "bash_args", "bash", "$1"),
    ("use curl to send a post request in bash", "bash_curl", "bash", "curl"),
    ("git undo the last commit", "git_undo", "bash", "git reset"),
    ("how do i commit changes with git", "git_commit", "bash", "git commit"),
    ("create a new git branch", "git_branch", "bash", "git checkout -b"),
    ("git stash my changes", "git_stash", "bash", "git stash"),
    ("show git log in a compact format", "git_log", "bash", "git log"),
    # ── basics / misc ───────────────────────────────────────────────────────
    ("write a for loop in python", "for_loop", "python", "for "),
    ("how do i write a comment in python", "comment_syntax", "python", "#"),
    ("check if an array contains a value in javascript", "array_contains", "javascript", "includes"),
    ("convert a string to a number in javascript", "string_to_number", "javascript", "Number"),
    ("rename a file in python", "rename_file", "python", "os.rename"),
    ("parse command line arguments in python", "cli_args", "python", "argparse"),
    ("read an environment variable in python", "env_vars", "python", "os.environ"),
    ("generate a random number in python", "random_number", "python", "random"),
    ("generate a random password in python", "password_gen", "python", "secrets"),
    ("memoize a function in python", "memoize", "python", "cache"),
    ("retry a request with exponential backoff in python", "retry_backoff", "python", "backoff"),
    ("convert celsius to fahrenheit in python", "temp_convert", "python", "celsius_to_fahrenheit"),
    ("compute the square root of a number in python", "sqrt", "python", "sqrt"),
    ("check if a year is a leap year in python", "leap_year", "python", "leap"),
    ("get yesterday's date in python", "yesterday_date", "python", "timedelta"),
    ("copy text to the clipboard in javascript", "clipboard", "javascript", "clipboard"),
    # ── new / likely-missing tasks (the interesting failures) ───────────────
    ("write a python function that sorts a dictionary by its values", None, "python", "sorted"),
    ("merge two dictionaries in python", None, "python", "update"),
    ("zip two lists together in python", None, "python", "zip("),
    ("write a python decorator that times a function", None, "python", "decorator"),
    ("generate a uuid in python", None, "python", "uuid4"),
    ("compute the md5 hash of a string in python", None, "python", "hashlib"),
    ("encode a string in base64 in python", None, "python", "b64encode"),
    ("convert a unix timestamp to a readable date in python", None, "python", "fromtimestamp"),
    ("format a date as yyyy-mm-dd in python", None, "python", "strftime"),
    ("get the current time in a specific timezone in python", None, "python", "timezone"),
    ("convert a file size to a human readable string in python", None, "python", "def human_file_size"),
    ("write a python function to find the longest common prefix of strings", None, "python", "def longest_common_prefix"),
    ("implement a lru cache in python", None, "python", "OrderedDict"),
    ("implement a queue using two stacks in python", None, "python", "class QueueWithStacks"),
    ("detect a cycle in a linked list in python", None, "python", "def has_cycle"),
    ("reverse a linked list in python", None, "python", "def reverse"),
    ("implement a trie in python", None, "python", "class Trie"),
    ("implement a min heap in python", None, "python", "heapq"),
    ("top k frequent elements in a list in python", None, "python", "Counter"),
    ("merge intervals in python", None, "python", "def merge_intervals"),
    ("implement a stack in python", None, "python", "class Stack"),
    ("implement a queue in python", None, "python", "class Queue"),
    ("write a python function for breadth first search on a graph", None, "python", "def bfs"),
    ("implement dijkstra's algorithm in python", None, "python", "def dijkstra"),
    ("find the longest substring without repeating characters in python", None, "python", "def length_of_longest_substring"),
    ("run-length encode a string in python", None, "python", "def run_length"),
    ("find the first non-repeating character in a string in python", None, "python", "def first_unique"),
    ("reverse words in a sentence in python", None, "python", "def reverse_words"),
    ("write a python function that converts a string to title case", None, "python", "title"),
    ("validate a date string in the format yyyy-mm-dd in python", None, "python", "strptime"),
    ("extract all numbers from a string in python", None, "python", "findall"),
    ("regex to match a hex color code in python", None, "python", "#[0-9a-fA-F]"),
    ("write a sql query using a window function to rank rows", None, "sql", "RANK"),
    ("write a sql query with a common table expression", None, "sql", "WITH"),
    ("add an index to a sql table", None, "sql", "CREATE INDEX"),
    ("write a sql case statement", None, "sql", "CASE"),
    ("write a sql query that uses a subquery", None, "sql", "SELECT"),
    ("dockerfile for a python flask app", None, None, "FROM python"),
    ("write a docker-compose file for a web app", None, None, "docker-compose"),
    ("github actions workflow to run tests on push", None, None, "on:"),
    ("write a .gitignore for a python project", None, None, "__pycache__"),
    ("create a setup.py for a python package", None, None, "setup("),
    ("write a pytest test for a python function", None, "python", "def test_"),
    ("write unit tests in javascript with jest", None, None, "describe("),
    ("create a react todo list component", None, "javascript", "useState"),
    ("write a python script to download a file from a url", None, "python", "requests.get"),
    ("write a python script to monitor a log file", None, "python", "tail"),
    ("schedule a cron job to run a script daily", None, None, "cron"),
    ("create a systemd service for a python app", None, None, "[Service]"),
    ("write a bash script to watch a file for changes", None, "bash", "inotify"),
    ("compress a directory with tar", None, "bash", "tar -czf"),
    ("grep recursively for a pattern in linux", None, "bash", "grep -r"),
    ("write a bash script to backup a directory with rsync", None, "bash", "rsync"),
    ("show only the last 50 lines of a log file and follow it", None, "bash", "tail -f"),
    ("convert an mp4 to gif with ffmpeg", None, "bash", "ffmpeg"),
    ("find and delete files older than 30 days in linux", None, "bash", "find"),
    ("write a python function to check if a string is a valid email", None, "python", "def is_valid_email"),
    ("write a python function to download and unzip a file", None, "python", "zipfile"),
    ("how do i read an environment variable in bash", None, "bash", "${"),
    ("write a bash script that loops over files in a directory", None, "bash", "for "),
    ("write a python script that reads a csv and prints each row", None, "python", "DictReader"),
    ("write a python function to get all keys of a dictionary", None, "python", ".keys"),
    ("write a python function that capitalizes the first letter of each word", None, "python", "title"),
    ("write a python function to check if a list has any duplicates", None, "python", "len("),
    ("find the most common word in a text file in python", None, "python", "Counter"),
    ("sort a list of dictionaries by a key in python", None, "python", "key="),
    ("group a list of dictionaries by a field in python", None, "python", "groupby"),
    ("write a python function to read a config file", None, "python", "configparser"),
    ("write a python function to deep copy an object", None, "python", "copy.deepcopy"),
    ("write a python function that returns the current timestamp", None, "python", "time.time"),
    ("convert a string to lowercase in python", None, "python", ".lower"),
    ("remove empty strings from a list in python", None, "python", "filter"),
    ("write a python function to check if a number is odd", None, "python", "% 2"),
    ("find the largest number in a list in python", None, "python", "max("),
    ("write a python function to compute the average of a list", None, "python", "average"),
    ("write a python function to get the unique characters in a string", None, "python", "set("),
    ("reverse a string in bash", None, "bash", "rev"),
    ("get the file extension of a file in python", None, "python", "splitext"),
    ("check if a string starts with a prefix in python", None, "python", "startswith"),
    ("replace all occurrences of a word in a string in python", None, "python", ".replace"),
    ("write a python function that returns the intersection of two dictionaries", None, "python", "items"),
    ("write a python function to count lines in a file", None, "python", "def count_lines"),
    ("parse a json string in javascript", None, "javascript", "JSON.parse"),
    ("stringify an object to json in javascript", None, "javascript", "JSON.stringify"),
    ("make a fetch request with error handling in javascript", None, "javascript", "try"),
    ("async await in javascript example", None, "javascript", "async"),
    ("promise.all example in javascript", None, "javascript", "Promise.all"),
    ("debounce a function in javascript", None, "javascript", "debounce"),
    ("throttle a function in javascript", None, "javascript", "throttle"),
    ("shallow copy an object in javascript", None, "javascript", "Object.assign"),
    ("deep clone an object in javascript", None, "javascript", "structuredClone"),
    ("write a javascript function to format a number as currency", None, "javascript", "toLocaleString"),
    ("get the current date in javascript", None, "javascript", "new Date"),
    ("set a timeout in javascript", None, "javascript", "setTimeout"),
    ("add an event listener in javascript", None, "javascript", "addEventListener"),
    ("remove an element from the dom in javascript", None, "javascript", "remove()"),
    ("fetch data from an api and render it in javascript", None, "javascript", "fetch"),
    ("write a javascript function to filter an array", None, "javascript", ".filter"),
    ("write a javascript function to map an array to new values", None, "javascript", ".map"),
    ("reduce an array to a single value in javascript", None, "javascript", ".reduce"),
    ("sort an array of objects by a property in javascript", None, "javascript", "sort"),
    ("get the last element of an array in javascript", None, "javascript", "length"),
    ("merge two arrays in javascript", None, "javascript", "concat"),
    ("check if a string contains a substring in javascript", None, "javascript", "includes"),
    ("split a string by comma in javascript", None, "javascript", "split"),
    ("find an element in an array in javascript", None, "javascript", ".find"),
    ("generate a random integer between 1 and 10 in javascript", None, "javascript", "Math.random"),
    ("round a number to 2 decimal places in javascript", None, "javascript", "toFixed"),
    ("get the length of an object in javascript", None, "javascript", "Object.keys"),
    ("loop over an object's values in javascript", None, "javascript", "Object.values"),
    ("write a go function to read a file", None, "go", "os.ReadFile"),
    ("write a go function to get an http request", None, "go", "http.Get"),
    ("write a go function to parse json", None, "go", "json.Unmarshal"),
    ("write a rust function to read a file", None, "rust", "fs::read_to_string"),
    ("write a rust function that computes the factorial", None, "rust", "fn factorial"),
    ("write a java function to read a file", None, "java", "Files.readAllLines"),
    ("write a java function that reverses a string", None, "java", "StringBuilder"),
    ("write a c++ function to sort a vector", None, "c++", "std::sort"),
    ("write a c# method to read a file", None, "c#", "File.ReadAllText"),
    ("write a ruby function to read a file", None, "ruby", "File.read"),
    ("write a php function to read a file", None, "php", "file_get_contents"),
    ("write a swift function to reverse a string", None, "swift", "reversed"),
    ("write a kotlin function to read a file", None, "kotlin", "readText"),
    ("write a sql query to find the second highest salary", None, "sql", "LIMIT"),
    ("write a sql query to delete duplicate rows keeping one", None, "sql", "DELETE"),
    ("write a sql query to get the top 10 rows", None, "sql", "LIMIT"),
    ("write a sql query to count rows per category", None, "sql", "GROUP BY"),
    ("write a sql query to join three tables", None, "sql", "JOIN"),
    ("write a sql query with a left join", None, "sql", "LEFT JOIN"),
]


def _fence_lang(answer: str):
    m = re.search(r'```([^\s`]+)', answer or '')
    if not m:
        return None
    lang = m.group(1).lower()
    return {'js': 'javascript', 'py': 'python', 'cpp': 'c++', 'cs': 'c#', 'jsx': 'javascript', 'tsx': 'javascript', 'ts': 'typescript'}.get(lang, lang)


def _has_fence(answer: str) -> bool:
    return bool(re.search(r'```', answer or ''))


def run_probes(probes, verbose=False):
    reset_conversation()
    results = []
    for q, exp_task, exp_lang, snippet in probes:
        reset_conversation()   # isolate per-query routing (no cross-talk)
        task = code_gen.detect_task(q)
        lang = code_gen.detect_language(q)
        response = process_query(q)
        low = (response or '').lower()
        ok = True
        reasons = []
        if not _has_fence(response):
            ok = False
            reasons.append('no code fence')
        if exp_task is not None and task != exp_task:
            ok = False
            reasons.append(f'task={task!r} (want {exp_task!r})')
        if exp_lang is not None:
            fl = _fence_lang(response)
            if fl != exp_lang:
                ok = False
                reasons.append(f'fence lang={fl!r} (want {exp_lang!r})')
        if snippet is not None:
            if snippet.lower() not in low:
                ok = False
                reasons.append(f'missing snippet {snippet!r}')
        if not response or len(response) < 40:
            ok = False
            reasons.append(f'response too short ({len(response or "")} chars)')
        results.append({
            'q': q, 'ok': ok, 'task': task, 'lang': lang,
            'fence_lang': _fence_lang(response), 'snippet': snippet,
            'reasons': reasons, 'response': response,
        })
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--full', action='store_true')
    ap.add_argument('--only-fail', action='store_true')
    args = ap.parse_args()

    results = run_probes(BATTERY)
    passed = sum(1 for r in results if r['ok'])
    total = len(results)

    if args.json:
        print(json.dumps([{k: r[k] for k in
                           ('q', 'ok', 'task', 'lang', 'fence_lang',
                            'snippet', 'reasons')} for r in results],
                         indent=1))
        return

    print(f'{"=" * 100}')
    print(f'PROBE RESULTS: {passed}/{total} pass '
          f'({100.0 * passed / total:.1f}%)')
    print(f'{"=" * 100}')

    for r in results:
        if args.only_fail and r['ok']:
            continue
        mark = 'PASS' if r['ok'] else 'FAIL'
        extra = ' | '.join(r['reasons']) if r['reasons'] else ''
        print(f"[{mark}] task={str(r['task']):24s} lang={str(r['lang']):12s} "
              f"fence={str(r['fence_lang']):10s} {extra}")
        print(f"      {r['q']}")
        if args.full:
            print('      ' + (r['response'] or '')[:800].replace('\n', '\n      '))
            print('      ' + '-' * 90)

    # group failures by reason
    print(f'\n{"=" * 100}')
    print('FAILURE BREAKDOWN')
    print(f'{"=" * 100}')
    from collections import Counter
    counters = {
        'no code fence': 0,
        'wrong task': Counter(),
        'wrong lang': Counter(),
        'missing snippet': Counter(),
    }
    for r in results:
        if r['ok']:
            continue
        if 'no code fence' in r['reasons']:
            counters['no code fence'] += 1
        if any(x.startswith('task=') for x in r['reasons']):
            counters['wrong task'][r['q']] += 1
        if any(x.startswith('fence lang=') for x in r['reasons']):
            counters['wrong lang'][r['q']] += 1
        if any(x.startswith('missing snippet') for x in r['reasons']):
            counters['missing snippet'][r['q']] += 1
    print(f"no code fence: {counters['no code fence']}")
    print(f"wrong task: {len(counters['wrong task'])}")
    for q in counters['wrong task']:
        print(f"    - {q}")
    print(f"wrong lang: {len(counters['wrong lang'])}")
    for q in counters['wrong lang']:
        print(f"    - {q}")
    print(f"missing snippet: {len(counters['missing snippet'])}")
    for q in counters['missing snippet']:
        print(f"    - {q}")


if __name__ == '__main__':
    main()
