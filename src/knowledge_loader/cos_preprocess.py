#!/usr/bin/env python3
"""
COS Dataset Pre-processor
Converts JSONL conversation datasets into COS-readable format.

Usage: python3 cos_preprocess.py dataset.jsonl > output.tsv
       python3 cos_preprocess.py dataset.jsonl | cos_knowledge_loader /dev/stdin

Output format (tab-separated):
  role\tcontent
  ---  (separator between conversations)
"""

import json
import sys

def process_file(path):
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Handle different formats
            messages = None
            if 'messages' in data:
                messages = data['messages']
            elif 'conversations' in data:
                messages = data['conversations']
            elif isinstance(data, list):
                messages = data

            if not messages or not isinstance(messages, list):
                continue

            for msg in messages:
                if isinstance(msg, dict):
                    role = msg.get('role', msg.get('from', 'unknown'))
                    content = msg.get('content', msg.get('value', ''))
                    # Clean content
                    content = content.replace('\n', ' ').replace('\t', ' ').strip()
                    if content:
                        print(f"{role}\t{content}")
            print("---")  # conversation separator

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 cos_preprocess.py dataset.jsonl > output.tsv", file=sys.stderr)
        sys.exit(1)
    process_file(sys.argv[1])
