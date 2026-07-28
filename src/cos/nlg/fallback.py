"""NLG Fallback Responses — natural responses when no information is available.

When all KB lookups and Wikipedia searches fail, this module provides
the final fallback. It tries to extract a topic from the query and
return whatever Wikipedia content it can find.
"""

from .config import NLGConfig
from .util import pick
import re


def fallback_response(query: str, config: NLGConfig) -> str:
    """Generate a response when no specific information was found.
    
    Tries to find ANY Wikipedia content for the query topic.
    Falls back to generic messages if that fails too.
    """
    q = query.strip()
    
    # Try to find Wikipedia content using aliases and search
    # Use two separate try blocks so if one method times out, the other still runs
    try:
        from urllib.request import Request, urlopen
        import urllib.parse
        import json as _json
        from pathlib import Path
        
        # Load aliases
        alias_file = Path(__file__).parent.parent.parent.parent / 'data' / 'aliases.json'
        search_term = None
        if alias_file.exists():
            try:
                aliases = _json.loads(alias_file.read_text())
                q_lower = q.lower().strip()
                sorted_alias = sorted(aliases.items(), key=lambda x: len(x[0]), reverse=True)
                for alias_key, alias_val in sorted_alias:
                    if alias_key in q_lower:
                        search_term = alias_val
                        break
            except Exception:
                pass
        
        if not search_term:
            clean = q.lower()
            clean = re.sub(r'^(?:write|create|make|give|tell|explain|describe|how\s+(?:do|does|to|would|can|should)|what\s+(?:is|are|was|were|does|do)|why\s+(?:is|are|do|does)|can\s+(?:you|i|we))\s+(?:me|us|a|an|the|about)?\s*', '', clean)
            clean = re.sub(r'[?.!,;:]$', '', clean).strip()
            clean = re.sub(r'\s+(?:covering|including|featuring|focusing|specifically)\s+.*$', '', clean).strip()
            search_term = clean[:100]
        
        if search_term:
            # Faster: use search API snippet instead of summary (single API call)
            search_url = (
                'https://en.wikipedia.org/w/api.php?'
                'action=query&list=search&srwhat=text'
                '&srsearch=' + urllib.parse.quote(search_term) +
                '&srlimit=1&format=json'
            )
            req = Request(search_url, headers={
                'User-Agent': 'COS/1.0 (no-inference)'
            })
            with urlopen(req, timeout=8) as resp:
                result = _json.loads(resp.read().decode())
            
            search_results = result.get('query', {}).get('search', [])
            if search_results:
                # Use the SNIPPET from search results (much faster than a second API call)
                snippet = search_results[0].get('snippet', '')
                if snippet:
                    snippet = re.sub(r'<[^>]+>', '', snippet)
                    if not snippet.endswith(('.', '!', '?')):
                        snippet += '.'
                    return snippet[:800]
    except Exception:
        pass
    
    # Last resort — try the fast snippet approach
    try:
        from urllib.request import Request, urlopen
        import urllib.parse
        import json as _json
        
        clean = q.lower()
        clean = re.sub(r'^(?:what|why|how|when|where|who)\s+(?:is|are|was|were|do|does|did|a|an|the|i|we|you|they|he|she|it)\s+', '', clean)
        clean = re.sub(r'[?.!,;:\'\"()]+', '', clean).strip()
        words = [w for w in clean.split() if len(w) > 3 and w not in {'the', 'and', 'that', 'this', 'with', 'from', 'have', 'been', 'were', 'what', 'when', 'where', 'which', 'their', 'them', 'they', 'your', 'about', 'would', 'could', 'should', 'there', 'these', 'those', 'after', 'before', 'still', 'more', 'than', 'then', 'very', 'just', 'also'}]
        if words:
            search_term = ' '.join(words[:3])
            search_url = (
                'https://en.wikipedia.org/w/api.php?'
                'action=query&list=search&srwhat=text'
                '&srsearch=' + urllib.parse.quote(search_term) +
                '&srlimit=1&format=json'
            )
            req = Request(search_url, headers={'User-Agent': 'COS/1.0 (no-inference)'})
            with urlopen(req, timeout=5) as resp:
                result = _json.loads(resp.read().decode())
            results = result.get('query', {}).get('search', [])
            if results:
                snippet = results[0].get('snippet', '')
                if snippet:
                    snippet = re.sub(r'<[^>]+>', '', snippet)
                    if not snippet.endswith(('.', '!', '?')):
                        snippet += '.'
                    return snippet[:800]
    except Exception:
        pass
    
    # Ultra-last-resort: try harder to find Wikipedia content
    try:
        from urllib.request import Request, urlopen
        import urllib.parse
        import json as _json
        
        # Try different parts of the query
        words = [w for w in q.lower().split() if len(w) > 4 and w not in {
            'what', 'why', 'how', 'when', 'where', 'which', 'does', 'this',
            'that', 'with', 'from', 'they', 'have', 'been', 'about', 'tell',
            'just', 'also', 'still', 'even', 'only', 'more', 'some', 'like',
            'into', 'over', 'such', 'than', 'then', 'very', 'really', 'actually'
        }]
        if words:
            search_term = ' '.join(words[:2])
            search_url = (
                'https://en.wikipedia.org/w/api.php?'
                'action=query&list=search&srwhat=text'
                '&srsearch=' + urllib.parse.quote(search_term) +
                '&srlimit=1&format=json'
            )
            req = Request(search_url, headers={'User-Agent': 'COS/1.0 (no-inference)'})
            with urlopen(req, timeout=5) as resp:
                result = _json.loads(resp.read().decode())
            results = result.get('query', {}).get('search', [])
            if results:
                snippet = results[0].get('snippet', '')
                if snippet:
                    snippet = re.sub(r'<[^>]+>', '', snippet)
                    if not snippet.endswith(('.', '!', '?')):
                        snippet += '.'
                    return snippet[:600]
    except Exception:
        pass
    
    # Final message - direct and honest
    return "I do not have enough specific information about that topic to give you a thorough answer. Could you ask a more specific question or try a different topic?"
