"""NLG Information Cleaning — remove noise, normalize text."""

import re
from typing import List, Optional
from .util import split_sentences


def clean_information(text: str, max_sentences: Optional[int] = None) -> str:
    """Clean raw information: remove pronunciation guides, normalize, truncate if requested."""
    if not text:
        return ""
    # Remove pronunciation guides like "(/ˈfɪzɪks/)"
    text = re.sub(r'\([^)]*\/[^)]*\)', '', text)
    # Remove empty parentheses
    text = re.sub(r'\(\s*\)', '', text)
    # Remove citation brackets like [1], [2]
    text = re.sub(r'\[\d+(?:–\d+)?\]', '', text)
    # Remove code blocks and code-like lines (def, class, import, print, return with indentation)
    text = re.sub(r'(?:^|\n)\s*(?:def |class |import |from \S+ import |print\(|if __name__|for .+ in .+:|while .+:|try:|except |raise |yield |async |await ).*?(?:\n|$)', '\n', text)
    # Remove lines that look like code (indented with specific patterns)
    text = re.sub(r'(?:^|\n)\s{4,}(?:return |self\.|raise |print\().*?(?:\n|$)', '\n', text)
    # Remove function signature lines like "def solution(input_data):"
    text = re.sub(r'(?:^|\n)\s*def\s+\w+\s*\(.*?\)\s*(?:->.*?)?:\s*\n', '\n', text)
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    # Truncate only if max_sentences is explicitly specified
    if max_sentences is not None:
        sents = split_sentences(text)
        if len(sents) > max_sentences:
            sents = sents[:max_sentences]
            text = ' '.join(sents).strip()
    return text

