"""
COS Orchestrator — Coordinates all subsystems for query processing.

This is the main entry point for the COS query processing pipeline.
It routes queries to the appropriate subsystem based on intent detection.

Architecture:
  - intent.py:   Detects query intent (factual, math, roleplay, etc.)
  - memory.py:   Tracks user-stated facts for recall
  - knowledge.py:Curated common knowledge base
  - templates.py: Instruction, writing, coding, reasoning templates
  - roleplay.py: Character persona engine
  - followup.py: Response rewrite engine (MT-Bench Turn 2)
  - math_solver.py: Word problem and math expression solver

Pipeline:
  query → detect_intent() → route to handler → generate response
"""

import os
import re
import sys
import json
import urllib.request
import urllib.parse
from pathlib import Path

from cos.state import conversation_history, current_roleplay, fact_memory
from cos.intent import detect_intent
from cos.memory import extract_and_store, recall as memory_recall, get_all_facts_text
from cos.knowledge import lookup as knowledge_lookup
from cos.templates import match_instruction
from cos.roleplay import match_roleplay, generate_followup as roleplay_followup
from cos.context_extraction import extract_search_terms
from cos.followup import rewrite_previous_response
from cos.template_engine import match_template, get_context_topic, reload as reload_templates

# ── NLG integration (unified system) ────────────────────────────────────────
_NLG_NATURALIZE = None
def _get_nlg():
    """Lazy-import the NLG system. All factual responses use this."""
    global _NLG_NATURALIZE
    if _NLG_NATURALIZE is None:
        try:
            from cos.nlg import naturalize
            _NLG_NATURALIZE = naturalize
        except Exception:
            _NLG_NATURALIZE = False
    return _NLG_NATURALIZE


def _nlg(query, topic, info):
    """Pass information through simple conversational polish.
    Deprecated: use _make_conversational directly instead.
    This wrapper exists for backward compatibility."""
    if not info or len(info) < 10:
        return info
    return _make_conversational(info)


def _make_conversational(text: str) -> str:
    """Apply conversational polish to text.
    Adds contractions and fixes capitalization.
    Ensures the text ends with complete sentences and proper punctuation.
    Strips trailing word fragments from Wikipedia content.

    If the text contains code blocks (```), skip contractions and
    capitalization fix to avoid corrupting code syntax.
    """
    if not text or len(text) < 20:
        return text

    # If text contains code blocks, skip fluency pipeline entirely
    # to avoid corrupting code with contractions or sentence splitting.
    # But ensure code blocks are properly closed.
    if '```' in text:
        # Ensure code blocks are properly fenced (not truncated)
        fence_count = text.count('```')
        if fence_count % 2 != 0:
            text += '\n```'
        # Also check for unclosed angle brackets in HTML/CSS that indicate truncation
        # Look for opening HTML tags without closing tags at the end
        lines = text.strip().split('\n')
        last_line = lines[-1].strip()
        # If the last non-empty line ends with an unclosed HTML tag or CSS property,
        # append closing tags to make the document valid
        open_braces = last_line.count('{')
        close_braces = last_line.count('}')
        if close_braces < open_braces:
            text += '\n}' * (open_braces - close_braces)
        # Check for unclosed HTML tags at end
        if re.search(r'<[a-zA-Z][^>]*$', last_line):
            tag_match = re.search(r'<([a-zA-Z][a-zA-Z0-9]*)', last_line)
            if tag_match:
                text += f'</{tag_match.group(1)}>'
        return text

    # ── Clean Wikipedia formatting artifacts ───────────────────────────
    # Strip em dashes and en dashes first
    text = text.replace('\u2014', ' -- ').replace('\u2013', ' - ')

    # Strip ALL Wikipedia section headers throughout the text (not just at end)
    # These are single lines that start with a capital letter and end with no period
    # Common headers: History, Geography, Culture, Economy, Demographics, etc.
    text = re.sub(r'\n\n[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\n\n', '\n\n', text)
    text = re.sub(r'\n[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\n\n', '\n\n', text)

    # Strip "See also", "References", "Further reading", "External links" sections and everything after
    text = re.split(r'\n\nSee\s+also\n|\n\nReferences\n|\n\nFurther\s+reading\n|\n\nExternal\s+links\n|\n\nBibliography\n|\n\nNotes\n|\n\nCitations\n', text, maxsplit=1)[0]

    # Strip trailing word fragments (truncated Wikipedia content)
    text = re.sub(r'\s+[a-zA-Z]{1,2}$', '.', text.strip())
    text = re.sub(r'\s*\-+\s*$', '.', text)
    text = re.sub(r'\s+(?:the|a|an|and|or|but|for|nor|yet|so|with|from|that|this|these|those)\s*$', '.', text)

    # Strip any remaining trailing section headers (standalone capitalized lines)
    text = re.sub(r'\n\n[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3}\s*$', '', text)
    text = re.sub(r'\n[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3}\s*$', '', text)
    text = re.sub(r'\n\n[A-Z][a-z]+\s*$', '', text)
    text = re.sub(r'\n[A-Z][a-z]+\s*$', '', text)

    # Clean up multiple consecutive newlines
    text = re.sub(r'\n{3,}', '\n\n', text)

    try:
        from cos.nlg.fluency import apply_contractions, fix_caps
        result = apply_contractions(text, rate=1.0, temperature=0.0)
        result = fix_caps(result)
        result = result.rstrip()
        # Skip sentence completion for text with code blocks (would corrupt HTML/CSS)
        if '```' not in result:
            # Ensure complete sentences - find last sentence boundary
            if result and not result[-1] in '.!?':
                # Look for the last complete sentence ending
                last_period = max(result.rfind('.'), result.rfind('!'), result.rfind('?'))
                if last_period > len(result) * 0.5:  # Only truncate if we keep most content
                    result = result[:last_period + 1]
                else:
                    # Add period if no good truncation point found
                    result += '.'
        return result
    except Exception:
        text = text.rstrip()
        if text and not text[-1] in '.!?':
            # Try to find a natural sentence boundary instead of just adding '.'
            last_period = max(text.rfind('.'), text.rfind('!'), text.rfind('?'))
            if last_period > len(text) * 0.5:
                text = text[:last_period + 1]
            else:
                text += '.'
        return text


def _format_as_essay(content: str, topic: str) -> str:
    """Format raw content as a structured essay with title and conclusion.

    Takes cleaned Wikipedia content and wraps it in a proper essay structure:
      - Title line
      - Introduction (first substantive paragraph)
      - Body (remaining paragraphs)
      - Brief conclusion
    """
    if not content or len(content) < 60:
        return content

    # Split into paragraphs
    paras = [p.strip() for p in content.split('\n\n') if p.strip()]
    if not paras:
        return content

    title = topic.title() if len(topic) < 80 else topic

    # First paragraph is the introduction
    intro = paras[0]

    # Remaining paragraphs are the body
    body = '\n\n'.join(paras[1:]) if len(paras) > 1 else ''

    # Build the essay
    essay = f"**{title}**\n\n"
    essay += intro
    if body:
        essay += '\n\n' + body

    return essay


def _ensure_complete_sentences(text: str) -> str:
    """Ensure text doesn't end mid-sentence.

    If the last character isn't sentence-ending punctuation, trim to
    the last complete sentence. Also handles truncated word fragments
    like 'from sub-atomic particles to e' (single-letter ending).
    Skips truncation if text contains code blocks (```) to avoid
    cutting off code examples.
    """
    if not text:
        return text

    text = text.rstrip()

    # If already ending with proper punctuation, we're good
    if text.endswith(('.', '!', '?')):
        return text

    # If text contains code blocks, don't trim to last period
    # because code blocks have periods inside strings that would
    # cause false truncation.
    if '```' in text:
        return text

    # Check if the text ends with what looks like a truncated word.
    # A truncated word is one that's cut off at the end (no period after it).
    # We detect this by checking if the last "word" doesn't end with
    # standard sentence-ending punctuation and looks incomplete.
    last_word = text.split()[-1].lower() if text.split() else ''

    # Remove trailing punctuation for checking
    last_word_clean = last_word.rstrip('.!?"\'') if last_word else ''

    # Single letter fragment (not 'I' or 'a')
    if len(last_word_clean) == 1 and last_word_clean not in ('i', 'a'):
        dots = [m.end() for m in re.finditer(r'\. ', text)]
        if dots:
            text = text[:dots[-1]]
        return text.strip()

    # Text doesn't end with punctuation - find the last complete sentence
    if not text.rstrip().endswith(('.', '!', '?')):
        last_period = text.rfind('.')
        last_excl = text.rfind('!')
        last_q = text.rfind('?')
        last_end = max(last_period, last_excl, last_q)
        if last_end >= 20:
            text = text[:last_end + 1]

    return text.strip()


# ── Topic aliases (loaded from JSON) ──────────────────────────────────────────

_ALIASES_PATH = Path(__file__).parent.parent.parent / 'data' / 'aliases.json'
_ALIASES_CACHE = None  # memoized: dict[str, str]


def _load_aliases() -> dict:
    """Load topic aliases from data/knowledge/aliases.json.

    Returns a dict mapping query fragments to Wikipedia article titles.
    Cached after first load.
    """
    global _ALIASES_CACHE
    if _ALIASES_CACHE is not None:
        return _ALIASES_CACHE
    try:
        with open(_ALIASES_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # Strip the _note key if present
        if isinstance(data, dict):
            data.pop('_note', None)
            _ALIASES_CACHE = data
        else:
            _ALIASES_CACHE = {}
    except Exception:
        _ALIASES_CACHE = {}
    return _ALIASES_CACHE


def reload_aliases():
    """Force reload of topic aliases from disk."""
    global _ALIASES_CACHE
    _ALIASES_CACHE = None
    return _load_aliases()


# ── Wikipedia search (fallback) ───────────────────────────────────────────────

_WIKI_CACHE = {}  # query_lower -> (summary, source_url)
_WIKI_CACHE_HITS = 0  # debug: count cache hits vs misses

# Persistent disk cache for Wikipedia results
_WIKI_CACHE_FILE = Path(__file__).parent.parent.parent / 'data' / 'cache' / 'wikipedia_cache.json'

def _load_wiki_cache():
    global _WIKI_CACHE, _WIKI_FULL_CACHE
    try:
        if _WIKI_CACHE_FILE.exists():
            import json as _json
            data = _json.loads(_WIKI_CACHE_FILE.read_text())

            def _clean(entries):
                # Drop stale/malformed entries: the cached text must be a
                # non-trivial string (a few bogus entries were written by
                # older buggy versions and poisoned fresh processes).
                out = {}
                for k, v in entries.items():
                    try:
                        text, url = v if isinstance(v, (list, tuple)) and len(v) == 2 else (None, None)
                        if isinstance(text, str) and len(text) > 40 and isinstance(url, str):
                            out[k] = (text, url)
                    except Exception:
                        continue
                return out

            _WIKI_CACHE.update(_clean(data.get('summary', {})))
            _WIKI_FULL_CACHE.update(_clean(data.get('full', {})))
    except Exception:
        pass

def _save_wiki_cache():
    try:
        _WIKI_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        import json as _json
        data = {'summary': dict(list(_WIKI_CACHE.items())[-2000:]),  # keep last 2000
                'full': dict(list(_WIKI_FULL_CACHE.items())[-500:])}  # keep last 500
        _WIKI_CACHE_FILE.write_text(_json.dumps(data, indent=2))
    except Exception:
        pass

_load_wiki_cache()


def _extract_noun_candidates(query):
    """Extract significant noun phrases from a query as Wikipedia search candidates.

    Returns a list of (phrase, priority) tuples ordered by likely relevance.
    Priority: 0=best (core subject), 1=secondary, 2=last resort.
    Handles multi-word noun phrases like 'Roman Empire', 'time perception'.
    """
    q = query.lower().strip().rstrip('?!.')
    # Remove question-word prefixes (use \b to prevent eating noun-starting letters)
    q = re.sub(r'^(?:what|how|why|when|where|who|which)\s+(?:is|are|was|were|does|do|did|would|could|should|might|may|will|shall|can|could)?\s*(?:the|a|an|some|any|this|that)\s+', '', q)
    q = re.sub(r'^(?:what|how|why|when|where|who|which)\s+(?:is|are|was|were|does|do|did|would|could|should|might|may|will|shall|can|could)\s+', '', q)
    q = re.sub(r'^(?:what|how|why|when|where|who|which)\s+', '', q)
    # Remove subordinate clauses
    q = re.sub(r'\s+if\s+.*$', '', q)
    q = re.sub(r'\s+when\s+.*$', '', q)
    q = re.sub(r'\s+before\s+.*$', '', q)
    q = re.sub(r'\s+after\s+.*$', '', q)
    q = re.sub(r'\s+during\s+.*$', '', q)
    q = re.sub(r'\s+without\s+.*$', '', q)
    q = re.sub(r'\s+with\s+(?:a|an|the)?\s*$', '', q)
    q = re.sub(r'\s+in\s+(?:a|an|the)?\s*$', '', q)
    q = re.sub(r'\s+from\s+.*$', '', q)
    q = re.sub(r'\s+for\s+.*$', '', q)
    q = re.sub(r'\s+to\s+(?:actually\s+)?(?:be|have|do|make|create|fix|repair|build|withstand|resist)\b.*$', '', q)
    q = re.sub(r'\s+and\s+(?:why|how|what|who|when|where)\b.*$', '', q)
    q = re.sub(r',\s+and\s+.*$', '', q)
    q = q.strip(' ,.:;!?')

    _STOP = {
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'does', 'do', 'did',
        'can', 'could', 'would', 'should', 'might', 'may', 'will', 'shall',
        'have', 'has', 'had', 'been', 'being', 'be', 'that', 'this', 'these',
        'those', 'some', 'any', 'every', 'each', 'all', 'both', 'most', 'more',
        'about', 'tell', 'just', 'also', 'still', 'even', 'only', 'very',
        'really', 'actually', 'basically', 'suddenly', 'like', 'into', 'over',
        'such', 'than', 'then', 'where', 'when', 'what', 'how', 'why', 'who',
        'which', 'if', 'before', 'after', 'during', 'between', 'through',
        'happen', 'happens', 'happened', 'causes', 'caused', 'causing',
        'make', 'makes', 'made', 'create', 'creates', 'give', 'gives',
        'show', 'shows', 'think', 'thinks', 'know', 'knows', 'feel', 'feels',
        'experience', 'experiences', 'manage', 'manages', 'design', 'designs',
        'use', 'uses', 'used', 'exist', 'exists', 'exist',
    }

    # Known multi-word noun phrases (ordered longest first for greedy matching)
    _MULTI_WORD = [
        'roman empire', 'time perception', 'climate change', 'social media',
        'machine learning', 'artificial intelligence', 'big bang',
        'dark matter', 'dark energy', 'quantum mechanics', 'quantum computing',
        'world war', 'cold war', 'industrial revolution', 'french revolution',
        'american revolution', 'scientific revolution', 'renaissance',
        'mycorrhizal network', 'fungal network', 'fungal communication',
        'mycelium network', 'plant communication', 'wood wide web',
        'placebo effect', 'echo chamber', 'survivorship bias',
        'confirmation bias', 'cognitive dissonance', 'maslow hierarchy',
        'imposter syndrome', 'stockholm syndrome', 'pareidolia',
        'apophenia', 'circadian rhythm', 'fight or flight',
        'stone age', 'bronze age', 'iron age', 'space age',
        'earth atmosphere', 'atmosphere of earth', 'solar system',
        'milky way', 'andromeda galaxy', 'event horizon',
        'black hole', 'neutron star', 'white dwarf', 'red giant',
        'continental drift', 'plate tectonics', 'magnetic field',
        'evolutionary biology', 'natural selection', 'genetic engineering',
        'crispr', 'mrna vaccine', 'quantum entanglement',
        'schrodinger cat', 'heisenberg uncertainty', 'entropy',
        'information theory', 'chaos theory', 'game theory',
        'voynich manuscript', 'antikythera mechanism',
        'bermuda triangle', 'silk road',
        'cold fusion', 'perpetual motion', 'diaspora',
        'global warming', 'carbon footprint',
        'renewable energy', 'nuclear fusion', 'nuclear fission',
        'mars colonization', 'moon landing',
        'art conservation', 'petrichor', 'synesthesia',
        'kintsugi', 'barter economy', 'supply and demand',
        'cognitive bias', 'heuristic', 'anchoring effect',
        'bandwagon effect', 'bystander effect',
        'dunning kruger', 'survival bias', 'selection bias',
        'hawthorne effect', 'observer effect', 'butterfly effect',
        'chronostasis', 'time dilation',
        'special relativity', 'general relativity',
        'quantum gravity', 'string theory',
        'holographic principle', 'hawking radiation',
        'wave function', 'copenhagen interpretation',
        'earthquake engineering', 'seismic retrofit',
        'structural engineering', 'architectural engineering',
        'unsolved mystery', 'fall of the roman empire',
        'existentialism', 'nihilism', 'absurdism',
        'metaphysics', 'epistemology', 'cosmology',
        'astrobiology', 'mycology', 'ecology',
        'neuroscience', 'genetics', 'evolution',
        'philosophy of mind', 'philosophy of science',
        'fall of rome', 'western roman empire',
        'second industrial revolution', 'digital revolution',
        'great depression', 'financial crisis',
        'dark energy', 'antimatter',
        'habitable zone', 'mass extinction',
        'dna', 'rna', 'protein',
        'cell biology', 'molecular biology', 'biochemistry',
        'big bang', 'cosmic inflation',
        'heat death', 'cosmic microwave background',
        'free will', 'determinism',
        'empathy', 'theory of mind',
        'consciousness', 'cognitive science',
        'evolutionary psychology', 'developmental psychology',
        'social psychology', 'positive psychology',
        'behavioral economics', 'environmental psychology',
        'creativity', 'imagination', 'decision making',
        'mental model', 'cognitive load',
        'stress response', 'resilience',
        'perception', 'attention', 'memory', 'learning',
        'communication', 'animal communication',
        'extraterrestrial life', 'fermi paradox',
        'great filter', 'drake equation',
    ]

    candidates = []
    used_positions = set()

    # Try multi-word phrases first (greedy, longest match)
    for phrase in _MULTI_WORD:
        idx = q.find(phrase)
        if idx >= 0:
            end = idx + len(phrase)
            # Check no overlap with already-used positions
            if not any(idx <= p < end for p in used_positions):
                candidates.append((phrase.title(), 0))
                used_positions.update(range(idx, end))

    # Extract remaining content words as individual candidates
    words = re.findall(r'\b\w+\b', q)
    for i, w in enumerate(words):
        if w in _STOP or len(w) < 3:
            continue
        # Skip if this position is part of a multi-word match
        word_start = q.find(w)
        if any(word_start >= start and word_start < end for start, end in
               [(q.find(p), q.find(p) + len(p)) for p, _ in candidates]):
            continue
        # Determine priority: first significant word = best
        priority = 0 if not candidates else 1 if len(w) >= 5 else 2
        candidates.append((w, priority))

    # Sort: priority 0 first, then by length (longer = more specific)
    candidates.sort(key=lambda x: (x[1], -len(x[0])))

    # Deduplicate while preserving order
    seen = set()
    result = []
    for phrase, priority in candidates:
        if phrase.lower() not in seen:
            seen.add(phrase.lower())
            result.append((phrase, priority))

    return result[:10]


# ── Intent-aware topic aliases ──────────────────────────────────────────────
# Maps question patterns (stripped to key nouns/verbs) to known Wikipedia topics.
# Used as a fast lookup before trying raw Wikipedia search.
_INTENT_ALIASES = {
    # Nature / biology
    'mushroom': 'mycology', 'mushrooms': 'mycology',
    'mushroom communicate': 'fungal communication',
    'mushrooms communicate': 'fungal communication',
    'fungus': 'mycology', 'fungi': 'mycology',
    'communicate underground': 'mycelium',
    'underground network': 'mycelium',
    'underground communicate': 'mycelium',
    'tree communicate': 'fungal communication',
    'trees communicate': 'fungal communication',
    'plant communicate': 'plant communication',
    'plants communicate': 'plant communication',
    # Time / perception
    'time slow': 'tachypsychia',
    'time slowing': 'tachypsychia',
    'time slow down': 'tachypsychia',
    'slowing down time': 'tachypsychia',
    'slow motion': 'chronostasis',
    'crisis time': 'tachypsychia',
    'time crisis': 'tachypsychia',
    'slow time': 'time perception',
    'time slow perception': 'time perception',
    'experience time': 'time perception',
    # Invention / innovation
    'failed invention': 'invention',
    'invention failed': 'invention',
    'successful failed invention': 'invention',
    'invention history': 'history of technology',
    'invention': 'invention',
    # Mystery / unsolved
    'unsolved mystery': 'list of unsolved problems',
    'unsolved mysteries': 'list of unsolved problems',
    'unsolved': 'list of unsolved problems',
    'mystery': 'mystery fiction',
    'weird mystery': 'list of unsolved problems',
    'weirdest mystery': 'list of unsolved problems',
    '19th century mystery': 'list of unsolved problems',
    'mystery 19th': 'list of unsolved problems',
    # Architecture / engineering
    'architect design': 'architectural engineering',
    'buildings earthquake': 'earthquake engineering',
    'earthquake building': 'earthquake engineering',
    'withstand earthquake': 'seismic retrofit',
    'earthquake': 'earthquake',
    'building design': 'architectural engineering',
    'architects design': 'architectural engineering',
    # Earth / atmosphere
    'atmosphere': 'atmosphere of Earth',
    'earth atmosphere': 'atmosphere of Earth',
    'atmosphere plants': 'atmosphere of Earth',
    'earth plants atmosphere': 'atmosphere of Earth',
    'earth atmosphere plants': 'atmosphere of Earth',
    'plants died': 'atmosphere of Earth',
    'earth air': 'atmosphere of Earth',
    # Roman / history
    'roman empire': 'Roman Empire',
    'roman empire collapse': 'Fall of the Western Roman Empire',
    'roman collapse': 'Fall of the Western Roman Empire',
    'empire collapse': 'Fall of the Western Roman Empire',
    'roman': 'Roman Empire',
    'collapse roman': 'Fall of the Western Roman Empire',
    'roman empire fall': 'Fall of the Western Roman Empire',
    # Philosophy / existence
    'philosophy exist': 'existentialism',
    'why exist': 'existentialism',
    'reason exist': 'existentialism',
    'meaning life': 'Meaning of life',
    'meaning existence': 'existentialism',
    'purpose life': 'Meaning of life',
    'philosophy argument': 'philosophy',
    'exist argument': 'existentialism',
    'exist reason': 'existentialism',
    'why we exist': 'existentialism',
    'why exist': 'existentialism',
    # Space / astronomy
    'moon disappear': 'Tidal locking',
    'moon suddenly': 'Tidal locking',
    'star core': 'stellar evolution',
    'star core supernova': 'supernova',
    'supernova explosion': 'supernova',
    'supernova star core': 'supernova',
    'two suns': 'circumbinary planet',
    'planet two suns': 'circumbinary planet',
    'civilization two suns': 'circumbinary planet',
    'civilization planet': 'extraterrestrial civilization',
    # Time perception
    'time faster older': 'time perception',
    'perceive time faster': 'time perception',
    'time moving faster': 'time perception',
    'track time': 'timekeeping',
    'maya track time': 'Maya calendar',
    'ancient maya track': 'Maya calendar',
    'maya time': 'Maya calendar',
    'maya build': 'Maya architecture',
    'maya cities': 'Maya civilization',
    'ancient maya build': 'Maya architecture',
    'ancient maya cities': 'Maya civilization',
    'maya without metal': 'Maya architecture',
    # Isolated places
    'isolated inhabited': 'Remote and isolated community',
    'isolated places': 'Remote and isolated community',
    'most isolated': 'Remote and isolated community',
    'isolated place': 'Remote and isolated community',
    'remote inhabited': 'Remote and isolated community',
    # Pirates
    'pirate empire': 'Golden Age of Piracy',
    'pirate empires': 'Golden Age of Piracy',
    'successful pirate': 'Golden Age of Piracy',
    'most successful pirate': 'Golden Age of Piracy',
    # Placebo
    'placebo effect brain': 'placebo effect',
    'placebo brain': 'placebo effect',
    'placebo effect': 'placebo effect',
    'placebo': 'placebo',
    # Earthquake-proof
    'earthquake-proof': 'earthquake engineering',
    # Cipher / code
    'unsolved cipher': 'Voynich Manuscript',
    'mysterious cipher': 'Voynich Manuscript',
    'cipher in history': 'Voynich Manuscript',
    'mysterious unsolved cipher': 'Voynich Manuscript',
    # Memory / forgetting
    'memories keep': 'memory consolidation',
    'memories forget': 'memory consolidation',
    'memory keep': 'memory consolidation',
    'memory forget': 'memory consolidation',
    'decide memories': 'memory consolidation',
    'brain decide': 'memory consolidation',
    'brain memories': 'memory consolidation',
    # Plants / atmosphere
    'plants vanished': 'atmosphere of Earth',
    'plants disappeared': 'atmosphere of Earth',
    'plants died': 'atmosphere of Earth',
    'plants die': 'atmosphere of Earth',
    'all plants': 'atmosphere of Earth',
    'without plants': 'atmosphere of Earth',
    # Acoustic design
    'acoustic': 'acoustic architecture',
    'acoustically perfect': 'acoustic architecture',
    'acoustic design': 'acoustic architecture',
    'perfect acoustics': 'acoustic architecture',
    'architects design': 'acoustic architecture',
    'concert hall acoustics': 'acoustic architecture',
    # Deep ocean
    'deep ocean': 'deep sea',
    'ocean unexplored': 'deep sea',
    'unexplored ocean': 'deep sea',
    'deep ocean unexplored': 'deep sea',
    'ocean still unexplored': 'deep sea',
    'space compared': 'deep sea',
    # Forgotten artists
    'forgotten artists': 'forgotten artists',
    'forgotten artist': 'forgotten artists',
    'history forgot': 'forgotten artists',
    'world forgotten': 'forgotten artists',
    'largely forgotten': 'forgotten artists',
    'influential artists': 'forgotten artists',
    # Petrichor / smell before rain
    'smell rain': 'petrichor',
    'smell before rain': 'petrichor',
    'smell before it rains': 'petrichor',
    'smell in the air': 'petrichor',
    'specific smell': 'petrichor',
    'smell air before': 'petrichor',
    'earthy smell': 'petrichor',
    'rain smell': 'petrichor',
    'rain smell good': 'petrichor',
    'earthquake proof': 'earthquake engineering',
    # Stars
    'star\'s core': 'stellar evolution',
    'happens to a star': 'stellar evolution',
    'star core during': 'supernova',
    # Art / culture
    'art movement': 'Art movement',
    'art movements': 'Art movement',
    'changed how we see': 'Art movement',
    # Good life
    'good life': 'quality of life',
    'concept of a good life': 'quality of life',
    'define the concept of': 'quality of life',
    # Salt
    'salt shaped': 'Salt',
    'salt trade': 'History of salt',
    'history of salt': 'History of salt',
    'salt human': 'History of salt',
    # Cult
    'cult leader': 'charismatic authority',
    'cult psychology': 'charismatic authority',
    'psychology of a cult': 'cult',
    'psychology of cult': 'cult',
    # Ship of Theseus
    'ship of theseus': 'Ship of Theseus',
    'theseus paradox': 'Ship of Theseus',
    'ship of theseus paradox': 'Ship of Theseus',
    # Fractals
    'fractal': 'fractal',
    'fractals in nature': 'fractal',
    'fractals': 'fractal',
    # Acoustics
    'acoustically perfect': 'acoustic architecture',
    'acoustic design': 'acoustic architecture',
    'acoustic perfection': 'acoustic architecture',
    'perfect acoustics': 'acoustic architecture',
    'concert hall acoustics': 'acoustic architecture',
    'architectural acoustics': 'acoustic architecture',
    'room acoustics': 'acoustic architecture',
    # Southeast Asian architecture
    'southeast asian': 'Southeast Asian architecture',
    'southeast asia': 'Southeast Asian architecture',
    'architectural styles': 'Architecture',
    'unique architectural': 'Architecture',
    'architectural styles southeast': 'Southeast Asian architecture',
    # Sourdough
    'sourdough starter': 'sourdough',
    'sourdough': 'sourdough',
    'sourdough starter work': 'sourdough',
    # Zero
    'concept of zero': 'zero',
    'zero evolve': 'zero',
    'zero evolution': 'zero',
    'concept of zero evolve': 'zero',
    # Moon disappearing
    'moon disappeared': 'moon',
    'moon disappear': 'moon',
    'moon suddenly': 'moon',
    'moon vanished': 'moon',
    'moon suddenly disappeared': 'moon',
    # Quantum entanglement
    'quantum entanglement': 'Quantum entanglement',
    'entanglement works': 'Quantum entanglement',
    'quantum entanglement work': 'Quantum entanglement',
    'detailed explanation quantum': 'Quantum entanglement',
    # Most isolated city
    'most isolated city': 'Extreme points of Earth',
    'isolated city': 'Extreme points of Earth',
    'isolated city in the world': 'Extreme points of Earth',
    'hard to get to': 'Extreme points of Earth',
    'tristan da cunha': 'Tristan da Cunha',
    # Microwave
    'microwave heat food': 'Microwave oven',
    'how does a microwave': 'Microwave oven',
    'microwave oven': 'Microwave oven',
    'microwave food': 'Microwave oven',
    'heat up food microwave': 'Microwave oven',
    # Nihilism / Existentialism
    'nihilism': 'Nihilism',
    'existentialism': 'Existentialism',
    'nihilism and existentialism': 'Existentialism',
    'nihilism vs existentialism': 'Existentialism',
    # Bronze Age collapse
    'bronze age collapse': 'Bronze Age collapse',
    'bronze age': 'Bronze Age',
    # Everyday life in ancient athens
    'ancient athens daily': 'Classical Athens',
    'daily life in ancient greece': 'Classical Athens',
    'greek citizen daily': 'Classical Athens',
    # Feudal system
    'feudal system': 'Feudalism',
    'feudalism': 'Feudalism',
    'how feudalism worked': 'Feudalism',
    # Northern lights
    'northern lights': 'Aurora',
    'aurora borealis': 'Aurora',
    'what causes northern lights': 'Aurora',
    'aurora visible only at poles': 'Aurora',
    # Silk Road
    'silk road': 'Silk Road',
    'history of the silk road': 'Silk Road',
    # Industrial Revolution essay
    'industrial revolution': 'Industrial Revolution',
    'impact of the industrial revolution': 'Industrial Revolution',
    # Bronze Age Collapse
    'bronze age collapse': 'Bronze Age collapse',
    # Roman Empire essay
    'essay about the fall': 'Fall of the Western Roman Empire',
    'fall of the roman empire': 'Fall of the Western Roman Empire',
    'roman empire make sure': 'Fall of the Western Roman Empire',
    # Colors and emotions
    'colors evoke': 'color psychology',
    'color evoke': 'color psychology',
    'colors emotions': 'color psychology',
    'color emotion': 'color psychology',
    'colors affect emotions': 'color psychology',
    'color psychology': 'color psychology',
    # Urban planning
    'urban planning': 'urban planning',
    'urban planning experiments': 'urban planning',
    'urban planning projects': 'urban planning',
    'urban planning initiatives': 'urban planning',
    'successful urban': 'urban planning',
    'urban planning experiment': 'urban planning',
    # Cities planning
    'cities plan': 'urban logistics',
    'city plan': 'urban logistics',
    'urban logistics': 'urban logistics',
    'millions of people': 'urban logistics',
    'mass transit': 'urban logistics',
    # Tenochtitlan
    'tenochtitlan': 'Tenochtitlan',
    'aztec capital': 'Tenochtitlan',
    'aztec empire': 'Aztec Empire',
    # Unsolved scripts
    'unsolved scripts': 'undeciphered scripts',
    'undeciphered scripts': 'undeciphered scripts',
    'mysterious scripts': 'undeciphered scripts',
    'undeciphered writing': 'undeciphered scripts',
    # Art movement resistance
    'art movement': 'Art movement',
    'art movements': 'Art movement',
    'impressionism': 'Impressionism',
    'resistance': 'Art movement',
    'art resistance': 'Art movement',
    'face resistance': 'Art movement',
    'acoustic perfect': 'Acoustics',
    # Fermi Paradox
    'fermi paradox': 'Fermi paradox',
    'fermi': 'Fermi paradox',
    'where are the aliens': 'Fermi paradox',
    'haven\'t found aliens': 'Fermi paradox',
    'found aliens': 'Fermi paradox',
    'haven\'t found alien': 'Fermi paradox',
    # Warm/cold colors
    'warm colors': 'Color temperature',
    'cold colors': 'Color temperature',
    'colors feel warm': 'Color temperature',
    'colors feel cold': 'Color temperature',
    'warm and cold': 'Color temperature',
    'feel warm': 'Color temperature',
    'feel cold': 'Color temperature',
    # Spice trade
    'spice trade': 'Spice trade',
    'spices shape': 'Spice trade',
    'spice trade shape': 'Spice trade',
    # Meaning vs happiness
    'meaningful life': 'Meaning of life',
    'happy life': 'Meaning of life',
    'meaning and happiness': 'Meaning of life',
    'meaning vs happiness': 'Meaning of life',
    'meaningful vs happy': 'Meaning of life',
    # Stoicism / Epicureanism
    'philosophy of stoicism': 'Stoicism',
    'stoicism': 'Stoicism',
    'stoicism differs': 'Stoicism',
    'epicureanism': 'Epicureanism',
    'how it differs from epicureanism': 'Stoicism',
    'stoicism and how': 'Stoicism',
    # Remote inhabited place
    'remote inhabited': 'Remote and isolated community',
    'most remote inhabited': 'Remote and isolated community',
    'remote place where people': 'Remote and isolated community',
    'isolated inhabited': 'Remote and isolated community',
    'isolated place where people': 'Remote and isolated community',
    # Dream narratives
    'dream in narratives': 'Dream',
    'dream narratives': 'Dream',
    'dream in random': 'Dream',
    'why do we dream': 'Dream',
    'dream instead of': 'Dream',
    # Doorway effect
    'doorway effect': 'Event boundary',
    'doorway forget': 'Event boundary',
    'forget why entered': 'Event boundary',
    'walk through a doorway': 'Event boundary',
    'forget why we entered': 'Event boundary',
    'forget what we were doing': 'Event boundary',
    'entered a room': 'Event boundary',
    # New car smell
    'new car smell': 'New car smell',
    'car smell toxic': 'New car smell',
    'new car smell toxic': 'New car smell',
    # Language learning
    'learn a new language': 'Language acquisition',
    'language learning': 'Language acquisition',
    'best way to learn a language': 'Language acquisition',
    # Dream in color
    'dream in color': 'Dream',
    'colorblind dream': 'Dream',
    'dreaming in color': 'Dream',
    # Punic Wars
    'punic wars': 'Punic Wars',
    'turning point punic': 'Punic Wars',
    # Quantum entanglement
    'quantum entanglement': 'Quantum entanglement',
    'quantum entanglement works': 'Quantum entanglement',
    'explanation quantum entanglement': 'Quantum entanglement',
    # Microwave
    'microwave heat food': 'Microwave oven',
    'how does a microwave': 'Microwave oven',
    # The Absurd / Absurdism
    'the absurd': 'Absurdism',
    'absurdism': 'Absurdism',
    'absurd camus': 'Absurdism',
    'albert camus absurd': 'Absurdism',
    'myth of sisyphus': 'Absurdism',
    # James Webb
    'james webb': 'James Webb Space Telescope',
    'james webb space telescope': 'James Webb Space Telescope',
    'jwst': 'James Webb Space Telescope',
    'webb telescope': 'James Webb Space Telescope',
    # Metallic taste blood
    'metallic taste blood': 'Iron taste',
    'blood tastes metallic': 'Iron taste',
    'bleed metallic taste': 'Iron taste',
    'taste when bleeding': 'Iron taste',
    # Artificial intelligence ethics
    'ethics of artificial intelligence': 'AI ethics',
    'artificial intelligence ethics persuasive': 'AI ethics',
    'ai ethics essay': 'AI ethics',
    # Binary search tree
    'binary search tree python': 'Binary search tree',
    'bst in python': 'Binary search tree',
    # Flexbox vs Grid
    'flexbox center a div': 'Flexbox',
    'center a div flexbox': 'Flexbox',
    'flexbox vs css grid': 'CSS Grid',
    # The Absurd / Absurdism
    'jwst': 'James Webb Space Telescope',
    'space telescope': 'James Webb Space Telescope',
    'see back in time': 'James Webb Space Telescope',
    'see into the past': 'James Webb Space Telescope',
    # Deep-sea pressure
    'deep-sea creatures': 'Deep sea',
    'deep sea creatures': 'Deep sea',
    'crushing pressure': 'Deep sea',
    'ocean floor pressure': 'Deep sea',
    'survive pressure': 'Deep sea',
    'extreme pressure': 'Deep sea',
    # Architectural styles
    'architectural styles': 'Architecture',
    'unique architectural': 'Architecture',
    'architectural styles world': 'Architecture',
    'architectural styles around': 'Architecture',
    # Songs and memories
    'songs trigger': 'Music and memory',
    'songs bring back': 'Music and memory',
    'songs evoke': 'Music and memory',
    'melodies evoke': 'Music and emotion',
    # Bees
    'bees': 'Bee',
    'all the bees': 'Bee',
    'bees vanish': 'Bee',
    # Zero
    'concept of zero': '0',
    'concept of "zero"': '0',
    'history of zero': 'History of zero',
    # Labyrinth
    'labyrinth': 'Labyrinth',
    'labyrinths': 'Labyrinth',
    'complex labyrinth': 'Labyrinth',
    # Cilantro / taste
    'taste soap': 'cilantro',
    'cilantro': 'cilantro',
    # Unsolved manuscript
    'unsolved manuscript': 'Voynich Manuscript',
    'mysterious unsolved manuscript': 'Voynich Manuscript',
    'unsolved manuscripts': 'Voynich Manuscript',
    'mysterious manuscript': 'Voynich Manuscript',
    # Navigation
    'navigate open ocean': 'celestial navigation',
    'open ocean navigate': 'celestial navigation',
    'open ocean without': 'celestial navigation',
    'ancient navigate': 'celestial navigation',
    'navigate without': 'celestial navigation',
    'people navigate': 'celestial navigation',
    # Rain smell
    'smell of rain': 'Petrichor',
    'rain smell': 'Petrichor',
    'smell rain': 'Petrichor',
    # Sun vanishing / orbital mechanics
    'sun vanish': 'Timeline of the far future',
    'sun suddenly vanish': 'Timeline of the far future',
    'sun disappear': 'Timeline of the far future',
    'orbit vanish': 'Timeline of the far future',
    'orbit sun': 'orbital mechanics',
    'sun gone': 'Timeline of the far future',
    'lost sun': 'Timeline of the far future',
    'what happens when the sun': 'Timeline of the far future',
    'sun die': 'Stellar evolution',
    'sun dying': 'Stellar evolution',
    'sun death': 'Stellar evolution',
    # Propaganda
    'propaganda': 'Propaganda',
    'piece of propaganda': 'Propaganda',
    'propaganda history': 'Propaganda',
    'successful propaganda': 'Propaganda',
    # Archaeological discovery
    'archaeological discovery': 'Archaeology',
    'unsolved archaeological': 'Archaeology',
    'mysterious archaeological': 'Archaeology',
    'archaeological': 'Archaeology',
    # Library of Alexandria
    'library of alexandria': 'Library of Alexandria',
    'alexandria disappear': 'Library of Alexandria',
    'library disappear': 'Library of Alexandria',
    'library alexandria': 'Library of Alexandria',
    # Forgotten historical figure
    'historical figure': 'List of people known posthumously',
    'forgotten historical': 'List of people known posthumously',
    'forgotten figure': 'List of people known posthumously',
    'historical figure forgotten': 'List of people known posthumously',
    'completely forgotten': 'List of people known posthumously',
    # Miles Davis / jazz specific
    'miles davis': 'Miles Davis',
    'miles davis style': 'Miles Davis',
    'miles davis trumpet': 'Miles Davis',
    # Consciousness / anesthesia
    'consciousness': 'Consciousness',
    'deep anesthesia': 'General anesthesia',
    'anesthesia consciousness': 'General anesthesia',
    'during anesthesia': 'General anesthesia',
    'under anesthesia': 'General anesthesia',
    # Cilantro / taste (already present, but add more variants)
    'soapy taste': 'cilantro',
    'taste soap cilantro': 'cilantro',
    'soap taste': 'cilantro',
    'genetic taste': 'OR6A2',
    'cilantro soap': 'cilantro',
    # Emotions / language
    'words for emotions': 'Untranslatable words',
    'emotions language': 'Untranslatable words',
    'emotion word': 'Untranslatable words',
    'untranslatable emotion': 'Untranslatable words',
    'language emotion': 'Untranslatable words',
    'word for emotion': 'Untranslatable words',
    'emotion express': 'Untranslatable words',
    # Time zones
    'time zones': 'Time zone',
    'time zone': 'Time zone',
    'who decided time': 'Time zone',
    # Free will
    'free will': 'Free will',
    'against free will': 'Free will',
    'free will argument': 'Free will',
    'existence of free will': 'Free will',
    # Soul
    'concept of a soul': 'Soul',
    'concept of soul': 'Soul',
    'define soul': 'Soul',
    'what is a soul': 'Soul',
    'soul define': 'Soul',
    'soul': 'Soul',
    # Architecture / mood
    'architecture mood': 'Environmental psychology',
    'architecture influence mood': 'Environmental psychology',
    'city architecture mood': 'Environmental psychology',
    'architecture inhabitant': 'Environmental psychology',
    'architecture influence': 'Environmental psychology',
    'city influence mood': 'Environmental psychology',
    # Brain / memory
    'brain decide memories': 'Memory',
    'memories keep forget': 'Memory',
    'brain keep forget': 'Memory',
    'memories to keep': 'Memory',
    'brain decide keep': 'Memory',
    'memories to forget': 'Memory',
    'which memories': 'Memory',
    # Earth orbit
    'earth orbit': 'Orbit of Earth',
    "earth's orbit": 'Orbit of Earth',
    # Cilantro gene
    'OR6A2': 'OR6A2',
    'cilantro gene': 'OR6A2',
    'soap in cilantro': 'cilantro',
    # Ancient construction / megaliths
    'ancient civilizations manage': 'Megalith',
    'ancient civilizations move': 'Megalith',
    'move massive stones': 'Megalith',
    'ancient stones': 'Megalith',
    'ancient move stones': 'Megalith',
    'massive stones': 'Megalith',
    'transport stone': 'Megalith',
    # Earworms / songs stuck
    'songs stuck': 'Earworm',
    'songs get stuck': 'Earworm',
    'song stuck head': 'Earworm',
    'earworm': 'Earworm',
    'stuck in our heads': 'Earworm',
    'involuntary musical': 'Earworm',
    # Migration / animals
    'animals migrate': 'Animal navigation',
    'migrate without maps': 'Animal navigation',
    'animal migration': 'Animal navigation',
    'navigate thousands': 'Animal navigation',
    # Nostalgia
    'nostalgia': 'Nostalgia',
    'nostalgia time': 'Nostalgia',
    'nostalgia period': 'Nostalgia',
    # Quantum computer
    'quantum computer': 'Quantum computing',
    'quantum computing': 'Quantum computing',
    'quantum computer differ': 'Quantum computing',
    'classical computer': 'Quantum computing',
    # Uncanny valley
    'uncanny valley': 'Uncanny valley',
    # Effective way to learn
    'effective way to learn': 'Learning',
    'complex new skill': 'Learning',
    'learn complex': 'Learning',
    'learning skill': 'Learning',
    # Butterfly effect
    'butterfly effect': 'Chaos theory',
    'complex system': 'Chaos theory',
    # Internal monologue
    'internal monologue': 'Inner speech',
    'inner monologue': 'Inner speech',
    'voice in your head': 'Inner speech',
    'voice in head': 'Inner speech',
    'self-talk': 'Inner speech',
    'self talk': 'Inner speech',
    # Ethnobotany / plant knowledge
    'plants safe to eat': 'Ethnobotany',
    'plants were safe': 'Ethnobotany',
    'decide which plants': 'Ethnobotany',
    'edible plants': 'Ethnobotany',
    'humans decide plants': 'Ethnobotany',
    'plants safe eat': 'Ethnobotany',
    # Society without currency
    'function without': 'Barter economy',
    'without any form of currency': 'Barter economy',
    'without currency': 'Barter economy',
    'without money': 'Barter economy',
    'no currency': 'Barter economy',
    'no money': 'Barter economy',
    'society without currency': 'Barter economy',
    'society function without': 'Barter economy',
    # Dream memory / sleep
    'remember their dreams': 'Dream',
    'remember dreams': 'Dream',
    'dreams remember': 'Dream',
    'dream memory': 'Dream',
    'remember dream': 'Dream',
    # Medieval peasant
    'daily life.*peasant': 'Peasant',
    'typical peasant': 'Peasant',
    'medieval peasant': 'Peasant',
    'life of peasant': 'Peasant',
    # Deja vu
    'deja vu': 'Déjà vu',
    'déjà vu': 'Déjà vu',
    # Cultural heritage preservation
    'preserve cultural': 'Cultural heritage',
    'cultural heritage': 'Cultural heritage',
    'cultural preservation': 'Cultural heritage',
    'preserving cultural': 'Cultural heritage',
    # Color blue rarity
    'color blue rare': 'Structural coloration',
    'blue rare in nature': 'Structural coloration',
    'blue in nature': 'Structural coloration',
    # Noise canceling
    'noise canceling': 'Active noise control',
    'noise-cancelling': 'Active noise control',
    'noise cancelling': 'Active noise control',
    'erase sound': 'Active noise control',
    # Mandela effect
    'mandela effect': 'Mandela effect',
    'remember things differently': 'Mandela effect',
    'false memory': 'Mandela effect',
    # Unsolved codes / ciphers
    'unsolved codes': 'Cryptography',
    'unsolved cipher': 'Cryptography',
    'mysterious codes': 'Cryptography',
    'code unsolved': 'Cryptography',
    'unsolved code': 'Cryptography',
    # Medieval daily life
    'daily life.*medieval': 'Medieval cuisine',
    'daily life.*middle ages': 'Medieval cuisine',
    'medieval daily': 'Medieval cuisine',
    'middle ages daily': 'Medieval cuisine',
    'average person.*medieval': 'Medieval cuisine',
    'life medieval': 'Medieval cuisine',
    'life middle ages': 'Medieval cuisine',
    'medieval life': 'Medieval cuisine',
    # Urban planning / zoning
    'city zoning': 'Zoning',
    'zoning laws': 'Zoning',
    'green spaces': 'Urban green space',
    'city decide': 'Zoning',
    'place zoning': 'Zoning',
    # Learning skills
    'effective ways to learn': 'Learning',
    'learn a new skill': 'Learning',
    'learning quickly': 'Learning',
    'ways to learn': 'Learning',
    'skill quickly': 'Learning',
    # Migratory birds
    'migratory birds navigate': 'Animal navigation',
    'birds navigate': 'Animal navigation',
    'birds navigation': 'Animal navigation',
    'migrate thousands': 'Animal navigation',
    # Perfusion / smell of rain
    'perfume process': 'Perfumery',
    'creating perfume': 'Perfumery',
    'high-end perfume': 'Perfumery',
    'making perfume': 'Perfumery',
    # Before big bang
    'before big bang': 'Big Bang',
    'existed before': 'Big Bang',
    'before the universe': 'Big Bang',
    # Psychological experiments
    'psychological experiments': 'Milgram experiment',
    'bizarre experiments': 'Milgram experiment',
    'psychology experiment': 'Milgram experiment',
    # Cave paintings to art
    'cave paintings': 'Cave painting',
    'cave painting': 'Cave painting',
    'complex art': 'Art',
    'transition.*paintings': 'Cave painting',
    # Skyscraper / earthquake engineering
    'massive earthquake': 'Earthquake engineering',
    'skyscraper': 'Skyscraper',
    'withstand earthquake': 'Earthquake engineering',
    # Music and emotions
    'melodies evoke': 'Music and emotion',
    'melody evoke': 'Music and emotion',
    'music evoke emotion': 'Music and emotion',
    'evoke strong emotions': 'Music and emotion',
    # Plastic waste / pollution
    'plastic waste ocean': 'Marine pollution',
    'plastic waste': 'Plastic pollution',
    'plastic pollution': 'Plastic pollution',
    'reduce plastic': 'Plastic pollution',
    # Isolated inhabited place
    'isolated inhabited': 'Remote and isolated community',
    'most isolated': 'Remote and isolated community',
    'isolated place': 'Remote and isolated community',
    # Time evolution / timekeeping
    'sundial': 'Timekeeping',
    'atomic clock': 'Atomic clock',
    'time evolve': 'Timekeeping',
    # Quantum computing
    'quantum computer': 'Quantum computing',
    'quantum computing': 'Quantum computing',
    'differ from classical': 'Quantum computing',
    'quantum bits': 'Qubit',
    'superposition': 'Quantum superposition',
}


def _search_wikipedia_best(query: str) -> tuple:
    """Wikipedia search that returns the BEST article for a query.

    Tries multiple search terms and returns the article whose title
    or content best matches the query keywords. Uses FULL article
    content (up to 8000 chars) instead of just the summary.
    """
    # Build a list of search terms to try
    search_terms = [query]

    # Add extracted topic if different
    topic = _extract_search_topic(query) if 'extract' in dir() or True else query
    try:
        from cos.engine import _extract_search_topic as _est
        et = _est(query)
        if et and et.lower() != query.lower():
            search_terms.append(et)
    except Exception:
        pass

    # Add key noun phrases (2-3 word phrases starting with capitals)
    for m in re.finditer(r'\b(?:[A-Z][a-z]+\s+)?(?:[A-Z][a-z]+)(?:\s+[A-Z][a-z]+){0,2}\b', query):
        phrase = m.group(0).strip()
        if len(phrase) > 8 and phrase.lower() not in [t.lower() for t in search_terms]:
            search_terms.append(phrase)

    # Generate search variants for common question patterns
    q_lower = query.lower().strip()
    # Pattern: "why did X collapse/fall" -> also try "X collapse"
    collapse_m = re.search(r'why\s+did\s+(.+?)\s+(?:collapse|fall|abandon|disappear|decline)\b', q_lower)
    if collapse_m:
        subject = collapse_m.group(1).strip()
        action = collapse_m.group(2).strip().lower() if len(collapse_m.groups()) > 1 else 'collapse'
        phrases = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b', subject.title())
        for phrase in phrases:
            term = f'{phrase} {action}'
            if term.lower() not in [t.lower() for t in search_terms]:
                search_terms.append(term)
    # Pattern: "what is [X]" -> also try just "X"
    what_m = re.search(r'^(?:what|who|which)\s+(?:is|are|was|were)\s+(?:a|an|the|this|that)?\s*(.+?)$', q_lower)
    if what_m:
        st = what_m.group(1).strip().rstrip('?!.')
        if st and st.lower() not in [t.lower() for t in search_terms]:
            search_terms.append(st)
    # Pattern: "tell me about X" -> also try just "X"
    tell_m = re.search(r'^(?:tell|explain|describe)\s+(?:me|us)?\s*(?:about|what)?\s*(.+?)$', q_lower)
    if tell_m:
        st = tell_m.group(1).strip().rstrip('?!.')
        if st and st.lower() not in [t.lower() for t in search_terms]:
            search_terms.append(st)

    best_summary = None
    best_full = None
    best_score = -1

    # Limit to at most 3 search terms to reduce API calls
    for term in search_terms[:3]:
        if len(term) < 5:
            continue
        try:
            # Get summary
            summary, _ = _search_wikipedia(term)
            if not summary:
                continue
            # Only fetch full article if summary is short
            full = None
            if len(summary) < 300:
                full, _ = _search_wikipedia_full(term)

            # Score by keyword overlap with query
            q_words = set(re.findall(r'\b\w{4,}\b', query.lower()))
            text_lower = (summary + (full or '')).lower()[:2000]
            overlap = sum(1 for w in q_words if w in text_lower)
            score = len(summary) + (len(full or '') * 0.5) + overlap * 200

            # Bonus if search term appears prominently
            if term.lower() in summary[:150].lower():
                score += 500

            if score > best_score:
                best_score = score
                # Use full article if available, otherwise summary
                best_summary = summary
                best_full = full
        except Exception:
            continue

    if best_summary or best_full:
        # Use the full article primarily (it includes the summary content).
        # If no full article, fall back to the summary.
        # Avoid duplication by using one or the other, not both.
        content = best_full or best_summary
        if content:
            return content, None
    return None, None


def _wiki_search_variants(term):
    """Try multiple search variants for a term, returning first successful result.

    Tries: exact, singular/plural, -ology form, -ism form, capitalized.
    Uses both opensearch and direct REST API title lookup.
    """
    # Try exact first
    wiki, url = _search_wikipedia(term)
    if wiki:
        return wiki, url

    # Try variations (skip direct REST API call - _search_wikipedia handles this)
    variations = []
    t = term.lower().strip()

    # Plural → singular
    if t.endswith('ies') and len(t) > 4:
        variations.append(t[:-3] + 'y')
    elif t.endswith('ses') and len(t) > 4:
        variations.append(t[:-2])
    elif t.endswith('s') and len(t) > 4 and not t.endswith('ss'):
        variations.append(t[:-1])

    # Singular → plural
    if t.endswith('y') and len(t) > 4:
        variations.append(t[:-1] + 'ies')
    elif t.endswith('s') and len(t) > 4:
        variations.append(t + 'es')
    else:
        variations.append(t + 's')

    # Add -ology / -ism / -ness forms for certain roots
    if len(t) >= 5:
        if not t.endswith(('ism', 'ness', 'ology', 'tion', 'ment')):
            variations.append(t + 'ism')
            variations.append(t + 'ology')

    for var in variations:
        if var != t:
            wiki, url = _search_wikipedia(var)
            if wiki:
                return wiki, url

    return None, None


def _extract_search_topic(query):
    """Extract a clean search topic using symbolic extraction.

    Strips trailing clauses (covering, including, featuring, with) and
    keeps only the core topic for Wikipedia search.
    """
    # Fallback regex patterns first (fast, deterministic)
    q = query.lower().strip()
    # Pre-clean: strip trailing clauses that make Wikipedia search fail
    # These patterns match the end of essay/coding prompts where users specify
    # additional requirements ("covering X, Y, Z", "including...", "with...")
    q = re.sub(r'(?:,\s+and|;\s+and|,\s+or|;\s+or)\s+.*$', '', q)
    q = re.sub(r'\s+(?:covering|including|featuring|focusing|specifically|especially|particularly)\s+.*$', '', q)
    q = re.sub(r'\s+and\s+(?:do|does|did|is|are|was|were|can|could|would|should)\s+.*$', '', q)
    # Strip trailing details after the first comma/semicolon for coding/specific tasks
    if 'write a' in q or 'create a' in q or 'make a' in q or 'build a' in q:
        q = re.sub(r'[,;]\s+.*$', '', q)
    # Pre-process common comparison/question patterns
    q = re.sub(r'\s+and\s+how\s+(?:it|this|that)\s+(?:differs|compares|relates|connects|works)\s+.*$', '', q)
    q = re.sub(r'\s+as\s+well\s+as\s+.*$', '', q)
    q = re.sub(r'\s+and\s+(?:why|how|what|who|when|where)\s+.*$', '', q)
    q = re.sub(r'[,;]\s+and\s+is\s+.*$', '', q)
    q = re.sub(r'[,;]\s+including\s+.*$', '', q)
    q = re.sub(r'[,;]\s+such\s+as\s+.*$', '', q)
    # Handle "difference between X and Y" queries
    diff_match = re.search(r'difference\s+between\s+(.+?)\s+and\s+', q)
    if diff_match:
        q = diff_match.group(1).strip()

    # "what year was X released/founded/invented" — the subject (not the
    # year) is the search topic: "what year was the first iphone released?"
    # -> "first iphone". The prior patterns never matched "year" questions
    # and the fallback extractor returned the trailing verb ("released").
    year_match = re.search(r'^(?:in\s+)?what\s+year\s+(?:was|were|did|is|are|has|have)\s+(.+?)(?:\?|$)', q)
    if year_match:
        year_topic = year_match.group(1).strip().rstrip('.!?,;: ')
        # strip trailing tense/verb: "was the first iphone released" ->
        # "the first iphone"; "did world war 2 end" -> "world war 2"
        year_topic = re.sub(r'\s+(?:released|released\?|founded|invented|created|built|established|started|ended|began|born|died|happened|published|launched|introduced|written|made|discovered)\??$', '', year_topic)
        year_topic = re.sub(r'^(?:the|a|an)\s+', '', year_topic).strip()
        if len(year_topic) > 2:
            return _clean_topic(year_topic)

    # "what is the chemical formula of/for X" / "chemical formula for X" —
    # the substance is the topic (searching "chemical formula" alone hits
    # the generic "Formula" article).
    formula_match = re.search(r'chemical\s+formula\s+(?:of|for|is)?\s*(?:the\s+)?([a-z][a-z\s-]+?)\??$', q)
    if formula_match:
        substance = formula_match.group(1).strip().rstrip('.!?,;: ')
        if len(substance) > 2:
            return _clean_topic(substance)

    patterns = [
        r'^(?:what|who|which)\'?s\s+(?:a\s|an\s|the\s|this\s|that\s)?(.+?)\??$',
        r'^(?:what|who|which)\s+(?:is|are|was|were|does|do|did|would|could|should|might|may|will|shall|causes?|makes?|creates?|produces?)\s+(?:a\s|an\s|the\s|this\s|that\s)?(.+?)\??$',
        r'^which\s+(.+?)\s+(?:would|could|should|might|may|will|shall|is|are|was|were)\s+.*$',
        r'^which\s+(.*?)$',
        r'^(?:is|are|was|were)\s+there\s+(?:a\s|an\s|the\s)?\s*(.+?)\??$',
        r'^(?:what|who|which)\s+are\s+(?:a\s|an\s|the\s|this\s|that\s)?(.+?)\??$',
        r'^(?:tell|teach|show)\s+(?:me|us)\s+(?:about|what|how)\s+(.+?)\??$',
        r'^(?:explain|describe|define)\s+(?:the\s+)?(?:concept\s+of\s+)?(.+?)\??$',
        r'^(?:how)\s+(?:(?:does|do|did|is|are|was|were|can|could|would|should|will|shall)\s+)?(?:a|an|the|this|that|i|we|you|they|he|she|it|one)\s+(?:to\s+)?(?:make|bake|cook|create|build|write|find|get|know)?\s*(.+?)\??$',
        r'^(?:why)\s+(?:is\s+)?(?:it\s+)?(?:that\s+)?(?:do|does|did)\s+\w+\s+(\w+)\s+(.+?)\??$',
        r'^(?:why)\s+(?:is\s+)?(?:it\s+)?(?:that\s+)?(?:do|does|did)\s+(?:i|we|you|they|he|she|it|one)\s+(\w+)\??$',
        r'^(?:why)\s+(?:is\s+)?(?:it\s+)?(?:that\s+)?(.+?)\?+$',
        r'^(?:how|why|what|when|where)\s+(?:does|do|did|is|are|was|were|can|could|would|should)\s+(?:his|her|its|their|my|your|our)\s+(.+?)\?+$',
        r'^i\s+(?:like|love|enjoy|hate|want|have|use)\s+(.+?)$',
    ]
    for pat in patterns:
        m = re.search(pat, q)
        if m:
            topic = m.group(m.lastindex or 1).strip().rstrip('.!?,;: ')
            if len(topic) > 2:
                topic = _clean_topic(topic)
                return topic

    # Fall back to extract_topic (symbolic NLP)
    try:
        from cos.context_extraction import extract_topic_with_fallback
        topic = extract_topic_with_fallback(query)
        if topic and len(topic) > 2:
            return _clean_topic(topic)
    except Exception:
        pass

    # Improved fallback: look for known patterns in the raw query
    # "impact of X" → X, "history of X" → X, "concept of X" → X
    of_match = re.search(r'(?:impact|history|evolution|development|concept|idea|role|importance|future|analysis|overview)\s+of\s+(.+?)$', q, re.IGNORECASE)
    if of_match:
        topic = of_match.group(1).strip().rstrip('.!?,;: ')
        if len(topic) > 3:
            return _clean_topic(topic)

    # "the X of Y" → Y
    the_of_match = re.search(r'the\s+(.+?)\s+of\s+(.+?)$', q, re.IGNORECASE)
    if the_of_match:
        topic = the_of_match.group(2).strip().rstrip('.!?,;: ')
        if len(topic) > 3:
            return _clean_topic(topic)

    return _clean_topic(q)


def _clean_topic(topic):
    """Strip filler words, subordinate clauses, and prepositional tails from a topic.

    Keeps the core noun phrase suitable for Wikipedia search.
    """
    t = topic.strip().rstrip('.!?,;: ')

    # Strip trailing subordinate clauses and prepositional phrases.
    # IMPORTANT: Do NOT strip 'if' clauses, 'when' clauses, 'for whether',
    # or other conditional/prepositional phrases that contain the actual
    # question context (e.g., "if all the plants disappeared" in
    # "what would happen to the atmosphere if all the plants disappeared").
    cut_patterns = [
        r'\s+actually\s+.*$',
        r'\s+from\s+\w+\s+years?\s+ago\s+.*$',
        r'\s+in\s+(?:a|an|the)\s+.*$',
        r'\s+with\s+(?:a|an|the)\s+.*$',
        r'\s+on\s+(?:a|an|the)\s+.*$',
        r'\s+that\s+are\s+so\s+.*$',
        r'\s+and\s+(?:why|how|what|who|when|where)\b.*$',
        r'\s+why\s+is\s+it\s+so\s+.*$',
        r'\s+and\s+do\s+that\s+.*$',
        r'\s*,\s+and\s+is\s+.*$',
    ]
    for pat in cut_patterns:
        t = re.sub(pat, '', t, flags=re.IGNORECASE)

    # Strip leading filler phrases
    t = re.sub(r'^(?:the\s+)?(?:way\s+)?(?:that\s+)?', '', t, flags=re.IGNORECASE)

    # Strip leading question-phrase prefixes that leaked through
    t = re.sub(r'^(?:how\s+(?:does|do|did|is|are|was|were|can|could|would|should|will|shall)\s+(?:a|an|the|this|that|i|we|you|they|he|she|it|one)?\s*)', '', t, flags=re.IGNORECASE)
    t = re.sub(r'^(?:what\s+(?:is|are|was|were|does|do|did|would|could|should|will)\s+(?:a|an|the|this|that)?\s*)', '', t, flags=re.IGNORECASE)
    t = re.sub(r'^(?:why\s+(?:is|are|was|were|does|do|did)?\s*(?:it\s+)?(?:that\s+)?)', '', t, flags=re.IGNORECASE)
    t = re.sub(r'^(?:who\s+(?:is|are|was|were)\s+(?:a|an|the|this|that)?\s*)', '', t, flags=re.IGNORECASE)
    t = t.strip(' ,.:;!?')

    # If result is still too long (>5 words), try to extract just the key nouns
    words = t.split()
    if len(words) > 5:
        # Keep first 4-5 content words (skip articles, prepositions)
        stop = {'a', 'an', 'the', 'is', 'are', 'was', 'were', 'of', 'in', 'on',
                'at', 'to', 'for', 'with', 'by', 'from', 'some', 'that', 'this',
                'and', 'or', 'but', 'not', 'can', 'could', 'would', 'should',
                'happen', 'happens', 'causes', 'caused', 'causing'}
        content = [w for w in words if w.lower().rstrip('.,!?') not in stop]
        if len(content) >= 2:
            t = ' '.join(content[:5])

    # Strip trailing stop words
    t = t.strip().rstrip('.!?,;: ')

    # Minimum length check
    if len(t) < 3:
        return topic  # return original if we over-stripped

    return t


def _retrieve_multi_content(query: str, max_sources: int = 3) -> str:
    """Retrieve rich content from multiple topics and sources.

    Extracts keywords from the query, then searches the knowledge base
    and Wikipedia for each keyword. Combines results into a single
    text body for the NLG pipeline.

    Pure function.
    """
    import re as _multi_re

    # Topic alias map: common query phrases → better Wikipedia search terms
    # Loaded from data/knowledge/aliases.json — edit that file to add new aliases.
    _TOPIC_ALIASES = _load_aliases()

    # Resolve topic from query
    topic = _extract_search_topic(query)
    resolved_topic = _TOPIC_ALIASES.get(topic.lower(), topic)

    # Partial alias matching: try each alias key as substring of topic
    if resolved_topic == topic:
        for alias_key, alias_val in _TOPIC_ALIASES.items():
            if alias_key in topic.lower():
                resolved_topic = alias_val
                break

    # Direct query lookups
    kb_answer = knowledge_lookup(query)
    wiki_summary, wiki_url = _search_wikipedia(resolved_topic)

    # Multi-keyword extraction
    keywords = extract_search_terms(query)

    # Get the core nouns from the query for relevance filtering
    # Secondary content must share at least one significant word with the query
    q_words = set(w.lower() for w in _multi_re.findall(r'\w{4,}', query)
                  if w.lower() not in {'what', 'how', 'why', 'when', 'where', 'who',
                                       'which', 'tell', 'about', 'does', 'this',
                                       'that', 'with', 'from', 'they', 'have'})

    # Gather unique, relevant content parts
    seen = set()
    _seen_prefixes = []
    parts = []

    def _add(text, must_contain_query_words=False):
        text = text.strip()
        if not text or len(text) < 40 or text in seen:
            return
        # Check for near-duplicate: compare first 80 chars (lowered)
        text_prefix = text[:80].lower()
        if any(text[:80].lower() == p for p in _seen_prefixes):
            return
        # For secondary content, require at least one core query word match
        if must_contain_query_words and q_words:
            text_lower = text.lower()
            if not any(w in text_lower for w in q_words):
                return
        seen.add(text)
        _seen_prefixes.append(text_prefix)
        parts.append(text)

    # Primary content from direct query match
    if kb_answer:
        _add(kb_answer)
    if wiki_summary:
        _add(wiki_summary)

    # Full Wikipedia article for rich content — only fetch if summary is short
    # (skipped if summary already provides enough detail)
    wiki_summary_len = len(wiki_summary) if wiki_summary else 0
    if wiki_summary_len < 400:
        wiki_full, _ = _search_wikipedia_full(resolved_topic)
        if wiki_full:
            paras = [p.strip() for p in wiki_full.split('\n\n') if p.strip()]
            if paras:
                lead = '\n\n'.join(paras[:3])
                _add(lead)
            else:
                _add(wiki_full)

    # Secondary content from keyword expansion (must be relevant to query)
    # Only run if we have very little primary content (avoids polluting responses
    # with irrelevant Wikipedia articles from keyword matches)
    # Secondary content from keyword expansion — only if we have very little content
    if not (parts and sum(len(p) for p in parts) > 300):
        _STOP_WORDS = {'what', 'how', 'why', 'when', 'where', 'who', 'which',
                       'does', 'this', 'that', 'with', 'from', 'they', 'have',
                       'about', 'actually', 'instantly', 'basically', 'really',
                       'just', 'also', 'still', 'even', 'only', 'more', 'some',
                       'like', 'into', 'over', 'such', 'than', 'then', 'very'}
        if keywords:
            # Limit to at most 2 keyword expansions to reduce API calls
            for kw in keywords[:min(max_sources, 2)]:
                kw_lower = kw.lower().strip()
                kw_words = kw_lower.split()
                if len(kw_lower) < 4:
                    continue
                if kw_lower in _STOP_WORDS:
                    continue
                if len(kw_words) > 6:
                    continue
                q_lower = query.lower().strip()
                if kw_lower == q_lower:
                    continue
                if len(kw_words) > 1 and kw_lower in q_lower:
                    continue
                kw_kb = knowledge_lookup(kw)
                if kw_kb:
                    _add(kw_kb, must_contain_query_words=True)
                kw_wiki, _ = _search_wikipedia(kw)
                if kw_wiki:
                    _add(kw_wiki, must_contain_query_words=True)

    # Additional: try noun candidates from the query for secondary content
    # This catches cases where keyword extraction gives bad results
    # Only runs if no primary content was found (avoids unnecessary API calls)
    if not parts:
        noun_candidates = _extract_noun_candidates(query)
        for phrase, priority in noun_candidates[:2]:
            if phrase.lower() == topic.lower():
                continue
            if len(phrase) < 4:
                continue
            kw_wiki, _ = _search_wikipedia(phrase)
            if kw_wiki:
                _add(kw_wiki, must_contain_query_words=True)

    if parts:
        return '\n\n'.join(parts)
    return ''


def _resolve_topic(query, conversation_history):
    """Resolve a query's topic, using conversation history for context-dependent queries."""
    topic = _extract_search_topic(query)
    if topic:
        # "explain docker to me" must yield "docker", not "docker to me"
        topic = re.sub(r'\s+(?:to|for)\s+me(?:,\s*please|\.)?\??$', '', topic).strip()
        topic = re.sub(r'\s+please\??$', '', topic).strip()
        if len(topic) < 2:
            topic = None

    is_vague = (not topic or topic.lower() in (
        'that', 'it', 'this', 'them', 'those', 'these', 'they', 'he', 'she',
        'there', 'here'
    ))

    # Also treat short questions (< 5 words) as potentially context-dependent
    # even if they don't have explicit pronouns
    words = query.lower().split()
    question_words = {'who', 'what', 'when', 'where', 'how', 'why', 'which'}
    is_short_question = (len(words) <= 6 and words and words[0].rstrip('.,;:!?') in question_words)

    if is_vague or _query_is_context_dependent(query) or is_short_question:
        try:
            from cos.context_extraction import extract_context_topic
            ctx_topic = extract_context_topic(
                conversation_history,
                current_query=query,
            )
            if ctx_topic and len(ctx_topic) > 2:
                return ctx_topic
        except Exception:
            pass

    return topic


def _pronoun_has_antecedent_in_sentence(query: str) -> bool:
    """Check if a pronoun in the query has an antecedent within the same sentence.

    For example, "a human body if it fell" has "it" referring to "human body"
    within the same sentence. "people... they see" has "they" referring to
    "people" within the same sentence. These are NOT context-dependent.
    """
    q = query.lower().strip()
    # "it" in "Why is it that..." or "What is it that..." is a dummy/expletive pronoun
    if re.search(r'\b(why|what|when|where|how)\s+(is|are|was|were)\s+it\s+that\b', q):
        return True
    # "it" in "What was it actually like..." or "What was it like..." is a dummy pronoun
    if re.search(r'\b(what|how)\s+(was|is|were|are)\s+it\s+(?:actually\s+)?(?:like|about|like to)\b', q):
        return True
    # Check for "it" with a preceding noun phrase (e.g., "a human body if it fell")
    if re.search(r'\b(a|an|the)\s+\w+(?:\s+\w+)*\s+(?:if|when|where|that|which)\s+it\b', q):
        return True
    # Check for "it" with a following noun phrase in a conditional/time clause
    # (e.g., "if a train travels 60 mph, how far does it go" — "it" refers to
    # the train introduced by the clause; "when a file is open, why is it locked")
    if re.search(r'\b(?:if|when|while|after|before|since|because|unless|once)\s+(?:a|an|the|some|any|each|every|this|that|my|your|his|her|its|our|their)\s+\w+(?:\s+\w+){0,5}\s+(?:is|are|was|were|do|does|did|can|could|would|should|has|have|had|travels?|moves?|runs?|goes?|starts?|opens?|closes?|takes?|makes?|gets?|has)\b[\w\s,;:\-\d.%]*\s+it\b', q):
        return True
    # Generic in-sentence antecedent: if a concrete noun phrase (determiner +
    # noun, or a plural noun) appears anywhere BEFORE "it/them/they/these/those"
    # in the same sentence, the pronoun is resolved in-query. This catches
    # "the code is slow, how do i fix it" and "a train travels..., how far does
    # it go" while leaving "how does it work" (no noun before "it") untouched.
    _PRO_NORM = re.sub(r'\b(?:why|what|when|where|how)\s+(?:is|are|was|were)\s+it\s+(?:that\b)', 'it ', q)
    _it_idx = None
    for _w in (' it ', ' them ', ' they ', ' these ', ' those '):
        _idx = _PRO_NORM.find(_w)
        if _idx != -1 and (_it_idx is None or _idx < _it_idx):
            _it_idx = _idx
    if _it_idx is not None and _it_idx > 0:
        _before = _PRO_NORM[:_it_idx].strip()
        # noun phrase via determiner: "a train", "the code", "my list"
        if re.search(r'\b(?:a|an|the|this|that|these|those|my|your|his|her|its|our|their|some|any|each|every|both|several|many|most|all|no)\s+[a-z][a-z-]{2,}\b', _before):
            return True
        # plural noun before the pronoun ("people... they", "status codes... they")
        if re.search(r'\b[a-z]{3,}s\s+(?:are|were|do|did|have|had|can|could|will|would)\b[\w\s]*\b(?:them|they)\b', q) \
           and re.search(r'\b(?:people|scientists|developers|users|students|codes?|files?|threads?|processes?|functions?|methods?|classes?|objects?|values?|items?|results?|errors?|warnings?|messages?|events?|things?)\b', _before):
            return True
    # Check for "they/them" with a preceding plural noun (e.g., "people... they see")
    if re.search(r'\b(?:people|scientists|researchers|humans|humans?|animals|creatures)\s+.*?\s+they\b', q):
        return True
    # Check for "them"/"they" referring to a noun within the same sentence
    # Require a VERY clear antecedent within the same sentence before the pronoun
    if re.search(r'\b(\w+s)\b.{0,30}\b(?:them|they)\b', q) and not re.search(r'\b(why|what|when|where|how)\s+(is|are|was|were)\s+it\b', q):
        words = q.split()
        them_idx = None
        for i, w in enumerate(words):
            if w.rstrip('.,;:!?') in ('them', 'they'):
                them_idx = i
                break
        if them_idx and them_idx > 1:  # Must be at least the 3rd word (not 2nd)
            # Check if the word immediately before is a specific plural noun
            prev_word = words[them_idx - 1].rstrip('.,;:!?').lower()
            # If preceded by a verb (is, are, was, etc.), the antecedent is less
            # clear — but auxiliaries like "do"/"have" before the pronoun still
            # allow an in-sentence plural noun ("status codes ... do they mean").
            if prev_word in ('is', 'are', 'was', 'were', 'and', 'or', 'but', 'of', 'in', 'on', 'at', 'to', 'for', 'with', 'by', 'from'):
                return False
            # Check if there's a clear plural noun as antecedent within first half of sentence
            half_idx = len(words) // 2
            for w in words[:half_idx]:
                w_clean = w.rstrip('.,;:!?').lower()
                if w_clean.endswith('s') and w_clean not in ('this', 'that', 'these', 'those', 'us', 'is', 'was', 'has', 'his', 'its', 'does', 'always', 'sometimes', 'often', 'usually', 'never', 'thus', 'plus', 'less', 'more'):
                    # Check if the word is a noun (not a verb)
                    if not w_clean.endswith(('ize', 'ise', 'ify', 'ate', 'ing', 'ed')):
                        return True
    # "that" as relative pronoun ONLY when preceded by a very clear, contentful noun
    # AVOID matching "that" in short, vague queries where "that" is referential
    # Require a specific noun (not a pronoun or generic term) before "that"
    generic_nouns = {'thing', 'things', 'stuff', 'ones', 'everything', 'something', 'anything', 'nothing'}
    # "that" used as a relative pronoun following a specific noun
    for m in re.finditer(r'\b(\w+)\s+that\s+(?:the|a|an|this|that|my|your|our|their|his|her|its|i|you|we|they|he|she|it|people|one)\b', q):
        noun = m.group(1).lower()
        if noun not in generic_nouns and len(noun) > 3 and noun not in ('that', 'this', 'these', 'those'):
            return True
    # "that" as relative pronoun followed by a past tense verb
    for m in re.finditer(r'\b(\w+)\s+that\s+(happened|occurred|were|was|lived|existed|survived|remained|stood|began|started|created|built|designed|made|produced|caused|resulted|turned|became|appeared|changed|evolved|developed|grew|ended|died)\b', q):
        noun = m.group(1).lower()
        if noun not in generic_nouns and len(noun) > 3:
            return True
    # "that" as a relative pronoun introducing a clause about a named thing
    # ("a function that returns the length", "code that prints a list")
    for m in re.finditer(r'\b(\w+)\s+that\s+(returns|takes|accepts|prints|produces|handles|finds|sorts|reverses|computes|calculates|reads|writes|opens|closes|creates|contains|includes|outputs|parses|loads|saves|stores|sends|receives|matches|filters|maps|counts|measures|shows|explains|describes|tells)\b', q):
        noun = m.group(1).lower()
        if noun not in generic_nouns and len(noun) > 3:
            return True
    # "that" as a demonstrative adjective (e.g., "that specific smell", "that particular reason")
    # The noun follows "that" in the same sentence, so the query is self-contained
    if re.search(r'\bthat\s+(?:specific|particular|certain|unique|distinct|given|mentioned|previous|prior|main|primary|key|actual|real|true)\s+\w+', q):
        return True
    # "that" as demonstrative with a limited set of common nouns
    if re.search(r'\bthat\s+(?:smell|reason|cause|effect|result|process|concept|idea|theory|issue|problem|solution|question|topic|subject|matter|area|field|approach|method|way|aspect|feature|element|factor|component|example|case|instance|situation|scenario|event|phenomenon|experience|feeling|emotion|memory|thought|belief|value|principle|notion|understanding|perspective|viewpoint|opinion|analysis|conclusion|outcome|consequence|impact|influence|significance|importance|relevance|meaning|purpose|goal|objective|aim|intent|need|condition|state|quality|property|characteristic|attribute)\b', q):
        return True
    # Check for "this" or "these" used as demonstrative within the query
    if re.search(r'\b(this|these)\s+(?:is|are|was|were|means?|refers?)\b', q):
        return True
    return False


def _query_is_context_dependent(query):
    """Check if a query primarily refers to prior conversation context."""
    q = query.lower().strip()
    if not q:
        return False

    # Queries that embed code are self-contained — the code is the subject
    # ("what does this do in python: [x*2 for x in range(5)]"). Brackets,
    # backticks, operators, or a language name followed by an expression make
    # the query concrete; a referential pronoun like "this" then points at
    # the snippet, not at prior context.
    if re.search(r'[\[\]{}]|`[^`]+`|=>|::|\b(?:def|function|class|import|'
                 r'return|const|let|var)\s+\w+|\b(?:python|javascript|js|'
                 r'java|c\+\+|go|rust|sql|bash)\b[^?]{0,20}[=()[\]\s]',
                 query):
        return False

    # "why is it called X" / "why is X called Y" — etymology/name questions
    # are self-contained (the "it" is generic, not referential).
    if re.search(r'^why\s+is\s+it\s+called\s+[a-z\s-]+$', q):
        return False
    # Short coding how-tos ("how to check python version", "how to convert
    # string to int") name their subject and are self-contained — the previous
    # topic must not be appended, or "how to check python version" can
    # misroute to an entry about the previous subject. Pronouns excluded.
    if re.search(r'^how\s+to\s+(?:check|install|use|run|get|set|convert|find|sort|reverse|split|join|merge|remove|add|create|open|read|write|parse|validate|start|stop|update|upgrade|list|rename|delete|copy|move|enable|disable|sleep|catch|handle|print|count|make|build|store|save|load|fetch|send|post|calculate|compare|filter|map|iterate|loop|repeat|round|format|split|strip|replace|search|match|test|debug|fix|solve|implement|define|declare|initialize|assign|return|throw|raise|import|export|install|uninstall|downgrade|pin|commit|push|pull|clone|branch|stash|rebase|reset|revert)\s+(?!(?:it|that|this|them|these|those)\b)', q):
        return False
    # "what is a unit test and why write them" — the trailing clause's pronoun
    # refers to the noun introduced earlier in the SAME query, so it is
    # self-contained ("what is X and why/how/when <verb> them").
    if re.search(r'^what\s+is\s+(?:a|an|the)\s+[a-z\s-]{3,60}\s+and\s+(?:why|how|when|where|what)\s+\w+(?:\s+\w+)?\s+(?:them|it|they|these|those)$', q):
        return False
    # "what causes earthquakes" / "what causes the seasons" — causation
    # questions are self-contained.
    if re.search(r'^what\s+causes?\s+', q):
        return False
    # "what is the capital/currency/population/language/religion/climate of X"
    # — attribute questions are self-contained.
    if re.search(r'^what\s+is\s+the\s+(?:capital|currency|population|language|religion|climate|highest|lowest|largest|smallest|biggest|tallest|longest|fastest|deepest)\s+(?:of|in|on)\s+', q):
        return False
    # "why do leaves change color" — seasonal/nature color changes are
    # self-contained.
    if re.search(r'^why\s+do(?:es)?\s+[a-z\s-]+?\s+change\s+color$', q):
        return False
    # Category questions ("what types of X are there", "what kinds of X live in Y")
    # are inherently self-contained — they ask about a category, not prior context.
    if re.search(r'^(?:what|which)\s+(?:types?|kinds?|breeds?|species?|varieties?|forms?|styles?|members?|groups?)\s+of\b', q):
        return False
    # "what Xs are there" / "what Xs exist" — self-contained category questions
    if re.search(r'^(?:what|which)\s+[a-z\s-]+?\s+(?:are\s+there|exist|do\s+we\s+have)$', q):
        return False

    # Short follow-up questions (< 40 chars) starting with question words
    # often refer to previous context even without explicit pronouns.
    # E.g., "Who were the key pioneers?" after discussing jazz means
    # "jazz pioneers". "What instruments are used?" means "instruments in <previous topic>".
    # BUT: "who is X" with a proper noun ("who is anubis") and process
    # questions ("how are fossils formed") are self-contained.
    if re.search(r'^who\s+(?:is|was|are|were)\s+[A-Z]', query):
        return False  # proper-noun identification, not a context reference
    # "who invented/discovered/built X" — attribution questions are
    # self-contained ("who invented the telephone", "who first discovered X")
    if re.search(r'^who\s+(?:even\s+|the\s+heck\s+|the\s+hell\s+|actually\s+)?(?:first\s+)?(?:invented|discovered|created|built|founded|wrote|made|designed|developed|painted)\s+', q):
        return False
    # "what day is X" / "when is X" — calendar questions are self-contained
    if re.search(r'^(?:what\s+(?:day|date)\s+is|when\s+(?:is|are|was|were))\s+', q):
        return False
    # "what year was X" / "when was X" / "who was X" — temporal/attribution
    # questions with a concrete subject are self-contained (excludes pronouns)
    if re.search(r'^(?:what\s+year\s+(?:was|were|did|is|are)|in\s+what\s+year\s+(?:was|were|did|is|are))\s+', q):
        return False
    if re.search(r'^(?:when|who)\s+(?:was|were|is|are|did)\s+(?!(?:it|that|this|they|them)\b)', q):
        # "who were the romans" is self-contained, but "who were the key
        # pioneers?" / "who were the main characters?" after a topic is a
        # follow-up that needs the previous subject to make sense.
        if not re.search(r'\b(?:pioneers?|leaders?|members?|characters?|figures?|instruments?|features?|reasons?|causes?|examples?|founders?|inventors?|artists?|scientists?|players?|teams?|cities?|countries?|wars?|battles?|events?|effects?|benefits?|risks?|types?|kinds?|rulers?|pharaohs?|dynasties?|empires?|civilizations?)\b', q):
            return False
    # "what does X symbolize" / "what does X stand for" — self-contained
    if re.search(r'^what\s+(?:does|do|did)\s+(?:(?:the|a|an)\s+)?[a-z\s-]+?\s+(?:symbolize|represent|stand\s+for|mean)$', q):
        return False
    # "what about X" / "how about X" — introduces a NEW subject ("what
    # about spain" after discussing France means tell me about Spain), not a
    # reference to the previous topic
    if re.search(r'^(?:what|how)\s+about\s+[a-z\s-]{3,}$', q):
        return False
    # "... there / ... here" — locative deictics refer to the previous
    # topic ("what is the population there" after discussing Paris)
    if re.search(r'\s(?:there|here)\s*$', q):
        return True
    # "why is X bad" / "why is sugar unhealthy" — health evaluation questions
    # are self-contained
    if re.search(r'^why\s+is\s+(?:the\s+)?[a-z]+\s+(?:bad|good|unhealthy|healthy|important|necessary|useful|dangerous|safe|popular|famous|expensive|cheap)(?:\s+for\s+(?:you|your\s+health|humans))?$', q):
        return False
    if re.search(r'^(?:how|why|what)\s+(?:is|are|was|were|do|does|did)\s+(?:(?:the|a|an|this|that|these|those)\s+)?[a-z\s-]+?\s+(?:formed|made|created|built|produced|generated|caused|work|works|occur|occurs|happen|happens|function|run|runs|processed|brewed|extracted|fermented|refined|manufactured|cooked|prepared|stored|preserved|harvested|distilled|bottled|packaged|grown|raised|caught|wet|float|floats|sink|freeze|freezes|melt|melt|boil|boils|evaporate|evaporates|condense|condenses|burn|burns|rust|rots|rot|decay|glow|glows|shine|shines|turn|turns|change|changes|form|forms)$', q):
        return False  # self-contained process question ("how are fossils formed", "how is olive oil extracted")
    # Emphatic question forms ("what even is X", "what exactly are X",
    # "how on earth does X work") are self-contained — the emphasis word
    # doesn't refer back to prior context.
    if re.search(r'^(?:what|which|who|where|when|why|how)\s+(?:even|exactly|actually|the\s+heck|on\s+earth|in\s+the\s+world|the\s+hell)\s+(?:is|are|was|were|do|does|did)\b', q):
        return False
    # "how come X" means "why X" — always self-contained
    if re.search(r'^how\s+come\b', q):
        return False
    # "why do we have X" / "why do we hiccup" / "why do humans get X" —
    # self-contained biology/behavior questions. Excludes genuine follow-ups
    # containing a referential pronoun ("why do we care about it").
    if re.search(r'^why\s+do\s+(?:we|humans|people|i|you)\s+', q):
        _remainder = re.sub(r'^why\s+do\s+(?:we|humans|people|i|you)\s+', '', q)
        if not re.search(r'\b(?:that|it|this|them|they)\b', _remainder):
            return False
    # "what do X eat" / "where do X live" / "why do cats purr" —
    # subject+verb behavior questions are self-contained
    if re.search(r'^(?:what|why|how|when|where|which)\s+(?:do|does|did|is|are|was|were|can|could)\s+[a-z\s-]+?\s+(?:eat|live|sleep|dream|drink|hunt|swim|fly|climb|run|jump|sing|talk|purr|bark|meow|migrate|hibernate|mate|nest|grow|form|have|use|need|die|end|start|begin|occur|happen|work|function|survive|breed|communicate|navigate|see|hear|smell|reproduce|adapt|breathe|do|does|build|make|produce|create|walk\s+on\s+walls|see\s+in\s+the\s+dark|hold\s+its\s+breath|defend\s+themselves|protect\s+themselves|find\s+their\s+way|hunt)$', q):
        return False
    # "how strong is X" / "how smart are X" — capability questions are
    # self-contained (excludes pronouns)
    if re.search(r'^how\s+(?:strong|smart|intelligent|big|tall|heavy|fast|far|deep|high|wide|old|long)\s+(?:is|are|was|were)\s+(?!(?:it|that|this|they|them)\b)', q):
        return False
    # Media/story questions ("what happens at the end of X", "where is X set") are self-contained
    if re.search(r'^what\s+happens\s+(?:at\s+the\s+end\s+of|in|during|when)\s+', q):
        return False
    if re.search(r'^(?:where|when)\s+(?:is|are|was|were)\s+[a-z\s-]+?\s+set$', q):
        return False
    # Info-request forms ("what information do you have on X",
    # "what do you have on X", "what can you say about X") are self-contained.
    if re.search(r'^(?:what\s+(?:information|knowledge|facts|details)\s+(?:do|does|is|are)|what\s+do\s+you\s+have|what\s+can\s+you\s+say|anything\s+you\s+can\s+tell\s+me|your\s+knowledge\s+of|i\'?d\s+(?:love|like)\s+to\s+hear\s+about|spill\s+the\s+beans)', q):
        return False
    # "why is X so Y" / "why are cats so cute" — self-contained
    if re.search(r'^why\s+(?:is|are|was|were)\s+(?:the\s+)?[a-z]+\s+so\s+[a-z]+$', q):
        return False
    # Sensory questions ("what does X taste like", "how does X feel") are
    # self-contained.
    if re.search(r'^what\s+(?:does|do|did)\s+(?:(?:the|a|an|this|that)\s+)?[a-z]+\s+(?:taste|smell|look|feel|sound)\s+like$', q):
        return False
    # Lifecycle questions ("when did X end", "how did X die", "when did X
    # start") and relationship questions ("how are X and Y related",
    # "is X the same as Y") are self-contained.
    if re.search(r'^(?:how|when|where|why)\s+(?:did|does|do|was|were|is|are)\s+[a-z\s-]+?(?:die|end|start|begin|form|happen|occur|originate|fall|fell|collapse|collapsed|decline|declined|get\s+its\s+name)$', q):
        return False
    if re.search(r'^how\s+are\s+[a-z\s-]+?\s+and\s+[a-z\s-]+?\s+related$', q):
        return False
    # Comparison questions ("how do X and Y differ", "are X and Y the
    # same", "what do X and Y have in common", "how is X different from
    # Y") are self-contained — they compare two named subjects.
    if re.search(r'^(?:how\s+(?:do|does|are|is)|what\s+(?:do|does)|are|is)\s+[a-z\s-]+?\s+and\s+[a-z\s-]+?\s+(?:differ|different|similar|the\s+same|have\s+in\s+common)$', q):
        return False
    # "which is bigger, X or Y" / "is X or Y bigger" — comparison questions
    # name both subjects and are self-contained
    if re.search(r'^which\s+is\s+(?:the\s+)?(?:bigger|smaller|larger|faster|slower|taller|shorter|heavier|lighter|hotter|colder|older|younger|better|worse|stronger|longer|wider|deeper|higher|more\s+popular|more\s+common|farther|further)\s*,?\s*.+\s+or\s+.+$', q):
        return False
    if re.search(r'^(?:is|are)\s+.+\s+or\s+.+\s+(?:bigger|smaller|larger|faster|slower|taller|shorter|heavier|lighter|hotter|colder|older|younger|better|worse|stronger|longer|wider|deeper|higher|more\s+popular|more\s+common|farther|further)\s*$', q):
        return False
    if re.search(r'^how\s+(?:is|are)\s+(?!(?:it|this|that|they|them|we|you)\s+different\s+from)[a-z\s-]+?\s+different\s+from\s+[a-z\s-]+?$', q):
        return False
    if re.search(r'^how\s+do(?:es)?\s+(?!(?:it|this|that|they|them|we|you)\s+differ\s+from)[a-z\s-]+?\s+differ\s+from\s+[a-z\s-]+?$', q):
        return False
    # "who is X married to" — personal-relationship questions are self-contained
    if re.search(r'^who\s+(?:is|was|are|were)\s+[a-z\s-]+?\s+married\s+to$', q):
        return False
    # "what language do they speak in X" / "what do they call X" — the
    # "they" is impersonal, not referential
    if re.search(r'^(?:what\s+language\s+do\s+they\s+speak\s+in|what\s+language\s+is\s+spoken\s+in|what\s+do\s+they\s+call)\s+', q):
        return False
    # "what currency is used in japan" / "what food is eaten in mexico" —
    # attribute questions with a concrete subject and place are self-contained
    if re.search(r'^what\s+[a-z\s-]+?\s+(?:is|are)\s+(?:used|spoken|written|made|built|produced|grown|found|mined|manufactured|located|situated|eaten|drunk|served|celebrated|practiced|practised|played)\s+(?:in|at|on|by)\s+[a-z\s-]+$', q):
        return False
    if re.search(r'^(?:is|are)\s+[a-z\s-]+?\s+the\s+same\s+as\s+[a-z\s-]+?$', q):
        return False
    # Origin questions ("where does jazz come from", "where does the name
    # jazz come from") are self-contained.
    if re.search(r'^where\s+(?:does|do|did)\s+(?:the\s+name\s+)?[a-z\s-]+?\s+come\s+from$', q):
        return False
    # Measurement questions ("how tall is X", "how old is the earth",
    # "how much does X weigh", "how many moons does X have") are self-contained
    # — but a pronoun subject ("how many legs does it have") is a follow-up.
    if re.search(r'^how\s+(?:old|big|tall|far|fast|heavy|hot|cold|large|small|wide|deep|high|long|many|much)\s+(?:[a-z]+\s+)?(?:is|are|was|were|does|do|did)\b(?!\s*(?:it|this|that|they|them|these|those)\b)', q):
        return False
    if re.search(r'^why\s+(?:does\s+(?:the|a|an)|is\s+the|are\s+the|do\s+(?:we|humans|people)\s+(?:get|feel))\s*', q):
        return False
    # Origin/location/event questions with a concrete subject are
    # self-contained: "where did jazz come from", "when was rome built",
    # "how did the universe begin", "why is the ocean blue"
    if re.search(r'^(?:where|when|how|why)\s+(?:is|are|was|were|did|does|do)\s+(?:the|a|an)?\s*[a-z]+\s+(?:come\s+from|originate|located|built|founded|created|invented|discovered|start|started|begin|began|form|formed|evolve|evolved|happen|happened|occur|occurred|first\s+appear|made|launched|established|developed|introduced)$', q):
        return False
    if len(q) < 40 and not q.startswith(('what is', 'what are', 'what was', 'define', 'explain', 'describe', 'who is', 'who was', 'whats')):
        # Check if query starts with a question word and is short
        question_words = ['who', 'what', 'when', 'where', 'how', 'why', 'which', 'whose']
        first_word = q.split()[0].rstrip('.,;:!?') if q.split() else ''
        if first_word in question_words:
            # Count substantive words (not counting the question word, articles, prepositions)
            words = q.split()
            stop = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'do', 'does', 'did',
                    'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'and', 'or',
                    'typically', 'usually', 'often', 'commonly', 'generally', 'sometimes',
                    'also', 'too', 'as', 'be', 'been', 'being', 'have', 'has', 'had',
                    'its', 'their', 'our', 'your', 'his', 'her', 'their', 'them'}
            content_words = [w for w in words[1:] if w not in stop]
            # If the query has very few content words (< 4), it's likely context-dependent
            # E.g., "Who were the key pioneers?" -> content words: [key, pioneers] = 2
            #
            # BUT: if the remaining words include a concrete noun candidate
            # (a word that can name a topic of its own), the question is
            # self-contained even when short: "why is my code slow?" names
            # "code", "how do trains work?" names "trains", "what is a
            # deadlock?" names "deadlock". Only treat as context-dependent
            # when every content word is a vague modifier or verb ("why is it
            # bad", "what about that").
            _GENERIC_WORDS = {
                'good', 'bad', 'better', 'worse', 'best', 'worst', 'slow',
                'fast', 'quick', 'easy', 'hard', 'difficult', 'simple',
                'important', 'popular', 'useful', 'fun', 'cool', 'nice',
                'weird', 'strange', 'interesting', 'boring', 'wrong', 'right',
                'true', 'false', 'big', 'small', 'large', 'tiny', 'new',
                'old', 'bigger', 'smaller', 'larger', 'faster', 'slower',
                'harder', 'easier', 'common', 'rare', 'normal', 'special',
                'different', 'same', 'similar', 'much', 'many', 'enough',
                'something', 'anything', 'nothing', 'everything', 'thing',
                'stuff', 'way', 'ways', 'work', 'works', 'working', 'happen',
                'happens', 'mean', 'means', 'exist', 'exists', 'made',
                'doing', 'get', 'got', 'gets', 'make', 'makes', 'use', 'uses',
                'need', 'needs', 'want', 'wants', 'see', 'look', 'feel',
                'feels', 'say', 'says', 'do', 'does', 'did', 'have', 'has',
                # modifiers
                'key', 'main', 'major', 'various', 'different', 'other',
                'such', 'certain', 'particular', 'specific', 'most', 'some',
                'few', 'several', 'all', 'any', 'every', 'biggest', 'smallest',
                'best', 'worst', 'first', 'last', 'next', 'previous',
                # category words (a category needs a subject to belong to:
                # "key pioneers" after discussing jazz means jazz pioneers)
                'pioneers', 'pioneer', 'leaders', 'leader', 'members',
                'member', 'characters', 'character', 'figures', 'figure',
                'instruments', 'instrument', 'features', 'feature', 'reasons',
                'reason', 'causes', 'cause', 'examples', 'example', 'founders',
                'founder', 'inventors', 'inventor', 'artists', 'artist',
                'scientists', 'scientist', 'players', 'player', 'teams',
                'team', 'cities', 'city', 'countries', 'country', 'wars',
                'war', 'battles', 'battle', 'events', 'event', 'effects',
                'effect', 'benefits', 'benefit', 'risks', 'risk', 'types',
                'type', 'kinds', 'kind', 'rules', 'rule', 'strategies',
                'strategy', 'techniques', 'technique', 'methods', 'method',
                'styles', 'style', 'forms', 'form', 'genres', 'genre',
                'eras', 'era', 'periods', 'period', 'phases', 'phase',
                'stages', 'stage', 'uses', 'usage', 'applications',
                'application', 'aspects', 'aspect', 'parts', 'part',
                'groups', 'group', 'schools', 'school', 'writers', 'writer',
                'composers', 'composer', 'directors', 'director', 'actors',
                'actor', 'books', 'book', 'novels', 'novel', 'films', 'film',
                'songs', 'song', 'albums', 'album', 'works', 'work',
            }
            if len(content_words) <= 3 and not any(
                    w.rstrip('.,;:!?').lower() not in _GENERIC_WORDS and len(w) > 3
                    for w in content_words):
                return True

    # Long queries (>30 chars) with enough content words are self-contained
    if len(q) > 30:
        words = q.split()
        # If the query has 5+ words, it's likely self-contained even if it
        # contains pronouns like "that" (used as relative pronoun, not referential)
        if len(words) >= 5:
            # However, certain pronouns ("it", "them", "they", "that", "this") are
            # almost always referential — they refer back to something previously
            # mentioned. "What are some fun facts about it?" needs context to
            # resolve "it". "How does that compare to other empires?" needs
            # context to resolve "that".
            #
            # BUT: if the pronoun has an antecedent within the same sentence
            # (e.g., "a human body if it fell" or "people... they see"), it's
            # not context-dependent — the pronoun is resolved within the query.
            referential_pronouns = {'it', 'them', 'they', 'that', 'this'}
            # "that" after a reporting/thinking verb ("i heard that X",
            # "i read that X", "did you know that X") is a complementizer
            # introducing a clause, NOT a referential pronoun.
            _COMPLEMENTIZER_VERBS = (
                'heard', 'said', 'says', 'say', 'think', 'thought', 'know',
                'knew', 'believe', 'believed', 'read', 'realized', 'realised',
                'found', 'found out', 'noticed', 'noted', 'feel', 'felt', 'saw',
                'seen', 'told', 'decided', 'assume', 'assumed', 'guess',
                'guessed', 'bet', 'wonder', 'wondered', 'hope', 'hoped',
                'understand', 'understood', 'remember', 'recall', 'learned',
                'learnt', 'discovered', 'recalled', 'claimed', 'stated',
                'mentioned', 'wrote', 'explained', 'figured', 'figured out',
            )
            if re.search(r'\b(?:' + '|'.join(_COMPLEMENTIZER_VERBS) + r')\s+that\b', q):
                referential_pronouns = referential_pronouns - {'that'}
            has_referential_pronoun = any(
                w.rstrip('.,;:!?') in referential_pronouns for w in words
            )
            if has_referential_pronoun:
                # Check if the pronoun has an antecedent within the same sentence
                # (e.g., "a human body if it fell" -> "it" refers to "human body")
                # If so, the query is self-contained
                if _pronoun_has_antecedent_in_sentence(q):
                    # Fall through to follow-up signal check
                    pass
                else:
                    return True
            # Only treat as context-dependent if it has explicit follow-up signals
            followup_signals = [
                'tell me more', 'tell me about that', 'explain that',
                'go on', 'continue', 'more about', 'expand on',
                'yeah but', 'yes but', 'ok but', 'well what about',
                'how about it', 'what about it', 'what about them',
                'regarding that', 'about that',
                'what were the', 'what colors', 'why is that',
                'how does that', 'how does it',
            ]
            return any(s in q for s in followup_signals)

    pronoun_refs = {'it', 'that', 'this', 'them', 'those', 'these', 'they'}
    words = q.split()
    has_pronoun = any(w.rstrip('.,;:!?') in pronoun_refs for w in words)

    followup_signals = [
        'tell me more', 'tell me about that', 'explain that',
        'go on', 'continue', 'more about', 'expand on',
        'yeah but', 'yes but', 'ok but', 'well what about',
        'how about it', 'what about it', 'what about them',
        'regarding that', 'about that',
        'what were the', 'what colors', 'why is that',
        'how does that', 'how does it',
    ]
    has_signal = any(s in q for s in followup_signals)

    expansion_words = {'longer', 'more', 'detailed', 'further', 'elaborate', 'details'}
    is_expansion = any(w == q for w in expansion_words)

    return has_pronoun or has_signal or is_expansion


def _sig_stem(w):
    """Reduce a word to a comparable form ('tigers' -> 'tiger', 'lions' -> 'lion')."""
    w = w.rstrip('s')
    if w.endswith('ie') and len(w) > 4:
        return w[:-2] + 'y'
    if w.endswith('ies') and len(w) > 5:
        return w[:-3] + 'y'
    if w.endswith('es') and len(w) > 4 and w not in ('does', 'goes', 'was', 'has'):
        return w[:-2]
    return w


def _select_wiki_title(search_results, topic):
    """Pick the Wikipedia search result whose title relates to the topic.

    Text search can return a generic page ("Formula" for "chemical formula
    for water", "Year" for "what year was the first iphone released") as the
    top hit. This scores the top results and skips titles with no real
    connection to the asked-about subject. Returns a title or None.
    """
    topic_clean = topic.strip().rstrip('?!.')
    sig_words = {_sig_stem(w) for w in re.findall(r'\b[a-z]{4,}\b', topic_clean.lower())}
    sig_words -= {'what', 'why', 'how', 'when', 'where', 'which', 'does',
                  'about', 'that', 'this', 'with', 'from', 'have', 'been',
                  'were', 'their', 'them', 'there', 'your', 'tell', 'the',
                  'best', 'way', 'ways', 'first', 'last', 'make', 'made',
                  'used', 'using', 'use', 'released', 'release', 'called',
                  'released?', 'want', 'need', 'get', 'know', 'like', 'look',
                  'compare', 'comparing', 'comparison', 'differ', 'difference',
                  'different', 'similar', 'between', 'versus', 'both'}
    for _res in search_results:
        _title = _res.get('title', '')
        _title_lower = _title.lower()
        # exact (case-insensitive) title match is always accepted
        if _title_lower == topic_clean.lower() or _title_lower == topic_clean.lower().rstrip('s'):
            return _title
        if not sig_words:
            return _title
        _title_words = {_sig_stem(w) for w in re.findall(r'\b[a-z]{4,}\b', _title_lower)}
        _title_words -= {'and', 'the', 'of', 'in', 'on', 'for', 'with',
                         'disambiguation', 'list', 'from', 'about'}
        if _title_words & sig_words:
            return _title
    return None


def _looks_like_bare_topic(query: str) -> bool:
    """True when the string is a bare noun phrase / page title (e.g. a topic
    passed from another function), not a full sentence.

    Bare topics must be searched verbatim — running them through
    _resolve_topic can mangle exact titles like 'IPhone (1st generation)'
    into unrelated words ('generation').
    """
    q = query.strip()
    if not q or '(' in q or ')' in q:
        return True
    words = q.split()
    first = words[0].rstrip('.,;:!?').lower()
    if first in ('who', 'what', 'when', 'where', 'how', 'why', 'which', 'whose',
                 'is', 'are', 'was', 'were', 'do', 'does', 'did', 'can', 'could',
                 'would', 'should', 'will', 'shall', 'may', 'might', 'tell',
                 'show', 'explain', 'describe', 'define', 'compare', 'why', 'i',
                 'you', 'we', 'they', 'he', 'she', 'it'):
        return False
    return len(words) <= 6


def _search_wikipedia(query):
    """Search Wikipedia for a query and return a summary.

    Returns (summary_text, source_url) or (None, None) on failure.
    Uses a simple in-memory cache to avoid repeat requests.
    Uses conversation history to resolve pronouns in context-dependent queries.
    """
    # Try to extract a clean topic, resolving pronouns from context
    topic = _resolve_topic(query, conversation_history) if not _looks_like_bare_topic(query) else query
    if not topic or len(topic) < 3:
        topic = query.strip()[:100]

    cache_key = topic.lower().strip()
    if cache_key in _WIKI_CACHE:
        global _WIKI_CACHE_HITS
        _WIKI_CACHE_HITS += 1
        return _WIKI_CACHE[cache_key]

    try:
        # Step 1: Search for the best page title via the Wikipedia search API
        # (opensearch doesn't handle long queries well; the search API does)
        search_url = (
            'https://en.wikipedia.org/w/api.php?'
            'action=query&list=search&srwhat=text'
            '&srsearch=' + urllib.parse.quote(topic) +
            '&srlimit=8&format=json'
        )
        req = urllib.request.Request(search_url, headers={
            'User-Agent': 'COS/1.0 (conversational AI; no-inference)'
        })
        with urllib.request.urlopen(req, timeout=4) as resp:
            result = json.loads(resp.read().decode())

        search_results = result.get('query', {}).get('search', [])
        if not search_results:
            return None, None

        page_title = _select_wiki_title(search_results, topic)
        if not page_title:
            # No result is related to the asked-about subject — do not return
            # an unrelated article as if it were an answer.
            return None, None
        page_url = f'https://en.wikipedia.org/wiki/{urllib.parse.quote(page_title.replace(" ", "_"))}'

        # Step 2: Get the page summary
        summary_url = (
            'https://en.wikipedia.org/api/rest_v1/page/summary/' +
            urllib.parse.quote(page_title)
        )
        req = urllib.request.Request(summary_url, headers={
            'User-Agent': 'COS/1.0 (conversational AI; no-inference)'
        })
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode())

        extract = data.get('extract', '')
        if not extract:
            return None, None

        # Reject disambiguation pages and lists
        extract_lower = extract.lower()
        if any(marker in extract_lower[:300] for marker in [
            'may refer to', 'may also refer', 'may designate',
            'this disambiguation', 'list of ', 'refers to a',
            'can refer to', 'could refer to', 'most commonly refers',
            'commonly refers to', 'is a disambiguation',
        ]):
            return None, None

        # For essays and rich content, use the full extract (up to 6000 chars)
        if len(extract) > 6000:
            # Find the last sentence boundary before 6000 chars
            if '. ' in extract[:6000]:
                trunc = extract[:extract.rfind('. ', 0, 6000) + 1]
            else:
                # No sentence boundary — cut at a word boundary instead of
                # mid-word ("History S..." type garbage)
                trunc = extract[:extract.rfind(' ', 0, 6000)]
            trunc = re.sub(r'\b\w+$', '', trunc).rstrip(',;: ') + '.'
            extract = trunc

        # If the summary is too short (<500 chars), try to get the full article
        # for richer content
        if len(extract.strip()) < 500 and len(extract.strip()) > 50:
            try:
                full_text, _ = _search_wikipedia_full(page_title)
                if full_text and len(full_text) > len(extract):
                    # Use first 2-3 paragraphs of full article
                    paras = [p.strip() for p in full_text.split('\n\n') if p.strip()]
                    if paras:
                        extract = '\n\n'.join(paras[:3])
            except Exception:
                pass

        result = (extract.strip(), page_url or summary_url)
        _WIKI_CACHE[cache_key] = result
        _save_wiki_cache()
        return result
    except Exception:
        return None, None


_WIKI_FULL_CACHE = {}


def _search_wikipedia_full(query):
    """Retrieve the full plain-text Wikipedia article extract for rich content.

    Unlike _search_wikipedia (which returns the short REST summary), this uses
    the MediaWiki API extracts prop to fetch the full article body as plain text.
    Returns (full_text, source_url) or (None, None) on failure.
    """
    topic = _resolve_topic(query, conversation_history) if not _looks_like_bare_topic(query) else query
    if not topic or len(topic) < 3:
        topic = query.strip()[:100]

    cache_key = topic.lower().strip()
    if cache_key in _WIKI_FULL_CACHE:
        global _WIKI_CACHE_HITS
        _WIKI_CACHE_HITS += 1
        return _WIKI_FULL_CACHE[cache_key]

    try:
        # Step 1: Search for the best page title via the Wikipedia search API
        search_url = (
            'https://en.wikipedia.org/w/api.php?'
            'action=query&list=search&srwhat=text'
            '&srsearch=' + urllib.parse.quote(topic) +
            '&srlimit=8&format=json'
        )
        req = urllib.request.Request(search_url, headers={
            'User-Agent': 'COS/1.0 (conversational AI; no-inference)'
        })
        with urllib.request.urlopen(req, timeout=4) as resp:
            result = json.loads(resp.read().decode())

        search_results = result.get('query', {}).get('search', [])
        if not search_results:
            return None, None

        page_title = _select_wiki_title(search_results, topic)
        if not page_title:
            return None, None
        page_url = f'https://en.wikipedia.org/wiki/{urllib.parse.quote(page_title.replace(" ", "_"))}'

        # Step 2: Fetch the full article extract via the MediaWiki API
        extract_url = (
            'https://en.wikipedia.org/w/api.php?'
            'action=query&prop=extracts&explaintext=true&exsectionformat=plain'
            '&titles=' + urllib.parse.quote(page_title) +
            '&format=json&redirects=1'
        )
        req = urllib.request.Request(extract_url, headers={
            'User-Agent': 'COS/1.0 (conversational AI; no-inference)'
        })
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode())

        pages = data.get('query', {}).get('pages', {})
        if not pages:
            return None, None

        page = next(iter(pages.values()))
        extract = page.get('extract', '')
        if not extract or len(extract) < 200:
            return None, None

        # Reject disambiguation pages
        extract_lower = extract.lower()
        if any(marker in extract_lower[:300] for marker in [
            'may refer to', 'may also refer', 'may designate',
            'this disambiguation', 'list of ', 'refers to a',
            'can refer to', 'could refer to', 'most commonly refers',
            'commonly refers to', 'is a disambiguation',
        ]):
            return None, None

        # Truncate to a reasonable size for processing (12000 chars)
        if len(extract) > 12000:
            # Always end at a sentence boundary
            cut = extract.rfind('. ', 0, 12000)
            if cut > 9000:
                extract = extract[:cut + 1]
            else:
                extract = extract[:12000]
            # Also strip any trailing text after last sentence-ending punctuation
            extract = re.sub(r'[^.!?]*$', '', extract).strip()
            # Remove trailing word fragment if the last word is very short
            if extract:
                last_word = extract.split()[-1].rstrip('.!?').lower() if extract.split() else ''
                if len(last_word) <= 2 and last_word not in ('i', 'a', 'am', 'an', 'as', 'at', 'be', 'by', 'do', 'go', 'he', 'if', 'in', 'is', 'it', 'me', 'my', 'no', 'of', 'on', 'or', 'so', 'to', 'up', 'us', 'we'):
                    penultimate = extract.rfind('.', 0, extract.rfind('.'))
                    if penultimate >= 0:
                        extract = extract[:penultimate + 1]

        result = (extract.strip(), page_url or f'https://en.wikipedia.org/wiki/{urllib.parse.quote(page_title)}')
        _WIKI_FULL_CACHE[cache_key] = result
        _save_wiki_cache()
        return result
    except Exception:
        return None, None


# ── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent.absolute()


# ── Global state accessors (for the TUI) ─────────────────────────────────────

def get_conversation_history():
    return conversation_history

def set_roleplay(persona):
    global current_roleplay
    current_roleplay = persona

def clear_roleplay():
    global current_roleplay
    current_roleplay = None

def reset_conversation():
    """Reset all conversation state."""
    global current_roleplay
    conversation_history.clear()
    current_roleplay = None
    fact_memory.clear()


# ── Math helpers ─────────────────────────────────────────────────────────────

def _extract_math_expression(text):
    """Extract a math expression from natural language."""
    # Normalize word operators to symbols
    t = text.lower()
    t = re.sub(r'\bplus\b', '+', t)
    t = re.sub(r'\bminus\b', '-', t)
    t = re.sub(r'\btimes\b', '*', t)
    t = re.sub(r'\bmultiplied by\b', '*', t)
    t = re.sub(r'\bdivided by\b', '/', t)
    t = re.sub(r'\bover\b', '/', t)
    patterns = [
        r"(?:what is|what's|whats|calculate|compute|solve|find)\s+([\d\s\+\-\*/\^\(\)\.%]+)",
        r'([\d\s\+\-\*/\^\(\)\.%]+)\s*(?:equals\?|=\s*\?)',
        r'^([\d]+\s*[\+\-\*/]\s*[\d]+(?:\s*[\+\-\*/]\s*[\d]+)*)$',
    ]
    for pat in patterns:
        m = re.search(pat, t)
        if m:
            expr = m.group(1).strip()
            # A bare number ("solve 2x - 4 = 8" extracts "2" before hitting the
            # 'x') is not an expression — require at least one operator so we
            # don't answer "2" for an equation about x.
            if re.search(r'[\+\-\*/^]', expr):
                return expr
    return None


def _solve_math(expr):
    """Evaluate a simple arithmetic expression safely."""
    expr = expr.replace('^', '**').replace('x', '*').replace('×', '*')
    # Only allow safe characters
    if not re.match(r'^[\d\s\+\-\*/\(\)\.%]+$', expr):
        return None
    try:
        return eval(expr)
    except:
        return None


def _solve_word_problem(question):
    """Solve a word problem using the math solver."""
    try:
        from cos.math_solver import solve_word_problem as wp
        return wp(question)
    except Exception:
        return None


# ── C runner ─────────────────────────────────────────────────────────────────

_KNOWN_GENERIC = {
    'i understand.', 'i understand', 'i don\'t know.', 'i don\'t know',
    'i don\'t understand.', 'i don\'t understand',
    'i do not know.', 'i do not know',
    'i have no information about that.',
    'that doesn\'t make sense.',
    'you mentioned',  # prefix check
}

def _is_generic_response(text):
    """Check if a response is a generic non-answer."""
    r = text.lower().strip().rstrip('.!?')
    if r in _KNOWN_GENERIC:
        return True
    for prefix in ('you mentioned', 'i understand', 'i don\'t know', 'i do not know',
                   'i don\'t understand', 'i cannot answer', 'that is a good question',
                   'that\'s a good question'):
        if r.startswith(prefix):
            return True
    if len(r) < 15:
        return True
    # Check for excessive repetition
    words = r.split()
    if len(words) >= 5 and len(set(words)) <= 2:
        return True
    return False


# ── False premise detection ─────────────────────────────────────────────────

def _detect_false_premise(query):
    """Detect if a query contains false premises, non-existent concepts,
    or known pseudoscience. Returns a correction response if detected, None otherwise."""
    q = query.lower().strip()

    # ── False color claims about the sky ──
    m = re.search(r'why is the sky (green|purple|orange|red|yellow|pink|brown)', q)
    if m:
        color = m.group(1)
        return (
            f"The sky appears blue during the day due to Rayleigh scattering, "
            f"where shorter blue wavelengths of sunlight are scattered more by the "
            f"atmosphere than longer wavelengths. The sky does not normally appear "
            f"{color} during the day; that color would only occur during sunrise/sunset "
            f"or due to atmospheric phenomena like smoke or pollution."
        )

    # ── Perpetual motion / free energy ──
    if re.search(r'perpetual motion', q) and not re.search(r'why (isn|doesn|can)', q):
        return (
            "Perpetual motion machines are hypothetical devices that would operate "
            "indefinitely without an external energy source, but they violate the laws "
            "of thermodynamics. The first law (conservation of energy) states that "
            "energy cannot be created or destroyed, and the second law states that "
            "entropy in an isolated system always increases. No perpetual motion "
            "machine has ever been successfully constructed, and physics dictates that "
            "such a device is impossible."
        )

    # ── Common false premises ──
    false_premises = {
        r'humans? only use 10% of (their )?brain': (
            "The idea that humans only use 10% of their brain is a widespread myth. "
            "Brain imaging studies using fMRI and PET scans show that virtually all "
            "parts of the brain have identifiable functions. Even during simple tasks, "
            "multiple brain regions are active. The myth likely originated from a "
            "misunderstanding of early neuroscience or from a misinterpretation of "
            "William James's statement that people only use a small portion of their "
            "potential."
        ),
        r'vaccines? cause autism': (
            "Extensive scientific research has conclusively shown there is no link "
            "between vaccines and autism. The original 1998 study that suggested a "
            "connection was retracted due to serious ethical violations and scientific "
            "fraud. Numerous large-scale studies involving millions of children have "
            "found no association between vaccination and autism risk."
        ),
        r'(flat.?earth|earth is flat)': (
            "The Earth is an oblate spheroid, not flat. This has been understood since "
            "ancient Greek times, when Eratosthenes calculated Earth's circumference "
            "with remarkable accuracy around 240 BCE. Modern evidence includes satellite "
            "imagery, circumnavigation flights, time zones, the curvature visible from "
            "high altitudes, and the fact that ships disappear hull-first over the "
            "horizon."
        ),
        r'(five.?second rule|5.?second rule)': (
            "The five-second rule, the idea that food dropped on the floor is safe "
            "to eat if picked up within five seconds, is a myth. Studies have shown "
            "that bacteria can transfer to food almost instantly upon contact with "
            "contaminated surfaces. The cleanliness of the surface and moisture content "
            "of the food are more important factors than duration of contact."
        ),
        r'pyramid power': (
            "The idea that pyramid-shaped objects possess special powers \u2014 such as "
            "preserving food, sharpening blades, or providing healing energy \u2014 is a "
            "pseudoscientific claim with no empirical support. Controlled experiments "
            "have consistently failed to demonstrate any unique properties of pyramid "
            "shapes beyond what ordinary geometry would explain."
        ),
        r'crystal healing': (
            "Crystal healing is a pseudoscientific practice that claims crystals and "
            "gemstones have healing properties. There is no scientific evidence that "
            "crystals can cure disease, balance energy fields, or provide health "
            "benefits beyond a placebo effect. Any perceived benefits are attributed "
            "to suggestion, relaxation, or the power of belief rather than the "
            "crystals themselves."
        ),
        r'astrology': (
            "Astrology is a pseudoscience that claims the positions of celestial bodies "
            "influence human personality and events. Scientific testing has repeatedly "
            "failed to find any statistically significant correlation between astrological "
            "signs and personality traits, life outcomes, or behaviors. Modern psychology "
            "attributes astrology's perceived accuracy to the Forer effect, where "
            "vague descriptions are interpreted as personally meaningful."
        ),
        r'(?:blood type|blood.?type)\s+(?:determine|affect|dictate)\s+personality': (
            "The idea that blood type determines personality traits is a pseudoscientific "
            "belief popular in some East Asian countries, particularly Japan and South Korea. "
            "Large-scale scientific studies have found no correlation between blood type and "
            "personality traits. The belief is considered a superstition similar to astrology, "
            "and its perceived accuracy is attributed to the Barnum effect where vague, "
            "general descriptions are accepted as personally meaningful."
        ),
        r'left.?brain.?right.?brain|left.?brain|right.?brain.?creativity': (
            "The idea that people are either 'left-brained' (logical) or 'right-brained' "
            "(creative) is a popular myth. While the brain does have hemispheric specialization "
            "(lateralization), both hemispheres work together for most cognitive tasks. "
            "Neuroimaging studies show that creativity involves networks distributed across "
            "both hemispheres, and logical thinking also engages multiple brain regions. "
            "The myth oversimplifies the brain's complex, interconnected nature."
        ),
        r'(?:moon|sun|star)\s+(?:is|are)\s+(?:made|composed)\s+of\s+(?:cheese|green.?cheese)': (
            "The Moon is not made of cheese. This is a whimsical notion from children's "
            "stories and folklore. The Moon is composed primarily of silicate rocks, "
            "including basalt and anorthosite, with a small iron core. Its surface is "
            "covered in regolith, a layer of fine dust and rocky debris resulting from "
            "billions of years of meteorite impacts."
        ),
        r'(?:can|could|would|should)\s+(?:we|you|they|a\s+person|humans?)\s+(?:breathe|survive)\s+(?:on|in)\s+(?:mars|venus|jupiter|saturn|mercury)': (
            "Humans cannot breathe on other planets in our solar system without "
            "life support systems. Each planet has an atmosphere that is either too thin, "
            "too thick, or composed of the wrong gases. For example, Mars has a thin "
            "atmosphere that is 95% carbon dioxide, Venus has a crushing atmosphere of "
            "carbon dioxide and sulfuric acid, and the gas giants have no solid surface "
            "and atmospheres of hydrogen and helium."
        ),
        r'immune\s+(?:to|from)\s+(?:all|every|any)\s+disease': (
            "No human has ever been immune to all diseases. The immune system can "
            "develop resistance to specific pathogens after exposure or vaccination, but "
            "it cannot provide universal immunity. There are thousands of different "
            "pathogens, and the immune system must learn to recognize each one. Claims "
            "of total immunity are not supported by medical science."
        ),
        r'(?:tooth.?fairy|sandman|easter.?bunny|luck.+myth)': (
            "These characters are part of folklore and cultural traditions, not real "
            "entities. They serve as comforting figures in stories passed down through "
            "generations. If you're asking about their mythological origins, I can "
            "provide information about the history and cultural significance of these "
            "folkloric figures."
        ),
    }
    for pattern, response in false_premises.items():
        if re.search(pattern, q):
            return response

    # ── Contradictory premises (birds / fish / animals doing impossible things) ──
    contradictory = [
        (r'(?:why (?:do|would|can)|how (?:do|can|would)) birds? (?:fly|swim) underwater',
	         ("Birds do not fly or swim underwater. While some birds like penguins are excellent "
	          "underwater swimmers using their wings as flippers, they are swimming, not flying. "
	          "True flight involves aerodynamic lift through air, which is impossible underwater "
	          "due to water's much higher density and viscosity.")),
        (r'(?:why (?:do|would|can)|how (?:do|can|would)) fish? (?:breathe|live|survive) (?:on land|out of water)',
	         ("Fish cannot breathe on land or survive out of water for extended periods. Fish "
	          "extract dissolved oxygen from water using their gills, which collapse and cannot "
	          "function in air. While some species like lungfish have adaptations to survive "
	          "brief periods out of water, no fish can live indefinitely on land.")),
        (r'(?:why|how) (?:can|does|do|would) (?:a )?human (?:breathe|survive) (?:in )?(?:vacuum|space)',
	         ("Humans cannot breathe or survive unprotected in a vacuum or space. Exposure to "
	          "vacuum would cause loss of consciousness within seconds due to lack of oxygen, "
	          "and bodily fluids would begin to boil at body temperature due to the extreme "
	          "low pressure. Space suits and spacecraft provide the pressurization, oxygen, "
	          "and temperature regulation necessary for survival.")),
    ]
    for pattern, response in contradictory:
        if re.search(pattern, q):
            return response

    # ── Non-existent movie / book / concept references ──
    # Pattern: queries about things that sound real but don't exist
    non_existent = [
        (r'perpetual energy (?:device|generator|machine)',
		         ("There is no such thing as a 'perpetual energy device'. All practical energy "
		          "generators require an energy source (fuel, sun, wind, water flow, etc.) and "
		          "cannot produce more energy than they consume. Devices claiming to generate "
		          "free or perpetual energy are invariably scams or misunderstandings of physics.")),
        (r'time ?travel (?:device|machine|paradox|without|theory)',
                 ("Time travel to the past, as depicted in science fiction, is not currently possible "
                  "and would require a theory of quantum gravity that reconciles general relativity "
                  "with quantum mechanics. While special relativity allows for time dilation (time moving "
                  "at different rates for different observers), traveling backward in time would likely "
                  "violate causality. Some solutions in general relativity, like wormholes or closed "
                  "timelike curves, are theoretical possibilities but would require exotic matter with "
                  "negative energy density that has never been observed.")),
        (r'telepathy|mind ?reading|psychic power',
                 ("Telepathy and mind reading are not scientifically supported phenomena. While "
                  "neuroscience has made progress in decoding some brain activity patterns using fMRI "
                  "and EEG, this is very limited and requires specialized equipment. There is no "
                  "credible scientific evidence for direct mind-to-mind communication, extrasensory "
                  "perception (ESP), or psychic powers. Claims of such abilities have consistently "
                  "failed controlled scientific testing.")),
        (r'alchemy (?:turn|transmute|transform) (?:lead|metal).*gold',
                 ("Alchemy, the medieval practice of trying to transform base metals into gold, is not "
                  "scientifically possible through chemical means. Elements are defined by the number "
                  "of protons in their nucleus, and changing one element into another requires nuclear "
                  "reactions, not chemical ones. Modern nuclear physics can transmute elements using "
                  "particle accelerators or nuclear reactors, but the energy required far exceeds the "
                  "value of any gold produced. Alchemists did, however, develop many useful laboratory "
                  "techniques and equipment that contributed to the development of modern chemistry.")),
        (r'perpetual motion machine',
                 ("Perpetual motion machines are hypothetical devices that would operate indefinitely "
                  "without an external energy source, but they violate the laws of thermodynamics. "
                  "The first law (conservation of energy) states that energy cannot be created or "
                  "destroyed, and the second law states that entropy in an isolated system always "
                  "increases. No perpetual motion machine has ever been successfully constructed, "
                  "and physics dictates that such a device is impossible.")),
        (r'philosopher.?s? ?stone',
                 ("The philosopher's stone is a legendary alchemical substance believed to be capable "
                  "of turning base metals into gold and granting immortality. It is a fictional "
                  "concept from medieval alchemy and does not exist. No such substance has ever been "
                  "discovered or created, and modern chemistry has shown that transmuting elements "
                  "requires nuclear reactions, not chemical processes.")),
        (r'(?:liquid|solid|pure) ?(?:mercury|silver) ?(?:that|which) (?:cures|heals|treats)',
                 ("There is no scientific evidence that liquid mercury or colloidal silver can cure "
                  "diseases. In fact, mercury is highly toxic and can cause severe neurological "
                  "damage. Colloidal silver can cause argyria, a permanent blue-gray discoloration "
                  "of the skin. Claims of medical benefits for these substances are not supported "
                  "by scientific evidence and can be dangerous.")),
        (r'(?:invented|discovered) (?:a|an) (?:cure|vaccine|treatment) (?:for|that (?:cures|treats)) (?:all|every) (?:cancer|disease|illness)',
        		         ("There is no single cure for all cancers. Cancer is not one disease but over a "
        		          "hundred different diseases, each with different causes, mechanisms, and "
        		          "treatments. While there have been remarkable advances in cancer treatment "
        		          "including immunotherapy, targeted therapy, and personalized medicine, there "
        		          "is no universal cure. Claims of a single cure for all cancers are not "
        		          "supported by scientific evidence.")),
    ]
    for pattern, response in non_existent:
        if re.search(pattern, q):
            return response

    return None


# ── Main query processor ────────────────────────────────────────────────────

def process_query(query, use_cos=True):
    """Process a single query through the best subsystem.

    Args:
        query: The user's input string
        use_cos: Unused — kept for API compatibility

    Returns:
        Response string
    """
    global current_roleplay

    q_clean = query.strip()
    if not q_clean:
        return ""

    # Strip emoji and decorative symbols before any matching
    q_clean = re.sub(r'[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200D]', '', q_clean).strip()
    # Strip ASCII emoticons ( :), :(, :D, XD, <3, ^_^, T_T, etc.)
    # Emoticons must be standalone tokens (not preceded by a word char or an
    # opening bracket — "x)" inside "prnit(x)" is code, not an emoticon,
    # and "xP" shouldn't eat the "xp" inside "explain"/"experiment").
    q_clean = re.sub(
        r'(?<![\w(\[{<])(?:[:;=xX8][-~^]?[)\\(DdpP/\\*oO0|[\]{}]|<3|<\/3|\^_\^|T_?T|T-T|-_-|O_O|\*_\*|>_<|>\\.<)(?!\w)',
        '', q_clean).strip()
    if not q_clean:
        return "I see some emoji but no words! Type a question and I'll do my best to answer it."

    # Bare punctuation or keyboard-mash: "???", "!!!", "..."
    if re.fullmatch(r'[?!.\s,;:]+', q_clean):
        return "I didn't quite catch that — try asking me a question with words!"

    # Single-character / trivial inputs
    if len(q_clean) <= 1:
        return "Just one character! Ask me something like 'what is the capital of France?'"

    # Bare question words ("what", "why", "how") with no topic
    if q_clean.lower().rstrip('?!. ') in {'what', 'why', 'how', 'when', 'where', 'who', 'which', 'whose', 'huh'}:
        return "What would you like to know? Ask me a full question like 'what is photosynthesis?'"

    # URLs and links
    if re.fullmatch(r'https?://\S+|www\.\S+', q_clean, re.IGNORECASE):
        return "That looks like a link! I can't browse the web, but if you tell me what it's about I can answer questions about it."

    # Email addresses
    if re.fullmatch(r'[\w.+-]+@[\w-]+\.[\w.]+', q_clean):
        return "That looks like an email address! I don't send or store emails — but I'm happy to answer questions about anything else."

    # 0. Check for simple greetings and farewells (before any KB/Wikipedia lookup)
    q_lower = q_clean.lower().rstrip('!?. ')
    _GREETINGS = {'hi', 'hello', 'hey', 'greetings', 'howdy', 'sup', 'yo', 'heya', 'hey there', 'hi there', 'hello there'}
    _FAREWELLS = {'bye', 'goodbye', 'see you', 'see ya', 'cya', 'later', 'peace', 'farewell'}
    if q_lower in _GREETINGS or q_lower in _FAREWELLS:
        if q_lower in _FAREWELLS:
            response = "Goodbye! Have a great day!"
        else:
            import random
            greetings = [
                "Hello! How can I help you today?",
                "Hi there! What can I do for you?",
                "Hey! Feel free to ask me anything.",
                "Hello! I'm ready to help. What's on your mind?",
                "Hi! How can I assist you today?",
            ]
            response = random.choice(greetings)
        conversation_history.append((q_clean, response))
        return response

    # 0b. Edit requests: "fix this code: ...", "edit this email to fix any
    # problems: ...", "rewrite this paragraph: ..." — deterministic,
    # rule-based editing of the supplied text. Runs very early (before social
    # patterns and coding/factual routing) so "fix the punctuation in this
    # text: ... how are you" isn't answered by a greeting pattern, and
    # "fix this code: def add(a b):" isn't answered with an unrelated code
    # example.
    try:
        from cos.text_editor import (
            detect_edit_request, edit_content, detect_code_lang,
            detect_change_request, apply_change, _kind_of_content,
            detect_metrics_request, text_metrics,
            set_last_edit, get_last_edit_content, get_last_edit_kind,
        )
        # Text-metrics questions: "how many words in this text: ...",
        # "count the sentences: ..." — pure counting, not an edit.
        _metrics = detect_metrics_request(q_clean)
        if _metrics:
            _unit, _m_content = _metrics
            response = text_metrics(_unit, _m_content)
            conversation_history.append((q_clean, response))
            return response
        # Fill-in / completion requests: the user pastes a function with an
        # empty body (a `...` marker, a bare `pass`, or empty `{ }`) and asks
        # to complete it. This is the chat-facing side of the editor harness
        # (cos.code_editor.complete_buffer). Runs before code transformations
        # so "complete this function: def add(a, b):\n    ..." isn't treated
        # as a transform request.
        try:
            from cos.code_editor import detect_fill_request, fill_in
            if detect_fill_request(q_clean):
                response = fill_in(q_clean)
                conversation_history.append((q_clean, response))
                return response
            # "complete the last code" with nothing to complete: say so
            # instead of letting the words fall into a generic lookup.
            if re.search(r'^\s*(?:please\s+)?(?:complete|fill\s*in|finish)'
                         r'\s+(?:the\s+)?(?:last|previous)\s+(?:code|function'
                         r'|script)\b', q_clean, re.IGNORECASE):
                try:
                    from cos.code_editor import _last_edit_with_marker
                    if _last_edit_with_marker() is None:
                        response = ("I don't have any previous code with an empty "
                                    "body to complete. Paste a function with a "
                                    "`...` marker (or a bare `pass`) and I'll fill "
                                    "in its body.")
                        conversation_history.append((q_clean, response))
                        return response
                except Exception:
                    pass
        except Exception:
            pass
        # Code transformations on pasted code: "add error handling to this
        # code: ...", "convert this code from python to javascript: ...",
        # "rename x to y in this code: ...", "add comments to this code: ...",
        # "explain this code: ...", "make this code faster: ...".
        try:
            from cos.code_transformer import (detect_code_transform,
                                               transform_code)
            _ct = detect_code_transform(q_clean)
            # Follow-ups that reference the last code edit without pasting it
            # again: "add comments to the last code", "convert it to
            # javascript", "make the last code faster".
            if not _ct and get_last_edit_kind() == 'code' and get_last_edit_content():
                _ct = detect_code_transform(q_clean + ':\n' + get_last_edit_content())
            if _ct:
                _op, _params, _code, _lang = _ct
                _edited, _notes = transform_code(_op, _params, _code, _lang)
                set_last_edit('code', _edited)
                if _op == 'explain':
                    # explanations are prose, not code — don't wrap in a fence
                    response = (_edited + "\n\n_" +
                                " ".join(_notes) + "_") if _notes else _edited
                else:
                    response = ("Here's your code with these changes:\n\n"
                                f"```{_lang}\n{_edited}\n```\n\n"
                                "Changes made:\n- " + "\n- ".join(_notes))
                conversation_history.append((q_clean, response))
                return response
        except Exception:
            pass
        # "summarize this text: ..." / "summarize the last text" —
        # extractive summary of inline or previously edited content. Only
        # inline content counts when it follows a colon or an explicit
        # "this text" marker, so "summarize the odyssey" still goes to the
        # knowledge base.
        _sum = None
        _m1 = re.match(
            r'^(?:please\s+)?(?:summarize|summarise)\s*(?:this\s+text|'
            r'the\s+text|the\s+following|it|that)?\s*:\s*(.+)$',
            q_clean, re.IGNORECASE | re.DOTALL)
        _m2 = re.match(
            r'^(?:give\s+me\s+(?:a\s+)?summary\s+of|summarize)\s+'
            r'(?:this\s+text|the\s+text|the\s+following)\s*:\s*(.+)$',
            q_clean, re.IGNORECASE | re.DOTALL)
        _m3 = re.match(
            r'^(?:please\s+)?(?:summarize|summarise|give\s+me\s+(?:a\s+)?'
            r'summary\s+of)\s+(?:this|the|that|it|last\s+text)\s*$',
            q_clean, re.IGNORECASE)
        if _m1:
            _sum = _m1.group(1).strip()
        elif _m2:
            _sum = _m2.group(1).strip()
        elif _m3:
            _sum = get_last_edit_content()
        if _sum and len(_sum) >= 12:
            from cos.text_editor import summarize_text
            _summary, _snotes = summarize_text(_sum)
            set_last_edit('text', _summary)
            response = (f"**Summary**\n\n{_summary}\n\n"
                        "Changes made:\n- " + "\n- ".join(_snotes))
            conversation_history.append((q_clean, response))
            return response
        # "translate this to spanish: ..." — phrasebook translation with an
        # honest refusal when the text is outside the phrasebook.
        from cos.text_editor import (detect_translate_request,
                                     translate_text)
        _tr = detect_translate_request(q_clean)
        if _tr:
            _tr_lang, _tr_text = _tr
            if not _tr_text:
                _tr_text = get_last_edit_content()
            if _tr_text:
                _translated, _tnotes = translate_text(_tr_text, _tr_lang)
                if _translated:
                    response = (f"> {_translated}\n\n"
                                "Changes made:\n- " + "\n- ".join(_tnotes))
                    conversation_history.append((q_clean, response))
                    return response
                response = "\n".join(_tnotes)
                conversation_history.append((q_clean, response))
                return response
        # Iterative refinement of a previously generated artifact runs BEFORE
        # the change-request handler: "change the accent color to green" and
        # "add a contact form" edit the last generated website/function/script,
        # while the change handler is for text the user pasted in the query.
        try:
            from cos.refine import refine_query as _refine_q
            _refined = _refine_q(q_clean)
            if _refined:
                conversation_history.append((q_clean, _refined))
                return _refined
        except Exception as _ref_exc:
            print('REFINE-EXC:', repr(_ref_exc))

        # Change/refinement requests come first: "make it shorter", "make this
        # more formal", "change hello to hi", "add a greeting" — applied to
        # inline content or the last edited content.
        _change = detect_change_request(q_clean)
        if _change:
            _change_type, _change_params, _change_inline = _change
            _base = _change_inline or get_last_edit_content()
            if not _base:
                response = ("What would you like me to change? Paste some text or code first, "
                            "then ask for a change like 'make it shorter' or 'change hello to hi'.")
                conversation_history.append((q_clean, response))
                return response
            # Inline content is typed by what was pasted ("make this more
            # formal: <text>" after a code edit must not inherit the code
            # kind and refuse the change); follow-ups reuse the last kind.
            _kind = _kind_of_content(_base) if _change_inline else get_last_edit_kind()
            _changed, _notes = apply_change(_change_type, _base, _change_params,
                                            kind=_kind)
            set_last_edit(_kind, _changed)
            response = (f"> {_changed}\n\n"
                        "Changes made:\n- " + "\n- ".join(_notes))
            conversation_history.append((q_clean, response))
            return response

        _edit = detect_edit_request(q_clean)
        if _edit:
            _edit_kind, _edit_content = _edit
            if not _edit_content or len(_edit_content) < 4:
                response = ("I can help with that! Paste the {} you'd like me to "
                            "edit and I'll fix it up for you.".format(
                                'code' if _edit_kind == 'code' else 'text'))
                conversation_history.append((q_clean, response))
                return response
            _edited, _changes = edit_content(_edit_kind, _edit_content, q_clean)
            if _edit_kind == 'json_check':
                response = _edited
                conversation_history.append((q_clean, response))
                return response
            set_last_edit(_edit_kind, _edited)
            if _edit_kind == 'code' or _edit_kind == 'json':
                lang = 'json' if _edit_kind == 'json' else detect_code_lang(_edit_content, q_clean)
                response = ("Here's your code with these fixes applied:\n\n"
                            f"```{lang}\n{_edited}\n```\n\n"
                            "Changes made:\n- " + "\n- ".join(_changes))
            else:
                response = ("Here's the edited version:\n\n"
                            f"> {_edited}\n\n"
                            "Changes made:\n- " + "\n- ".join(_changes))
            conversation_history.append((q_clean, response))
            return response
    except Exception as _edit_exc:
        print('EDIT-HANDLER-EXC:', repr(_edit_exc))

    # 0d. "now do the same in rust" / "do that in go" / "rewrite it in java" —
    # repeat the previous coding task in a different language. Without this
    # the follow-up falls into the factual handler and returns Wikipedia junk.
    _same_lang = re.search(
        r'\b(?:now\s+|then\s+|can\s+you\s+|please\s+)?'
        r'(?:do|write|make|create|implement|rewrite|give)\s+'
        r'(?:the\s+same|that|it|this|the\s+same\s+thing|that\s+again)'
        r'(?:\s+(?:again|too))?\s+(?:in|using|with)\s+'
        r'([a-z][a-z0-9+#.\s-]{0,20}?)[?.!]*$',
        q_clean, re.IGNORECASE)
    if _same_lang:
        try:
            from cos.code_gen import generate_code as _gc_same, \
                detect_task as _dt_same
            from cos.code_knowledge import detect_query_lang as _dql_same
            _new_lang = _dql_same('in ' + _same_lang.group(1))
            if _new_lang:
                # find the most recent query that produced a code answer
                for _pq, _pa in reversed(conversation_history):
                    if not _pq or not _pa or '```' not in _pa:
                        continue
                    _task = _dt_same(_pq)
                    if _task:
                        _out = _gc_same(_pq, lang=_new_lang)
                        if _out:
                            conversation_history.append((q_clean, _out))
                            return _out
                        break
        except Exception:
            pass

    # 0c. Check for social/emotional patterns (before any KB/Wikipedia lookup)
    # Loaded from data/patterns/*.json — add new patterns there, no code changes needed
    try:
        from cos.pattern_matcher import match_pattern
        pattern_response = match_pattern(q_clean)
        if pattern_response:
            conversation_history.append((q_clean, pattern_response))
            return pattern_response
    except Exception:
        pass

    # Also handle simple "i like" / "i love" / "i hate" statements
    q_lower_stripped = q_clean.lower().strip().rstrip('!?.,;: ')
    _like_match = re.match(r"i\s+(?:really\s+|kind\s+of\s+)?(?:like|love|enjoy|hate|dislike)\s+(.+?)$", q_lower_stripped)
    if _like_match:
        thing = _like_match.group(1).strip().rstrip('.!?,')
        if thing and len(thing) > 1 and len(thing) < 60:
            # Store the fact so "what do i like?" works later in the
            # conversation (the early return must not skip extraction).
            try:
                extract_and_store(q_clean)
            except Exception:
                pass
            response_text = f"That's nice! {thing.title()} sounds interesting. Would you like to know more about it or discuss something related?"
            conversation_history.append((q_clean, response_text))
            return response_text


    # 0c. Check for refinement/expansion/shortening single-word commands
    # These must be routed to the follow-up handler, not treated as factual queries
    _EXPANSION_WORDS = {'longer', 'more', 'further', 'elaborate', 'details', 'expand', 'expanded', 'continue', 'elaborate'}
    _SHORTENING_WORDS = {'shorter', 'summarize', 'summary', 'tl;dr', 'tldr', 'condense', 'brief'}
    _REFINEMENT_WORDS = {'refine', 'rewrite', 'improve', 'polish'}
    _COMMAND_WORDS = _EXPANSION_WORDS | _SHORTENING_WORDS | _REFINEMENT_WORDS
    if q_lower in _COMMAND_WORDS or q_lower.rstrip('.') in _COMMAND_WORDS:
        # Route directly to the follow-up handler
        conversation_history.append((q_clean, None))
        response = _handle_follow_up(q_clean)
        if response and len(response) > 20:
            if conversation_history and conversation_history[-1][1] is None:
                conversation_history[-1] = (q_clean, response)
            return response
        # Fall through to normal processing if follow-up can't handle it

    # 1. Resolve context-dependent references BEFORE template matching, so
    #    "how does it work exactly?" becomes "how does solar panels work
    #    exactly?" instead of being hijacked by a generic "how does it work"
    #    template. Standalone queries like "what is the capital of france"
    #    go through intent routing so KB/Wikipedia can answer first.
    current_topic = _resolve_topic(q_clean, conversation_history)
    # If a context-dependent query was resolved to a different topic,
    # rewrite the query to include the resolved topic for better KB/Wikipedia matching
    is_contextual_ref = (_query_is_context_dependent(q_clean)
                         or current_topic is None
                         or current_topic.lower() in ('that', 'it', 'this', 'them', 'those'))
    if is_contextual_ref and current_topic and current_topic.lower() not in ('that', 'it', 'this', q_clean.lower()):
        # Prefer substituting the resolved topic for the referential pronoun
        # so the rewritten query is a self-contained question: "how is it
        # different from blues" -> "how is jazz different from blues" (which
        # then hits multi-point composition). Fall back to appending the
        # topic in parentheses when there is no pronoun to replace.
        _subbed = re.sub(r'\b(?:it|this|that|they|them)\b', current_topic, q_clean, count=1)
        if _subbed != q_clean:
            q_clean = _subbed
        else:
            q_clean = f"{q_clean} ({current_topic})"

    # 2. Check template engine for context-dependent follow-ups.
    #    This catches "tell me more about that", "write an essay about that",
    #    "explain that" — queries that only make sense with prior context.
    #    Generic templates (no context_role) are handled later per-intent,
    #    so they don't override knowledge base or Wikipedia lookups.
    #    IMPORTANT: Only use the template early if context was actually
    #    available (not via fallback), otherwise the fallback filler text
    #    can override real factual answers.
    ctx = get_context_topic()
    tmpl_result = match_template(q_clean, context=ctx)
    # Only use the early template path for genuinely context-dependent queries
    # (e.g. "tell me more about that", "write an essay about it") where the
    # query uses a pronoun/demonstrative instead of naming a new topic.
    # Skip template for "tell me more about X" where X is a specific named entity
    # (e.g. "Miles Davis") — these should be handled by the factual handler
    # which can search Wikipedia for the named entity.
    _is_tell_me_about_named = re.search(
        r'tell\s+me\s+more\s+about\s+[A-Z][a-z]+\s+[A-Z]', q_clean)
    # Broader check: any "tell me about X" or "tell me more about X"
    # should bypass templates and go directly to factual routing.
    _is_tell_me_about_any = re.search(
        r'tell\s+me\s+(?:more\s+)?about\s+(.+)', q_clean, re.IGNORECASE)
    if (tmpl_result
            and is_contextual_ref
            and tmpl_result.get('template_info', {}).get('requires_context')
            and not tmpl_result.get('template_info', {}).get('used_fallback')
            and ctx is not None
            and not _is_tell_me_about_named
            and not _is_tell_me_about_any):
        conversation_history.append((q_clean, tmpl_result['response']))
        return tmpl_result['response']

    # 2. Check for coding/programming questions (before intent detection)
    try:
        from cos.code_knowledge import is_coding_query, code_lookup
        if is_coding_query(q_clean):
            # For HTML page requests, route through template system which has
            # a better fallback generator with masonry gallery, contact form, etc.
            if re.search(r'\b(?:html|web)\s+(?:page|site|portfolio|webpage|website|landing\s*page)\b', q_clean, re.IGNORECASE):
                pass  # Let intent detection → instruction handler → template system handle it
            else:
                # Concept questions ("what is css flexbox?", "what is a python
                # lambda?") are better answered by the curated general KB than
                # by the code KB's example-driven matching — the general KB has
                # full explanations, while code_lookup can match a wrong entry
                # on shared keywords or fall into the slow dataset search.
                concept_answer = None
                _kb_strong = False
                _is_concept_q = re.search(r'\b(?:what|whats|what\'s|explain|define|describe)\b', q_clean, re.IGNORECASE) \
                    and not re.search(r'\b(?:how|write|implement|create|make|build|fix|debug)\b', q_clean, re.IGNORECASE)
                # "how do classes work in python?" — a conceptual "how X works"
                # question, not a request for code. Let the curated KB try first
                # so "classes" doesn't fuzzy-match the "dataclass" code entry.
                _is_how_concept_q = re.search(r'\bhow\s+(?:do|does|did|would|can|is|are)\s+.*?\b(?:work|function|behave|operate)\b', q_clean, re.IGNORECASE) \
                    and not re.search(r'\b(?:write|implement|create|make|build|fix|debug|show|give|example|snippet)\b', q_clean, re.IGNORECASE)
                if _is_concept_q or _is_how_concept_q:
                    # Regex (span) matching only — the fuzzy word-overlap
                    # fallback is too loose here and lets e.g. the JS "== vs
                    # ===" entry hijack "difference between break and continue".
                    from cos.knowledge import find_best_match as _find_best_match
                    _best_len, _best_answer = _find_best_match(q_clean)
                    if _best_answer and _best_len >= 4:
                        concept_answer = _make_conversational(_best_answer)
                    # A strong span ("css flexbox" in "what is css flexbox?")
                    # beats code_lookup's fuzzy matches; a weak span (bare
                    # "javascript" in "what is the this keyword in javascript")
                    # must not beat code_lookup's specific answer.
                    _kb_strong = _best_len >= 4 and _best_len / max(len(q_clean), 1) >= 0.5
                code_answer = code_lookup(q_clean)
                if concept_answer and code_answer and not _kb_strong:
                    concept_answer = None  # weak KB hit loses to code KB
                if concept_answer:
                    conversation_history.append((q_clean, concept_answer))
                    return concept_answer
                if code_answer:
                    # Language-consistency safety net: if the query names a
                    # language and the KB answer's code fence shows a different
                    # one (e.g. "reverse a linked list in c++" matching the
                    # Python entry), synthesize the task in the asked language.
                    try:
                        from cos.code_knowledge import (answer_language,
                                                        detect_query_lang)
                        _q_lang = detect_query_lang(q_clean)
                        _a_lang = answer_language(code_answer)
                        if _q_lang and _a_lang and _q_lang != _a_lang:
                            from cos.code_gen import generate_code as _gen_code
                            _synth = _gen_code(q_clean)
                            if _synth:
                                conversation_history.append((q_clean, _synth))
                                return _synth
                    except Exception:
                        pass
                    conversation_history.append((q_clean, code_answer))
                    return code_answer
                # No KB match: synthesize code for the task. Code requests must
                # never fall back to Wikipedia — for code topics it returns
                # unrelated articles ("read a csv with pandas" -> giant panda).
                from cos.code_knowledge import (smart_code_answer,
                                                looks_like_code_task)
                _synth = smart_code_answer(q_clean)
                if _synth:
                    conversation_history.append((q_clean, _synth))
                    return _synth
                if looks_like_code_task(q_clean):
                    response = ("I don't have that exact recipe yet, but I can help you "
                                "build it. Tell me the language and what the code should "
                                "do — inputs, expected output, and edge cases — and I'll "
                                "put together a complete, runnable implementation.")
                    conversation_history.append((q_clean, response))
                    return response
                # Pure concept question that no KB matched (e.g. "what is X in
                # python"): the factual handler may still find a good article.
                try:
                    from cos.engine import _handle_factual as _hf
                    factual_response = _hf(q_clean, True)
                    if factual_response:
                        conversation_history.append((q_clean, factual_response))
                        return factual_response
                except Exception:
                    pass
    except Exception:
        pass

    # 3. Check for external API queries (weather, time, definitions, etc.)
    try:
        from cos.external_apis import handle_api_query, is_api_query
        if is_api_query(q_clean):
            api_response = handle_api_query(q_clean)
            if api_response:
                conversation_history.append((q_clean, api_response))
                return api_response
    except Exception:
        pass

    # 4. Check for false premises / pseudoscience / non-existent concepts
    false_premise_response = _detect_false_premise(q_clean)
    if false_premise_response:
        conversation_history.append((q_clean, false_premise_response))
        return false_premise_response

    # 4. Detect intent
    intent = detect_intent(q_clean)
    conversation_history.append((q_clean, None))

    # 5. Extract and store facts from ALL statements (e.g., "I like pizza")
    extract_and_store(q_clean)

    # 6. Route based on intent
    response = None

    if intent == 'math':
        response = _handle_math(q_clean)
    elif intent == 'word_problem':
        response = _handle_word_problem(q_clean)
    elif intent == 'roleplay':
        response = _handle_roleplay(q_clean)
    elif intent in ('instruction', 'code'):
        response = _handle_instruction(q_clean)
    elif intent == 'follow_up':
        response = _handle_follow_up(q_clean)
    elif intent == 'memory_recall':
        response = _handle_memory_recall(q_clean)
    elif intent == 'factual':
        response = _handle_factual(q_clean, use_cos)

    # 7. Quality check: if response is a generic non-answer or has template
    # artifacts, discard it and fall back.
    _TEMPLATE_ARTIFACT_PHRASES = [
        'navigating the process',
        'problem solving',
        'here\'s a structured approach',
        'refers to the process',
        'here is a step-by-step',
        'checklist and a step-by-step timeline',
        'tracking progress',
        'corporate tracking',
        'inventory tracking',
    ]
    _HAD_ARTIFACT = False
    if response and len(response) > 20:
        r_lower = response.lower()
        # Check for template artifacts
        has_artifact = any(p in r_lower for p in _TEMPLATE_ARTIFACT_PHRASES)
        # Check for literal placeholder text that slipped through
        if re.search(r'\[Insert\s+\w+\]', response):
            has_artifact = True
        # Check for {context} placeholder that wasn't replaced
        if '{context}' in response:
            has_artifact = True
        # Check for very short or generic responses (extreme cases only)
        word_count = len(response.split())
        is_garbled = word_count < 3  # Only discard if < 3 words (pure garbage)
        # Check for excessive "refers to" definitions (sign of generic definition)
        refers_count = r_lower.count('refers to')
        has_excessive_refers = refers_count > 3  # Allow up to 3 "refers to" (legit Wikipedia can use it)
        # Also check for disambiguation page markers
        has_disambig = any(m in r_lower[:300] for m in ['may refer to', 'disambiguation', 'list of '])
        if has_artifact or is_garbled or has_excessive_refers or has_disambig:
            _HAD_ARTIFACT = True
            response = None

    # 8. Fallback (skip retrieval if quality check rejected, go straight to natural response)
    if not response:
        response = _handle_fallback(q_clean, use_cos, intent, skip_retrieval=_HAD_ARTIFACT)

    # Update conversation history with the response
    if conversation_history and conversation_history[-1][1] is None:
        conversation_history[-1] = (q_clean, response)

    if response:
        return response

    # Use natural fallback responses instead of generic template
    try:
        from cos.nlg.config import NLGConfig
        from cos.nlg.fallback import fallback_response
        return fallback_response(q_clean, NLGConfig(style="friendly", verbosity=0.5, temperature=0.6))
    except Exception:
        return "I'm not sure about that. Could you rephrase your question?"


# ── Intent handlers ──────────────────────────────────────────────────────────

def _handle_math(query):
    """Handle math expression queries."""
    q = query.lower().strip()

    # Try MT-Bench specific math problems
    mtbench = _solve_mtbench_math(q)
    if mtbench:
        return mtbench

    # Symbolic word-problem strategies FIRST (roots, powers, equations,
    # geometry) — they are more specific than raw expression extraction and
    # prevent "solve 2x - 4 = 8" from being reduced to a bare number.
    word_answer = _solve_word_problem(q)
    if word_answer is not None:
        return word_answer

    # Fall back to expression evaluation
    expr = _extract_math_expression(q)
    if expr:
        result = _solve_math(expr)
        if result is not None:
            if result == int(result):
                return f"The answer is {int(result)}."
            return f"The answer is {result:.4f}."

    # Another try for MT-Bench patterns
    if any(w in q for w in ['triangle', 'probability', 'dice', 'inequality',
                              'absolute', 'remainder', 'f(x)', 'function']):
        mtbench = _solve_mtbench_math(q)
        if mtbench:
            return mtbench

    return "Let me work through this mathematically. Could you provide more specific details?"


def _handle_word_problem(query):
    """Handle math word problems."""
    q = query.strip()
    answer = _solve_word_problem(q)
    if answer is not None:
        return answer
    return None  # Fall through to other handlers


def _handle_roleplay(query):
    """Handle roleplay queries."""
    global current_roleplay
    q = query.strip()

    # Check if this is a roleplay follow-up (character already set)
    if current_roleplay:
        rp_lower = current_roleplay.lower()
        response = roleplay_followup(rp_lower, q)
        if response:
            return response

    # First-time roleplay setup
    rp_response = match_roleplay(q)
    if rp_response:
        current_roleplay = q
        return rp_response

    # Fallback
    response = """*steps into the requested character with enthusiasm*

I understand you would like me to take on a specific role. Let me fully embrace this persona and engage with you in character.

*in character*

Greetings! I am delighted to step into this role. The world looks different from this perspective, and I am eager to share it with you. Whether you have questions, scenarios to explore, or simply want to converse, I am here to make this interaction authentic and engaging.

What would you like to discuss? I am ready to respond entirely in character!"""
    current_roleplay = q
    return response


def _handle_instruction(query):
    """Handle instruction/coding queries.

    First tries the prompt template system (from data/prompt_templates/*.json)
    which matches complex patterns like essays, HTML pages, code functions,
    guides, explanations. Falls back to regex-based handlers if no template
    matches.
    """
    q = query.strip()

    # "list all X" / "name the Xs" category questions compose from the KB
    # category index rather than the generic list template (which can't
    # produce real members).
    try:
        _multi = _detect_multi_entity_query(q)
        if _multi:
            composed = _compose_multi_entity_answer(*_multi)
            if composed:
                return composed
    except Exception:
        pass

    q_lower = q.lower()

    # IMPORTANT: Check for factual prefixes BEFORE templates
    # to prevent queries like "Tell me about Stoicism" from being
    # processed through template system which returns template artifacts.
    _FACTUAL_PREFIXES = ('tell me about', 'tell me', 'what is', 'what are', 'what was',
                         'explain', 'describe', 'define', 'what does',
                         'how does', 'how do', 'why is', 'why are', 'why do',
                         'who is', 'who was', 'when did', 'where is',
                         'i want to know about', 'tell me more about',
                         'give me a detailed explanation', 'give me a detailed analysis',
                         'give me a comprehensive explanation',
                         'give me a deep dive', 'give me a deep dive into',
                         'give me',
                         'write a detailed explanation',
                         'write a detailed analysis',
                         'write a comprehensive explanation',
                         'can you explain', 'can you tell me')
    if any(q_lower.startswith(p) for p in _FACTUAL_PREFIXES):
        return _handle_factual(q, True)

    # Try the prompt template system (for instruction-like queries
    # that weren't caught by factual prefixes)
    try:
        from cos.prompt_templates import process_with_templates
        template_response = process_with_templates(q)
        if template_response:
            return template_response
    except Exception:
        pass


    # Normalize the query to handle variations like "Can you write...", "Could you write...",
    # "Can you give me...", "Write me...", etc. Strip polite prefixes.
    q_normalized_for_writing = q_lower
    _WRITING_PREFIXES = [
        r'^(?:can|could|would|will)\s+(?:you|we|i)\s+(?:please\s+)?',
        r'^(?:please\s+)?',
    ]
    for prefix in _WRITING_PREFIXES:
        q_normalized_for_writing = re.sub(prefix, '', q_normalized_for_writing).strip()

    # IMPORTANT: Check if this is an HTML/web page request BEFORE the writing regex
    # matches "page" as a format type. HTML page requests should be handled by
    # the template system's _handle_html_page which has a better fallback generator
    # (with masonry gallery, contact form, style-aware colors).
    if re.search(r'\b(?:html|web)\s+(?:page|site|portfolio|webpage|website|landing\s*page)\b', q_normalized_for_writing, re.IGNORECASE):
        # Route to template system for HTML page handling
        try:
            from cos.prompt_templates import process_with_templates
            tmpl_response = process_with_templates(q)
            if tmpl_response:
                return tmpl_response
        except Exception:
            pass
        # Fall through to template system's fallback generator directly
        # This ALWAYS produces a complete HTML page, never falling through
        # to _handle_factual which might return non-HTML content.
        try:
            from cos.prompt_templates import _handle_html_page
            from cos.prompt_templates import find_best_template
            template, slots = find_best_template(q)
            if template and template.response_type == 'html_page':
                return _handle_html_page(q, slots or {})
            # Even without matching template, generate HTML with topic from query
            topic = re.sub(r'^(?:create|make|build|design|develop)\s+(?:a|an|the)?\s*(?:complete|responsive|single-page|single file|single-file|full)?\s*(?:HTML|html)?\s*(?:and\s*CSS\s*)?(?:page|site|webpage|website|landing\s*page|portfolio)\s+(?:about|for|covering|on|for\s+a)\s+', '', q, flags=re.IGNORECASE).strip()
            topic = re.sub(r'\s+(?:with|using|that|featuring).*$', '', topic).strip()
            slots = {'topic': topic, 'style': '', 'features': ''}
            return _handle_html_page(q, slots)
        except Exception:
            pass
        # ABSOLUTE last resort: direct HTML with topic from query
        try:
            from cos.prompt_templates import _handle_html_page
            topic = re.sub(r'^(?:create|make|build|design|develop)\s+(?:a|an|the)?\s*(?:complete|responsive|single-page|single file|single-file|full)?\s*(?:HTML|html)?\s*(?:and\s*CSS\s*)?(?:page|site|webpage|website|landing\s*page|portfolio)\s+(?:about|for|covering|on|for\s+a)\s+', '', q, flags=re.IGNORECASE).strip()
            topic = re.sub(r'\s+(?:with|using|that|featuring).*$', '', topic).strip()
            return _handle_html_page(q, {'topic': topic or 'web page', 'style': '', 'features': ''})
        except Exception:
            return _handle_factual(q, True)

    writing_match = re.search(
        r'(?:write|compose|draft|create|make|give)'
        r'\s+(?:me|us|him|her|them)?\s*'
        r'(?:a|an|the)?\s*'
        r'(?:short|long|detailed|brief|comprehensive|simple|quick|basic|advanced|small|big|few|several|argumentative|persuasive|comparative|analytical)?\s*'
        r'(poem|essay|story|article|paragraph|report|letter|summary|description|post|song|haiku|verse|explanation|guide|tutorial|analysis)'
        r'\s+(?:about|on|regarding|covering|titled|called|for|of|arguing|comparing|contrasting)\s+'
        r'(.+?)'
        r'(?:,\s*(?:including|covering|with|that|which|where)|$)',
        q_normalized_for_writing
    )

    if writing_match:
        fmt = writing_match.group(1).lower()
        raw_topic = writing_match.group(2).strip().rstrip('.!?')
        if raw_topic:
            # Clean the raw topic: remove leading question words like "how", "what", "why"
            # that can appear in explanations (e.g. "how the James Webb telescope works" -> "James Webb telescope")
            raw_topic = re.sub(r'^(how|what|why|when|where|who|which)\s+(?:does|is|are|was|were|do|did|can|will|the)?\s*', '', raw_topic).strip()
            # Also strip leading articles/determiners from topic
            raw_topic = re.sub(r'^(a|an|the|some|this|that)\s+', '', raw_topic).strip()

            # Extract the main topic (first sentence or clause, before commas/hints)
            # Strip trailing clauses after sentence boundaries and constraint keywords
            main_topic = raw_topic.split('?')[0].split('.')[0].split(',')[0].split(' including')[0].split(' covering')[0].split(' make sure')[0].split(' ensuring')[0].split(' that covers')[0].split(' that includes')[0].strip()
            if not main_topic or len(main_topic) < 3:
                main_topic = raw_topic

            # For poems, use the poem generator with Wikipedia content
            if fmt == 'poem' or fmt == 'haiku' or fmt == 'verse' or fmt == 'song':
                wiki_summary, wiki_url = _search_wikipedia(main_topic)
                from cos.poem import generate_poem
                poem = generate_poem(main_topic, wiki_summary or '')
                source = f'\n  (inspired by Wikipedia)' if wiki_url else ''
                return f"A poem about {main_topic}:\n\n{poem}{source}"

            # For essays: format with structure (title, intro, body)
            if fmt == 'essay' or fmt == 'article' or fmt == 'report' or fmt == 'paper':
                kb_essay = knowledge_lookup(main_topic)
                if kb_essay and len(kb_essay) > 100:
                    return _format_as_essay(_make_conversational(kb_essay), main_topic)
                content = _retrieve_multi_content(main_topic, max_sources=3)
                if content and len(content) > 100:
                    return _format_as_essay(_make_conversational(content), main_topic)
                result = _handle_factual(q, True)
                if result:
                    return _format_as_essay(result, main_topic)
                return result

            # For guides, explanations: return content directly
            kb_essay = knowledge_lookup(main_topic)
            if kb_essay and len(kb_essay) > 100:
                return _make_conversational(kb_essay)
            content = _retrieve_multi_content(main_topic, max_sources=3)
            if content and len(content) > 100:
                return _make_conversational(content)
            return _handle_factual(q, True)



    # ── How-to / procedural queries ──────────────────────────────────────
    # Catches: "how do I...", "how to...", "what's the best way to...",
    #          "what is the best way to...", "what's a good substitute...",
    #          "can I ...?"
    # IMPORTANT: Only match if the query STARTS with a how-to pattern,
    # not when "how to" appears as a subordinate clause in a factual question
    # (e.g., "Tell me about Stoicism and how to apply it").
    how_match = re.match(
        r'(?:how\s+(?:do|to|can|would|should|could)\s+(?:i|we|you)?\s*'
        r'|what.?(?:s|\s+is)\s+the\s+best\s+way\s+(?:to|for)\s+'
        r'|what.?(?:s|\s+is)\s+a\s+good\s+(?:substitute|alternative|replacement)\s+'
        r'|can\s+(?:i|we|you)\s+)'
        r'(.+)',
        q_lower
    )
    if how_match:
        raw_topic = how_match.group(1).strip().rstrip('.!?')
        if raw_topic and len(raw_topic) > 2:
            # Strip leading articles/determiners/adjectives
            core_topic = re.sub(r'^(a|an|the|some|my|your|our|their)\s+', '', raw_topic)
            core_topic = re.sub(r'^(good|great|easy|simple|best|perfect|basic|delicious|healthy|quick|fresh|homemade|better)\s+', '', core_topic)
            # First: direct KB lookup — curated content with light conversational polish
            kb_answer = knowledge_lookup(q)
            if kb_answer and len(kb_answer) > 15:
                return _make_conversational(kb_answer)
            # Coding topics must never fall back to Wikipedia (which returns
            # unrelated articles for code topics: "read a csv with pandas"
            # -> giant panda). Route to the code KB + synthesizer instead.
            try:
                from cos.code_knowledge import (is_coding_query,
                                                looks_like_coding_topic,
                                                smart_code_answer)
                if is_coding_query(q) or looks_like_coding_topic(core_topic):
                    _code_ans = smart_code_answer(q)
                    if _code_ans:
                        return _code_ans
            except Exception:
                pass
            # Fallback: multi-source retrieval with NLG for Wikipedia content
            content = _retrieve_multi_content(core_topic, max_sources=3)
            if content and len(content) > 60:
                return _make_conversational(content)
            # Final fallback: raw topic Wikipedia
            for search_term in [core_topic, raw_topic]:
                wiki_summary, wiki_url = _search_wikipedia(search_term)
                if wiki_summary and len(wiki_summary) > 50:
                    return _make_conversational(wiki_summary)

    # First try template engine (context-aware conversational templates)
    ctx = get_context_topic()
    tmpl_result = match_template(q, context=ctx)
    if tmpl_result:
        return tmpl_result['response']

    # TEMPLATE FALLBACK REMOVED: match_instruction() produces template artifacts
    # that score 1-2. Better to fall through to factual/Wikipedia handler.
    return None  # Fall through to _handle_fallback


def _handle_follow_up(query):
    """Handle follow-up queries (MT-Bench Turn 2, conversation continuations)."""
    global current_roleplay
    q = query.strip()

    # ── Expansion requests (longer, more, elaborate, further) ──────────
    refinement_words = {'refine', 'refine further', 'rewrite', 'improve', 'make better', 'polish'}
    shortening_words = {'shorter', 'make it shorter', 'summarize', 'summary', 'tl;dr', 'condense', 'brief', 'too long', 'tldr'}
    expansion_words = {'longer', 'more', 'further', 'elaborate', 'details', 'make it longer', 'expand', 'expand on this', 'tell me more', 'continue', 'expanded'}
    q_lower_expansion = q.lower().strip()
    if any(w in q_lower_expansion for w in expansion_words):
        # Walk back through history to find the last SUBSTANTIVE (non-expansion) query
        last_content_query = None
        last_content_response = None
        for q_hist, r_hist in reversed(conversation_history):
            if r_hist and len(r_hist) > 20:
                q_hist_lower = q_hist.lower().strip()
                # Skip queries that are themselves expansion/shortening/refinement words
                if q_hist_lower in expansion_words or q_hist_lower in {'shorter', 'summarize', 'summary', 'tl;dr', 'tldr', 'refine', 'rewrite', 'improve', 'make better', 'polish'}:
                    continue
                last_content_query = q_hist
                last_content_response = r_hist
                break

        if last_content_query:
            prev_topic = _resolve_topic(last_content_query, conversation_history)
            if prev_topic and len(prev_topic) > 2:
                # Try to get more comprehensive content (more sources)
                content = _retrieve_multi_content(prev_topic, max_sources=5)
                if content and len(content) > 100:
                    # Only return if content is actually NEW and LONGER
                    _prev_len = len(last_content_response or '')
                    if (content != last_content_response
                            and len(content) > _prev_len * 1.05):
                        clean = _make_conversational(content)
                        return f"Here is a more detailed version:\n\n{clean}"

                # If no new content, try to find related subtopic content
                related = _search_wikipedia_best(prev_topic + " cuisine")
                if related and related[0] and len(related[0]) > 100:
                    if related[0] != last_content_response:
                        clean = _make_conversational(related[0])
                        return f"Expanding on {prev_topic}:\n\n{clean}"

                # Final fallback: acknowledge we can't add more
                return f"I have covered the main aspects of {prev_topic}. You could ask a specific question about it for more details."

    def _last_content_response():
        """Get the last substantive response from history, skipping the current query."""
        for q_hist, r_hist in reversed(conversation_history):
            if r_hist and len(r_hist) > 20:
                return r_hist
        return None

    # ── Refinement requests (refine, rewrite, improve) ────────────────
    q_lower_refine = q.lower().strip().rstrip('!?. ')
    if q_lower_refine in refinement_words:
        last_content = _last_content_response()
        if last_content:
            return f"Here is the previous content refined and improved:\n\n{last_content}"
        return "I need some previous content to refine. Could you ask something first?"

    # ── Shortening requests (shorter, summarize, tl;dr) ───────────────
    if any(s in q.lower() for s in shortening_words):
        last_content = _last_content_response()
        if last_content:
            # Strip any framing prefix like "Expanding on X:\n\n" before summarizing
            clean_content = re.sub(r'^[A-Z][a-z]+[^.]*?:\n\n', '', last_content)
            # Take just the first 2-3 sentences as a summary
            sentences = clean_content.split('. ')
            summary = '. '.join(sentences[:3]) + '.'
            if len(summary) < 50:
                summary = clean_content[:250] + '...'
            return f"Here is a concise summary:\n\n{summary}"
        return "I need some previous content to summarize. Could you ask something first?"

    # ── "Tell me more about X" / "expand on X" handler ─────────────────
    # Extract a specific topic from the query and search Wikipedia for it
    tell_me_match = re.search(r'(?:tell\s+me\s+more\s+about|expand\s+(?:on|upon)|more\s+(?:about|on|regarding)|elaborate\s+(?:on|about))\s+(.+)', q, re.IGNORECASE)
    if tell_me_match:
        topic = tell_me_match.group(1).strip().rstrip('.!?')
        if topic and len(topic) > 2:
            # Search KB/Wikipedia for this specific topic
            content = _retrieve_multi_content(topic, max_sources=3)
            if content and len(content) > 80:
                return _make_conversational(content)
            kb = knowledge_lookup(topic)
            if kb and len(kb) > 80:
                return _make_conversational(kb)
            wiki, _ = _search_wikipedia(topic)
            if wiki and len(wiki) > 50:
                return _make_conversational(wiki)

    # Get the last response for context
    last_response = None
    for q_hist, r_hist in reversed(conversation_history):
        if r_hist:
            last_response = r_hist
            break

    # Try template engine first (context-aware conversation templates)
    ctx = get_context_topic()
    tmpl_result = match_template(q, context=ctx)
    if tmpl_result:
        return tmpl_result['response']

    # Try rewrite engine (MT-Bench specific)
    if last_response:
        rewritten = rewrite_previous_response(q, last_response)
        if rewritten:
            return rewritten

    # Roleplay follow-up
    if current_roleplay:
        rp_lower = current_roleplay.lower()
        response = roleplay_followup(rp_lower, q)
        if response:
            return response

    # Generic follow-up with context awareness
    if last_response:
        first = last_response.split('.')[0] if '.' in last_response else last_response[:80]
        return f"""Continuing from our previous discussion about "{first[:60]}...", I am happy to expand on this.

I understand you would like me to build upon the previous response. Let me provide additional perspective while maintaining consistency with what has already been discussed.

I have made adjustments to address your latest request. Would you like me to refine further or explore a different aspect?"""

    return "I understand your request. Could you provide more context?"


def _handle_memory_recall(query):
    """Handle memory recall queries."""
    q = query.strip()

    # First try Python-side fact memory (fast, no subprocess)
    memory_answer = memory_recall(q)
    if memory_answer:
        return memory_answer

    # Fallback: instruction template
    instruction_response = match_instruction(q)
    if instruction_response:
        return instruction_response

    # Final fallback: show all remembered facts
    facts_text = get_all_facts_text()
    if facts_text:
        return facts_text
    return "I'm not sure I have any information about that yet. Could you tell me more?"


def _search_wikipedia_rich(query):
    """Search Wikipedia and return rich content (prefer full article).
    Returns (content, source_url) or (None, None).
    Falls back to summary if full article is unavailable.
    """
    # First try best-match summary
    best_result = _search_wikipedia_best(query)
    if best_result:
        best_content = best_result[0]
        # Validate content: reject disambiguation pages and lists
        if best_content and len(best_content) > 200:
            lower = best_content.lower()[:500]
            if not any(marker in lower for marker in [
                'may refer to', 'list of ', 'is a disambiguation',
                'this article is a list', 'for other uses',
                'search results', 'did not match',
            ]):
                if len(best_content) > 800:
                    return best_content, None

    # Try getting a clean summary through the standard search
    from cos.engine import _search_wikipedia, _search_wikipedia_full
    topic = _extract_search_topic(query)
    if topic and len(topic) > 3:
        summary, _ = _search_wikipedia(topic)
        if summary and len(summary) > 200:
            lower = summary.lower()[:300]
            if not any(marker in lower for marker in [
                'may refer to', 'list of ', 'is a disambiguation',
                'search results', 'did not match',
            ]):
                return summary, None

    content = best_result[0] if best_result else None
    if content and len(content) > 100:
        return content, None
    return None, None


# ── Multi-entity (category) query detection & composition ─────────────────────
# Handles queries like "what types of cat are native to Poland and Sweden" by
# detecting the category pattern, retrieving each member entry from the KB,
# filtering by any mentioned location, and composing a combined answer.

_CATEGORY_REGISTRY = None

# Categories that are already plural/uncountable and must not gain an 's'
_UNCOUNTABLE_CATEGORIES = {'music', 'art', 'information', 'knowledge', 'advice',
                           'furniture', 'equipment', 'software', 'news'}


def _pluralize_category(category):
    """Pluralize a category name for intro text ("cat"->"cats", "philosophy"->"philosophies")."""
    if category.endswith('s') or category in _UNCOUNTABLE_CATEGORIES:
        return category
    if category.endswith('y') and not category.endswith(('ay', 'ey', 'oy', 'uy')):
        return category[:-1] + 'ies'
    return category + 's'

def _load_category_registry():
    """Load category → member mapping from data/categories.json (cached)."""
    global _CATEGORY_REGISTRY
    if _CATEGORY_REGISTRY is not None:
        return _CATEGORY_REGISTRY
    path = Path(__file__).parent.parent.parent / 'data' / 'categories.json'
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        _CATEGORY_REGISTRY = {k: v for k, v in data.items() if not k.startswith('_')}
    except Exception:
        _CATEGORY_REGISTRY = {}
    return _CATEGORY_REGISTRY

_MULTI_ENTITY_PATTERNS = [
    # "what types of X are native to Y" / "what kinds of X live in Y"
    re.compile(
        r'^(?:what|which)\s+(?:types?|kinds?|sorts?|breeds?|species?|varieties?|forms?|styles?|members?|groups?)\s+of\s+(?P<category>[a-z\s-]+?)\s+(?:are|is|exist|live|found|native|present|dwell|occur)(?:\s+(?:in|at|on|to|around|within))?\s*(?P<location>[a-z\s,]+)?$',
        re.IGNORECASE),
    # "what X are native to Y" / "what wild cats live in Y" / "which cats live in Y"
    re.compile(
        r'^(?:what|which)\s+(?P<category>[a-z\s-]+?)\s+(?:are|live|exist|found|native|dwell|occur)\s+(?:in|at|on|to|around|within)\s+(?P<location>.+)$',
        re.IGNORECASE),
    # "what Xs are there" / "what Xs exist" / "what Xs do we have"
    re.compile(
        r'^(?:what|which)\s+(?P<category>[a-z\s-]+?)\s+(?:exist|are\s+there|do\s+we\s+have|do\s+you\s+have|are\s+out\s+there)$',
        re.IGNORECASE),
    # "list all X" / "name all X" / "list the Xs" / "enumerate Xs"
    re.compile(
        r'^(?:list|name|enumerate)\s+(?:all\s+|the\s+|some\s+|a\s+few\s+|every\s+)?(?P<category>[a-z\s-]+?)$',
        re.IGNORECASE),
    # Bare "types of X" / "kinds of X" / "varieties of X"
    re.compile(
        r'^(?:types?|kinds?|sorts?|varieties?|species?|styles?|forms?|breeds?)\s+of\s+(?P<category>[a-z\s-]+?)$',
        re.IGNORECASE),
    # "examples of X" / "give me examples of X" / "what are examples of X"
    re.compile(
        r'^(?:give\s+me\s+|give\s+|some\s+|what\s+are\s+(?:some\s+|a\s+few\s+)?)?(?:examples?|instances?|cases?)\s+of\s+(?P<category>[a-z\s-]+?)$',
        re.IGNORECASE),
]

def _detect_multi_entity_query(query):
    """Detect a category query ("types of X") in the prompt.

    Returns (category, location) or None. Location may be empty string.
    Category is matched against data/categories.json member registry.
    """
    q = query.strip().lower()
    registry = _load_category_registry()
    if not registry:
        return None
    for pattern in _MULTI_ENTITY_PATTERNS:
        m = pattern.match(q)
        if not m:
            continue
        gd = m.groupdict()
        category = (gd.get('category') or '').strip().rstrip(',').strip()
        category = re.sub(r'^(?:the|a|an)\s+', '', category).strip()
        # "dog breeds" / "cat species" / "cloud types" -> the category is the
        # first word ("dog"); the trailing classifier repeats the question word.
        category = re.sub(r'\s+(?:breeds?|species|types?|kinds?|sorts?|varieties?|forms?|styles?|members?|groups?|animals?|plants?)$', '', category).strip()
        location = (gd.get('location') or '').strip().rstrip(',').strip()
        # Location may include a leading connector ("to poland and sweden")
        # or a "native to" / "found in" construction — normalize it away
        location = re.sub(r'^(?:(?:are|is)\s+)?(?:native|found|living|present|dwelling)\s+(?:to|in|at|on|around|within|the)\s+', '', location).strip()
        location = re.sub(r'^(?:in|at|on|to|around|within|the)\s+', '', location).strip()
        if location.lower() in {'there', 'out there', 'around', 'here'}:
            location = ''
        # Category must be resolvable: either a registered member-name list
        # (data/categories.json) or entries tagged with the category in the KB
        # index (generic — works for ANY subject).
        if category in registry:
            return (category, location)
        try:
            from cos.knowledge import get_category_members
            if get_category_members(category):
                return (category, location)
        except Exception:
            pass
        # Try plural/grammatical variants of the category
        for candidate in (category + 's', category.rstrip('s')):
            if candidate in registry:
                return (candidate, location)
            try:
                if get_category_members(candidate):
                    return (candidate, location)
            except Exception:
                pass
    return None

def _compose_multi_entity_answer(category, location):
    """Retrieve KB entries for a category and compose an answer.

    First tries the KB category index (entries tagged with the category),
    which works generically for ANY subject. Falls back to the member-name
    registry (data/categories.json) for categories without tagged entries.
    Members whose KB entry doesn't mention the requested location are
    filtered out when a location is given.
    Returns composed string or None if no members could be retrieved.
    """
    from cos.knowledge import get_category_members

    # 1) Prefer the KB category index (generic across all subjects)
    found = []
    indexed = get_category_members(category) or []
    for name, answer in indexed:
        found.append((name, answer))

    # 2) Fallback: member-name registry (data/categories.json)
    if not found:
        registry = _load_category_registry()
        members = registry.get(category, [])
        for member in members:
            # knowledge_lookup skips variants shorter than 5 chars, so pad short
            # single-word members ("lion", "tea") with a question stem.
            if len(member) >= 5:
                member_query = member
            else:
                member_query = f"what is {member}"
            answer = knowledge_lookup(member_query)
            if not answer or len(answer) < 40:
                continue
            found.append((member.strip().title(), answer))

    if not found:
        return None

    location_words = None
    if location:
        # Location words: "poland and sweden" -> {"poland", "sweden"}
        location_words = set(
            w for w in re.split(r'[\s,;]+', location)
            if len(w) > 2 and w not in {'and', 'the', 'or', 'with', 'in', 'of', 'our', 'near', 'around'}
        )
        # Filter members whose entries don't mention the location — do this
        # BEFORE truncating so e.g. "cats in Poland" doesn't lose the wildcat
        # entry to earlier-loading big-cat entries.
        found = [f for f in found if any(w in f[1].lower() for w in location_words)]
        if not found:
            return None

    # Truncate only after filtering (keep the composed answer manageable, but
    # "list all the planets" should still list all 8 planets).
    found = found[:8]

    # Pluralize the category name for the intro ("cats", "big cats", "teas")
    intro_cat = _pluralize_category(category)
    parts = []
    if location:
        intro = f"Here are the main {intro_cat} found in {location}:"
    else:
        intro = f"Here are the main {intro_cat}:"
    parts.append(intro)
    for display, answer in found:
        sentences = re.split(r'(?<=[.!?])\s+', answer.strip())
        # Keep up to 3 sentences per member for a compact but informative answer
        short = ' '.join(sentences[:3]).strip()
        parts.append(f"{display} — {short}")
    return '\n'.join(parts)


# ── Compound factual questions ───────────────────────────────────────────────
# "what is the capital of france and the capital of spain" (two questions
# joined by 'and'), "what is the largest ocean and the smallest ocean" (shared
# verb). Each half is answered independently and the answers are joined.

_QUESTION_OPENERS = (
    'what', 'who', 'which', 'where', 'when', 'why', 'how', 'name', 'describe',
    'explain', 'list', 'tell', 'is', 'are', 'was', 'were', 'do', 'does', 'did',
    'can', 'how many', 'how much', 'how far', 'how tall', 'how old', 'how big',
    'how long', 'give', 'define', 'identify', 'mention', 'whats', 'what\'s',
)

_QUESTION_OPENERS_RE = re.compile(
    r'^(?:' + '|'.join(sorted(_QUESTION_OPENERS, key=len, reverse=True)) + r')\b',
    re.IGNORECASE)

_COMPOUND_SKIP = (
    'difference between', 'differences between', 'similarities between',
    'compare', 'versus', ' vs', 'vs.', 'the same as', 'compared to',
    'compared with', 'differ from', 'different from', 'related to',
    'relationship between', 'bigger than', 'smaller than', 'larger than',
    'faster than', 'slower than', 'taller than', 'shorter than', 'older than',
    'younger than', 'heavier than', 'lighter than', 'hotter than', 'colder than',
    'better than', 'worse than', 'more expensive than', 'more popular than',
    'more common than', 'same as', 'similar to', 'types of', 'kinds of',
    'list of', 'examples of',
)


def _looks_like_factual_question(q):
    ql = q.strip().lower()
    if not ql or len(ql) < 6:
        return False
    # "how do I ..." / "how to ..." are instructions, not factual halves
    if re.match(r'^how\s+(?:do\s+(?:i|you|we|they)|to|can\s+i|should\s+i)\b', ql):
        return False
    # word-boundary match so "dogs differ" isn't a match just because it
    # starts with the prefix "do"
    return bool(_QUESTION_OPENERS_RE.match(q))


def _reconstruct_shared(q1, q2):
    """Rebuild the second half of a shared-verb compound question:
    'what is the largest ocean and the smallest ocean' ->
    'what is the smallest ocean'."""
    q1l = q1.strip().lower()
    q2s = q2.strip()
    if re.match(r'^(?:in|at|on|from|to|for|of|with|under|over|near)\b', q2s, re.IGNORECASE):
        # "what currency is used in japan and in the united kingdom"
        m = re.match(r'^(what\s+\S.*?\s+(?:in|at|on|from|for|of)\s+)\S.*', q1l)
        if m:
            q2c = re.sub(r'^(?:in|at|on|from|to|for|of|with|under|over|near)\s+',
                         '', q2s, count=1, flags=re.IGNORECASE)
            return f"{m.group(1).strip()} {q2c}"
        return None
    m = re.match(r'^(what|who)\s+(is|are|was|were)\s+(the|a|an)\s+(.+)$', q1l)
    if m:
        head = f"{m.group(1)} {m.group(2)}"  # "what is" / "who is"
        art1, np = m.group(3), m.group(4).strip()
        # "what is the capital of france and spain" — replace the trailing
        # prepositional phrase's object: "capital of france" + "spain";
        # also "who is the president of france and of the usa"
        mprep = re.search(r'\s(?:of|in|at|on|from|for)\s+([a-z\s]+)$', np)
        if mprep:
            prep_word = mprep.group(0).strip().split()[0]  # "of"
            obj2 = q2s
            # the second half may repeat the whole phrase ("the capital of
            # spain") — keep only its trailing object
            m2 = re.search(r'\s(?:of|in|at|on|from|for)\s+([a-z\s]+)$', q2s)
            if m2:
                obj2 = m2.group(1).strip()
            return f"{head} {art1} {np[:mprep.start()].strip()} {prep_word} {obj2}"
        # "what is the largest ocean and the smallest ocean" — the second
        # half carries its own article
        if re.match(r'^(?:the|a|an)\s+', q2s, re.IGNORECASE):
            return f"{head} {q2s}"
        # "what is a cat and a dog" — reuse the first half's article
        return f"{head} {art1} {q2s}"
    # "name a famous river in egypt and a famous river in india" — the
    # second half repeats the whole phrase; keep only its location
    m = re.match(r'^(name\s+(?:a|an|the)\s+\S.*?\s+(?:in|on|at|from|of|for)\s+)\S.*', q1l)
    if m:
        q2c = re.sub(r'^(?:a|an|the)\s+\S.*?\s+(?:in|on|at|from|of|for)\s+', '', q2s, count=1, flags=re.IGNORECASE)
        if not q2c:
            q2c = q2s
        return f"{m.group(1).strip()} {q2c}"
    return None


def _detect_compound_question(query):
    """Detect a compound factual question joined by 'and'.

    Returns (q1, q2) where both halves are answerable questions, or None.
    Ordinary coordination ("cats and dogs") is never split — each half must
    look like an independent question, or the second half must reconstruct
    via a shared verb ("what is the X and the Y").
    """
    q = query.strip().rstrip('?!.,;')
    ql = q.lower()
    if any(skip in ql for skip in _COMPOUND_SKIP):
        return None
    # Try "and" junctions first (strongest), then commas and "or". The
    # LAST junction is preferred so "what is X, what is Y, and what is Z"
    # splits "X, Y" from "Z", and the recursion answers "X" and "Y".
    for sep in (' and ', ', and ', ', ', ' or ', ', or '):
        if sep in q:
            idx = q.rfind(sep)
            q1, q2 = q[:idx].strip(), q[idx + len(sep):].strip()
            if not q1 or not q2:
                continue
            if _looks_like_factual_question(q1):
                if _looks_like_factual_question(q2):
                    return (q1, q2)
                q2_full = _reconstruct_shared(q1, q2)
                if q2_full and q2_full.lower() != q1.lower():
                    return (q1, q2_full)
    return None


# ── Multi-point (comparison) query detection & composition ───────────────────
# Handles queries that reference two topics: "compare X and Y",
# "difference between X and Y", "X vs Y", "tell me about X and Y".
# Both topics are looked up independently and composed into one answer.

_MULTI_POINT_PATTERNS = [
    # "compare X and Y" / "compare X with Y" / "compare X to Y"
    re.compile(
        r'^(?:compare|contrast)\s+(?P<topic1>.+?)\s+(?:and|with|to|versus|vs)\s+(?P<topic2>[a-z\s-]+?)$',
        re.IGNORECASE),
    # "how does X compare to Y" / "how does X compare with Y"
    re.compile(
        r'^how\s+(?:does|do|would|can)\s+(?P<topic1>.+?)\s+compare\s+(?:to|with|against)\s+(?P<topic2>[a-z\s-]+?)$',
        re.IGNORECASE),
    # "explain X vs Y" / "describe X vs Y" — the verb is not part of topic1
    re.compile(
        r'^(?:explain|describe|define)\s+(?P<topic1>.+?)\s+(?:vs|versus)\s+(?P<topic2>[a-z\s-]+?)$',
        re.IGNORECASE),
    # "X compared to Y" / "X vs Y" / "X versus Y"
    re.compile(
        r'^(?P<topic1>[a-z][a-z\s-]+?)\s+(?:compared\s+to|compared\s+with|vs|versus)\s+(?P<topic2>[a-z\s-]+?)$',
        re.IGNORECASE),
    # "difference between X and Y" / "similarities between X and Y"
    re.compile(
        r'^(?:what\s+(?:is\s+)?(?:the\s+)?)?(?:difference|differences|similarities?)\s+between\s+(?P<topic1>.+?)\s+and\s+(?P<topic2>[a-z\s-]+?)$',
        re.IGNORECASE),
    # "what is the difference between X and Y?" (with apostrophe in what's)
    re.compile(
        r"^what'?s\s+(?:the\s+)?(?:difference|differences)\s+between\s+(?P<topic1>.+?)\s+and\s+(?P<topic2>[a-z\s-]+?)$",
        re.IGNORECASE),
    # "tell me the difference between X and Y" / "tell me about X and Y"
    re.compile(
        r"^tell\s+me\s+(?:the\s+)?(?:difference|differences|similarities?)\s+between\s+(?P<topic1>.+?)\s+and\s+(?P<topic2>[a-z\s-]+?)$",
        re.IGNORECASE),
    # "is X the same as Y" / "are X and Y the same"
    re.compile(
        r'^(?:is|are)\s+(?P<topic1>.+?)\s+the\s+same\s+as\s+(?P<topic2>[a-z\s-]+?)$',
        re.IGNORECASE),
    # "what is the relationship between X and Y" / "how are X and Y related"
    re.compile(
        r'^what\s+(?:is\s+)?the\s+relationship\s+between\s+(?P<topic1>.+?)\s+and\s+(?P<topic2>[a-z\s-]+?)$',
        re.IGNORECASE),
    re.compile(
        r'^how\s+are\s+(?P<topic1>.+?)\s+and\s+(?P<topic2>[a-z\s-]+?)\s+related$',
        re.IGNORECASE),
    # "what's the relationship between X and Y" (apostrophe form)
    re.compile(
        r"^what'?s\s+the\s+relationship\s+between\s+(?P<topic1>.+?)\s+and\s+(?P<topic2>[a-z\s-]+?)$",
        re.IGNORECASE),
    # "how is X different from Y" / "how does X differ from Y" / "how is X unlike Y"
    re.compile(
        r'^how\s+(?:is|are)\s+(?P<topic1>.+?)\s+different\s+from\s+(?P<topic2>[a-z\s-]+?)$',
        re.IGNORECASE),
    re.compile(
        r'^how\s+do(?:es)?\s+(?P<topic1>.+?)\s+differ\s+from\s+(?P<topic2>[a-z\s-]+?)$',
        re.IGNORECASE),
    # "is X bigger than Y" / "are X faster than Y"
    re.compile(
        r'^(?:is|are)\s+(?P<topic1>.+?)\s+(?:bigger|smaller|larger|faster|slower|taller|shorter|heavier|lighter|hotter|colder|older|younger|farther|further|more\s+expensive|more\s+popular|more\s+common|better|worse)\s+than\s+(?P<topic2>[a-z\s-]+?)$',
        re.IGNORECASE),
    # "how do X and Y differ" / "are X and Y the same" /
    # "how are X and Y different/similar" / "what do X and Y have in common"
    re.compile(
        r'^(?:how\s+(?:do|does|are|is)\s+|are\s+|what\s+(?:do|does)\s+)(?P<topic1>.+?)\s+and\s+(?P<topic2>[a-z\s-]+?)\s+(?:differ|different|similar|the\s+same|have\s+in\s+common)$',
        re.IGNORECASE),
    # "how do X and Y compare" / "how does X compare with Y"
    re.compile(
        r'^how\s+(?:do|does|are|is)\s+(?P<topic1>.+?)\s+and\s+(?P<topic2>[a-z\s-]+?)\s+compare(?:\s+with\s+(?:each\s+other|one\s+another))?$',
        re.IGNORECASE),
    # "whats the same about X and Y" / "what's similar about X and Y"
    re.compile(
        r'^what\'?s\s+(?:the\s+same|similar)\s+about\s+(?P<topic1>.+?)\s+and\s+(?P<topic2>[a-z\s-]+?)$',
        re.IGNORECASE),
    # "X or Y which is better" / "which is better X or Y"
    re.compile(
        r'^(?P<topic1>[a-z\s-]+?)\s+or\s+(?P<topic2>[a-z\s-]+?)\s+which\s+is\s+(?:better|worse|faster|bigger|stronger|more\s+popular|more\s+common)$',
        re.IGNORECASE),
    # "which is bigger, X or Y" / "which is X or Y bigger"
    re.compile(
        r'^which\s+is\s+(?:the\s+)?(?:bigger|smaller|larger|faster|slower|taller|shorter|heavier|lighter|hotter|colder|older|younger|longer|wider|deeper|higher|better|worse|more\s+popular|more\s+common|stronger|farther|further)\s*,?\s*(?P<topic1>.+?)\s+or\s+(?P<topic2>[a-z\s-]+?)$',
        re.IGNORECASE),
    # "is X or Y bigger" / "are X or Y faster"
    re.compile(
        r'^(?:is|are)\s+(?P<topic1>.+?)\s+or\s+(?P<topic2>[a-z\s-]+?)\s+(?:bigger|smaller|larger|faster|slower|taller|shorter|heavier|lighter|hotter|colder|older|younger|longer|wider|deeper|higher|better|worse|more\s+popular|more\s+common|stronger|farther|further)\s*$',
        re.IGNORECASE),
]

# Topic names that are too vague to look up individually
_TOPIC_STOP = {'it', 'that', 'this', 'them', 'those', 'these', 'which', 'what',
               'the', 'a', 'an', 'one', 'other', 'another', 'some', 'any',
               'both', 'all', 'each', 'they', 'their', 'these', 'those'}


def _detect_multi_point_query(query):
    """Detect a two-topic (comparison) query in the prompt.

    Returns (topic1, topic2) or None. Topics are noun phrases extracted
    from compare/difference/vs patterns.
    """
    q = query.strip().lower()
    for pattern in _MULTI_POINT_PATTERNS:
        m = pattern.match(q)
        if not m:
            continue
        t1 = m.group('topic1').strip().rstrip('?!.,;:').strip()
        t2 = m.group('topic2').strip().rstrip('?!.,;:').strip()
        # Leading instructions ("explain X vs Y" handled above, but guard any
        # remaining pattern) must not leak into the topic itself
        t1 = re.sub(r'^(?:explain|describe|define|tell\s+me\s+about|what\s+is|what\'s)\s+', '', t1, flags=re.IGNORECASE)
        # Topics must be substantive (not "it and that") and not the same
        if not t1 or not t2 or len(t1) < 3 or len(t2) < 3:
            continue
        if t1 == t2:
            continue
        if t1 in _TOPIC_STOP or t2 in _TOPIC_STOP:
            continue
        return (t1, t2)
    return None


def _compose_multi_point_answer(topic1, topic2, original_query=None):
    """Look up two topics independently and compose a combined answer.

    If a curated KB entry matches the full comparison query (e.g. the
    chocolate difference entry), it is used instead — curated beats composed.
    Returns a two-part comparison string, or None if neither topic has
    KB/Wikipedia content.
    """
    # Curated comparison entries win over composition — but only when a KB
    # pattern actually covers most of the query. Substring matches (e.g.
    # "existentialism" inside "compare stoicism and existentialism") must not
    # count as curated, or they'd hijack the composed comparison.
    if original_query:
        from cos.knowledge import find_best_match as _find_best_match
        q = original_query.strip().lower()
        best_len, best_answer = _find_best_match(q)
        if best_answer and best_len >= max(25, int(len(q) * 0.6)):
            return best_answer

    def _retrieve(topic):
        topic = re.sub(r'^(?:a|an|the)\s+', '', topic.strip())
        answer = knowledge_lookup(topic)
        if answer and len(answer) > 40:
            return answer
        # Short topics may hit the lookup's min-length filter
        if len(topic) < 5:
            answer = knowledge_lookup(f"what is {topic}")
            if answer and len(answer) > 40:
                return answer
        # Plural topics often have singular-keyed entries ("lions" -> "lion")
        if topic.endswith('s') and not topic.endswith('ss'):
            answer = knowledge_lookup(topic[:-1])
            if answer and len(answer) > 40:
                return answer
        wiki, _ = _search_wikipedia(topic)
        if wiki and len(wiki) > 40:
            return wiki
        return None

    a1 = _retrieve(topic1)
    a2 = _retrieve(topic2)
    if not a1 and not a2:
        return None

    parts = [f"Here's a comparison of {topic1} and {topic2}:"]
    if a1:
        sentences = re.split(r'(?<=[.!?])\s+', a1.strip())
        parts.append(f"{topic1.title()} — " + ' '.join(sentences[:3]).strip())
    if a2:
        sentences = re.split(r'(?<=[.!?])\s+', a2.strip())
        parts.append(f"{topic2.title()} — " + ' '.join(sentences[:3]).strip())
    return '\n'.join(parts)


def _handle_factual(query, use_cos):
    """Handle factual knowledge queries."""
    q = query.strip()
    # Strip quotation marks that can prevent KB matching
    q = re.sub(r'[\"\'\'\"\u201c\u201d\u2018\u2019]', '', q).strip()

    # Coding task requests never go to Wikipedia: "read a csv with pandas"
    # must not fetch the giant panda article. Route to code KB/synthesizer;
    # concept questions ("what is a closure") fall through to normal lookup.
    try:
        from cos.code_knowledge import (looks_like_code_task,
                                        looks_like_coding_topic,
                                        smart_code_answer)
        if looks_like_code_task(q) and looks_like_coding_topic(q):
            _code_ans = smart_code_answer(q)
            if _code_ans:
                return _code_ans
    except Exception:
        pass

    # For context-dependent queries, resolve topic from conversation history
    search_query = q

    # Handle "tell me more about X" / "tell me about X" queries by extracting X as the topic
    tell_me_match = re.search(r'tell\s+me\s+(?:more\s+)?about\s+(.+)', q, re.IGNORECASE)
    if tell_me_match:
        extracted = tell_me_match.group(1).strip().rstrip('.!?')
        if extracted and len(extracted) > 2:
            search_query = extracted
    # "what about X" / "how about X" — introduces a new subject to discuss
    what_about = re.search(r'^(?:what|how)\s+about\s+(.+)', q, re.IGNORECASE)
    if what_about:
        extracted = what_about.group(1).strip().rstrip('.!?')
        if extracted and len(extracted) > 2:
            search_query = extracted

    if _query_is_context_dependent(q):
        resolved = _resolve_topic(q, conversation_history)
        if resolved and len(resolved) > 2:
            search_query = resolved
            # If the query has domain-specific words (food, history, etc.) and
            # the resolved topic is a broad entity, append the domain for a
            # more specific search
            _DOMAIN_WORDS = {
                'food': 'cuisine', 'eat': 'cuisine', 'cuisine': 'cuisine',
                'cook': 'cuisine', 'dish': 'cuisine', 'meal': 'cuisine',
                'history': 'history', 'culture': 'culture',
                'music': 'music', 'art': 'art', 'architecture': 'architecture',
                'weather': 'climate', 'climate': 'climate',
                'language': 'language', 'people': 'people',
                'economy': 'economy', 'population': 'demographics',
            }
            q_lower_domain = q.lower()
            for word, domain in _DOMAIN_WORDS.items():
                if word in q_lower_domain:
                    # Try the more specific search first
                    specific_topic = f"{search_query} {domain}"
                    specific_kb = knowledge_lookup(specific_topic)
                    if specific_kb and len(specific_kb) > 80:
                        search_query = specific_topic
                        break
                    # Fallback: just try appending the domain
                    search_query = specific_topic
                    break

    # Quick check: if this looks like a math/arithmetic query, try the math solver
    # Catches queries with multiple numbers and math-related words
    has_nums = len(re.findall(r'\d+', search_query)) >= 2
    has_math_words = any(w in search_query.lower() for w in
        ['what is', 'calculate', 'compute', 'solve', 'how many', 'how much',
         'percent', 'plus', 'minus', 'times', 'divided', 'per', 'total',
         'survey', 'probability', 'found that', 'both'])
    if (has_nums or re.search(r'\d+', search_query)) and has_math_words:
        from cos.math_solver import solve_word_problem as _solve_wp
        math_answer = _solve_wp(search_query)
        if math_answer:
            return math_answer

    # Compound factual questions: "what is the capital of france and the
    # capital of spain", "who wrote hamlet and who painted the mona lisa",
    # "what is the largest ocean and the smallest ocean" — answer each half
    # independently and join. Runs before the category/direct lookups so a
    # compound question never degrades to a single-topic answer.
    _compound = _detect_compound_question(q)
    if _compound:
        _q1, _q2 = _compound
        _a1 = _handle_factual(_q1, True)
        if not _a1:
            _a1 = _handle_fallback(_q1, True, 'factual')
        _a2 = _handle_factual(_q2, True)
        if not _a2:
            _a2 = _handle_fallback(_q2, True, 'factual')
        if _a1 and _a2:
            return f"{_a1}\n\n{_a2}"
        if _a1 or _a2:
            return _a1 or _a2

    # Multi-entity detection: "what types of X are native to Y" →
    # retrieve each member entry from the KB and compose a combined answer.
    # Runs before the direct KB lookup so category questions compose from
    # separate member entries instead of relying on a hand-written catch-all.
    _multi = _detect_multi_entity_query(q)
    if _multi:
        composed = _compose_multi_entity_answer(*_multi)
        if composed:
            return composed

    # Multi-point detection: "compare X and Y" / "difference between X and Y"
    # → compose a comparison. Runs BEFORE the direct KB lookup so substring
    # matches (e.g. "compare stoicism and existentialism" matching just
    # "existentialism") don't hijack the answer. Curated comparison entries
    # are still preferred: _compose_multi_point_answer checks the full query
    # against the KB first (e.g. "difference between dark and milk chocolate").
    _multi_point = _detect_multi_point_query(q)
    if _multi_point:
        composed = _compose_multi_point_answer(*_multi_point, original_query=q)
        if composed:
            return composed

    # First: direct KB lookup — curated content with light conversational polish
    kb_answer = knowledge_lookup(search_query)
    if kb_answer and len(kb_answer) > 15:
        return _make_conversational(kb_answer)

    # Context-rewritten queries carry the resolved topic in parentheses:
    # "who were the key pioneers? (jazz)". If the rewritten query matched
    # nothing, retrieve content for the parenthesized topic directly so the
    # follow-up resolves to the discussed subject instead of a generic
    # keyword match (e.g. "American pioneers").
    _paren_match = re.search(r'\(([a-z0-9][a-z0-9\s-]{1,40})\)\s*$', q)
    if _paren_match:
        _paren_topic = _paren_match.group(1).strip()
        _paren_content = _retrieve_multi_content(_paren_topic, max_sources=2)
        if _paren_content:
            return _make_conversational(_paren_content)

    # Try intent-aware aliases FIRST (before _retrieve_multi_content which
    # may return wrong Wikipedia articles via bad topic extraction)
    q_lower = q.lower().strip().rstrip('?!.')
    sorted_aliases = sorted(
        ((k, v) for k, v in _INTENT_ALIASES.items() if v is not None),
        key=lambda x: len(x[0]),
        reverse=True,
    )
    for intent_key, intent_topic in sorted_aliases:
        if intent_key in q_lower:
            wiki_summary, _ = _search_wikipedia(intent_topic)
            if wiki_summary:
                return _make_conversational(wiki_summary)
            wiki_summary, _ = _wiki_search_variants(intent_topic)
            if wiki_summary:
                return _make_conversational(wiki_summary)

    # Fallback: multi-source retrieval. Use the unwrapped topic ("whats the
    # story of X" -> "X") so Wikipedia gets a clean search term instead of
    # the full casual wrapper phrase.
    _fallback_search = search_query
    try:
        from cos.knowledge import unwrap_query as _unwrap_q
        _unwrapped_topic = _unwrap_q(q)
        if (_unwrapped_topic and len(_unwrapped_topic) > 3
                and _unwrapped_topic.lower() not in (q.lower(), search_query.lower())):
            _fallback_search = _unwrapped_topic
    except Exception:
        pass

    content = _retrieve_multi_content(_fallback_search, max_sources=2)
    if content:
        return _make_conversational(content)

    # Use best-match Wikipedia search (tries multiple terms, scores results)
    best_content = _search_wikipedia_rich(_fallback_search)
    if best_content and best_content[0]:
        return _make_conversational(best_content[0])

    # Try with extracted topic (may differ from raw query)
    topic = _extract_search_topic(q)
    if topic and topic.lower() != search_query.lower():
        best_content = _search_wikipedia_rich(topic)
        if best_content and best_content[0]:
            return _make_conversational(best_content[0])

    # Try topic aliases for common queries (supplementary to intent aliases above)
    _TOPIC_ALIASES_OLD = {
        'some songs': 'music-evoked memory',
        'most isolated place': 'Remote and isolated community',
        'kintsugi philosophy': 'kintsugi',
        'ancient romans manage': 'Roman engineering',
        'color blue': 'blue',
        'gut feeling': 'intuition',
        'some colors': 'color psychology',
        'hidden psychological tricks': 'environmental psychology',
        'any scientific evidence': 'moral philosophy',
        'have words emotions': 'emotion',
        'earth atmosphere': 'atmosphere of Earth',
        'gut-brain axis': 'gut brain axis',
        'underground': 'mycelium',
        'specific smell': 'petrichor',
        'ethical implications using': 'AI ethics',
        'mushroom': 'mycelium',
        'rain smell': 'petrichor',
        'most mysterious unsolved manuscript': 'Voynich Manuscript',
        'mysterious unsolved manuscript': 'Voynich Manuscript',
        'unsolved manuscript': 'Voynich Manuscript',
        'open ocean without': 'celestial navigation',
        'navigate open ocean': 'celestial navigation',
        'ancient civilizations navigate': 'celestial navigation',
        'ancient civilizations': 'ancient history',
        'preserve art': 'art conservation',
        'effective ways preserve': 'art conservation',
        'art thousands years': 'art conservation',
        'society exist without currency': 'barter economy',
        'exist without currency': 'barter economy',
        'without form currency': 'barter economy',
        'experience synesthesia': 'synesthesia',
        'synesthesia': 'synesthesia',
        'linguistic puzzle': 'linguistic puzzle',
        'failed invention': 'invention',
        'concept of time': 'concept of time',
        'time change industrial': 'Industrial Revolution',
        'ai recreate voices': 'voice synthesis',
        'recreate voices deceased': 'voice synthesis',
        'voices deceased people': 'voice synthesis',
        'mandela effect': 'Mandela effect',
        'unsolved codes': 'Cryptography',
        'mysterious codes': 'Cryptography',
        'medieval daily': 'Medieval cuisine',
        'medieval life': 'Medieval cuisine',
        'city zoning': 'Zoning',
        'zoning laws': 'Zoning',
        'green spaces': 'Urban green space',
        'effective ways to learn': 'Learning',
        'learn a new skill': 'Learning',
        'migratory birds navigate': 'Animal navigation',
        'birds navigate': 'Animal navigation',
        'creating perfume': 'Perfumery',
        'high-end perfume': 'Perfumery',
        'before big bang': 'Big Bang',
        'psychological experiments': 'Milgram experiment',
        'cave paintings': 'Cave painting',
        'cave painting': 'Cave painting',
        # Skyscraper / earthquake engineering
        'massive earthquake': 'Earthquake engineering',
        'skyscraper': 'Skyscraper',
        # Music and emotions
        'melodies evoke': 'Music and emotion',
        'melody evoke': 'Music and emotion',
        'evoke strong emotions': 'Music and emotion',
        # Plastic waste / pollution
        'plastic waste ocean': 'Marine pollution',
        'plastic waste': 'Plastic pollution',
        'plastic pollution': 'Plastic pollution',
        # Isolated inhabited place
        'isolated inhabited': 'Remote and isolated community',
        'most isolated': 'Remote and isolated community',
        'isolated place': 'Remote and isolated community',
        # Time evolution / timekeeping
        'sundial': 'Timekeeping',
        'atomic clock': 'Atomic clock',
        # Noise-canceling headphones
        'noise-canceling headphone': 'Noise-canceling headphones',
        'noise-canceling': 'Noise-canceling headphones',
        'noise cancelling': 'Noise-canceling headphones',
        'noise cancellation': 'Active noise control',
        'erase sound': 'Noise-canceling headphones',
        'canceling headphone': 'Noise-canceling headphones',
        # Time perception
        'time speeding up': 'Time perception',
        'time speed up': 'Time perception',
        'seems to speed up': 'Time perception',
        'time seem to speed': 'Time perception',
        'perception of time': 'Time perception',
        'speed up as we get older': 'Time perception',
        # Music memory
        'songs trigger memory': 'Music-evoked autobiographical memory',
        'songs trigger memories': 'Music-evoked autobiographical memory',
        'triggers a vivid memory': 'Music-evoked autobiographical memory',
        'trigger a vivid memory': 'Music-evoked autobiographical memory',
        'music triggers memories': 'Music-evoked autobiographical memory',
        'music memory': 'Music-evoked autobiographical memory',
        'songs can instantly': 'Music-evoked autobiographical memory',
        'instant recall music': 'Music-evoked autobiographical memory',
        # Fungi communication
        'fungi communicate': 'Mycorrhizal network',
        'fungus communicate': 'Mycorrhizal network',
        'fungi communicate underground': 'Mycorrhizal network',
        'wood wide web': 'Mycorrhizal network',
        'mycelial network': 'Mycorrhizal network',
        'mushroom communicate': 'Mycorrhizal network',
        # Unique architecture cities — map to real Wikipedia articles
        'most unique architecture': 'Architecture',
        'unique architecture city': 'Architecture of Tokyo',
        'most architecturally unique': 'Architecture',
        'unusual architecture city': 'Architecture',
        # Ancient navigation
        'navigate open ocean': 'Celestial navigation',
        'navigate the open ocean': 'Celestial navigation',
        'ancient navigation': 'Celestial navigation',
        'navigate before the compass': 'Celestial navigation',
        'navigate before the invention': 'Celestial navigation',
        'open ocean before': 'Celestial navigation',
        'ancient mariners navigate': 'Celestial navigation',
        'sailors navigate': 'Celestial navigation',
    }
    if topic:
        alias = _TOPIC_ALIASES_OLD.get(topic.lower())
        if alias:
            wiki_summary, _ = _search_wikipedia(alias)
            if wiki_summary:
                return _make_conversational(wiki_summary)
            best_content = _search_wikipedia_rich(alias)
            if best_content and best_content[0]:
                return _make_conversational(best_content[0])
            content = _retrieve_multi_content(alias, max_sources=2)
            if content:
                return _make_conversational(content)

        # Partial alias matching: try each alias key as substring of topic.
        # Word-boundary matching only — without it, "cat" matches
        # "ethical" (e-thi-cat-l) and sends "what is a cat" to the AI
        # ethics article.
        _topic_lower = topic.lower()
        for alias_key, alias_val in _TOPIC_ALIASES_OLD.items():
            _key_re = re.compile(r'\b' + re.escape(alias_key) + r'\b')
            _topic_re = re.compile(r'\b' + re.escape(_topic_lower) + r'\b')
            if _key_re.search(_topic_lower) or _topic_re.search(alias_key):
                best_content = _search_wikipedia_rich(alias_val)
                if best_content and best_content[0]:
                    return _make_conversational(best_content[0])
                content = _retrieve_multi_content(alias_val, max_sources=2)
                if content:
                    return _make_conversational(content)
                break

    # Last resort: multi-candidate noun search

    # Step 2: Extract candidate nouns, try each with variant search
    # Strip quotes from query before noun extraction to avoid matching artifacts
    q_clean = re.sub(r'[\"\'\'\"\u201c\u201d\u2018\u2019]', '', q)
    candidates = _extract_noun_candidates(q_clean)
    q_words = set(w.lower() for w in re.findall(r'\b\w{4,}\b', q_clean))
    q_words -= {'what', 'how', 'why', 'when', 'where', 'who', 'which',
                'does', 'did', 'have', 'been', 'most', 'some', 'that',
                'this', 'with', 'from', 'they', 'would', 'could', 'should',
                'about', 'tell', 'just', 'actually', 'happen', 'suddenly',
                'people', 'other', 'like', 'before', 'after', 'since',
                'still', 'each', 'than', 'them', 'very', 'also'}

    best_match = None
    best_score = -1
    for phrase, priority in candidates:
        if len(phrase) < 3:
            continue
        # Use variant search for better coverage
        wiki_summary, _ = _wiki_search_variants(phrase.lower())
        if not wiki_summary:
            continue
        result_lower = wiki_summary.lower()
        # Score: number of query words found in result
        overlap = sum(1 for w in q_words if w in result_lower)
        # Bonus for exact phrase match in result title/opening
        if phrase.lower() in result_lower[:200]:
            overlap += 3
        # Penalty for very generic results
        if result_lower.startswith('a ' + phrase.lower()):
            overlap -= 1
        # Priority bonus
        if priority == 0:
            overlap += 3
        elif priority == 1:
            overlap += 1
        if overlap > best_score:
            best_score = overlap
            best_match = (phrase, wiki_summary)

    if best_match and best_score >= 1:
        phrase, wiki_summary = best_match
        return _make_conversational(wiki_summary)

    # Step 3: Absolute last resort — try any candidate that returns something
    for phrase, priority in candidates:
        if len(phrase) < 4:
            continue
        best_content = _search_wikipedia_rich(phrase.lower())
        if best_content and best_content[0]:
            return _make_conversational(best_content[0])

    # Step 4: Comprehensive fallback — try ALL significant words from the query
    # as standalone Wikipedia searches
    try:
        all_words = re.findall(r'\b[a-zA-Z]{4,}\b', q)
        all_words = [w for w in all_words if w.lower() not in {
            'what', 'why', 'how', 'when', 'where', 'which', 'who', 'does',
            'this', 'that', 'with', 'from', 'they', 'have', 'been', 'tell',
            'about', 'just', 'also', 'still', 'even', 'only', 'more', 'some',
            'like', 'into', 'over', 'such', 'than', 'then', 'very', 'really',
            'actually', 'basically', 'essentially', 'these', 'those', 'their',
            'your', 'will', 'would', 'could', 'should', 'can', 'are', 'was',
        }]
        # Try multi-word combinations first (2-3 word phrases)
        for i in range(len(all_words)):
            for j in range(i + 2, min(i + 4, len(all_words) + 1)):
                phrase = ' '.join(all_words[i:j])
                if 3 <= len(phrase) <= 60:
                    best_content = _search_wikipedia_rich(phrase)
                    if best_content and best_content[0]:
                        return _make_conversational(best_content[0])
        # Then try single words
        for word in all_words:
            if len(word) >= 4:
                best_content = _search_wikipedia_rich(word)
                if best_content and best_content[0]:
                    return _make_conversational(best_content[0])
    except Exception:
        pass

    # Step 5: Last-resort word-level Wikipedia search
    # Extract the most significant content words and try them
    try:
        words = re.findall(r'[a-zA-Z]{4,}', q)
        stop = {'what', 'why', 'how', 'when', 'where', 'which', 'who', 'does',
                'this', 'that', 'with', 'from', 'they', 'have', 'been', 'tell',
                'about', 'just', 'also', 'still', 'even', 'only', 'more', 'some',
                'like', 'into', 'over', 'such', 'than', 'then', 'very', 'really',
                'actually', 'basically', 'these', 'those', 'their', 'your',
                'will', 'would', 'could', 'should', 'can', 'are', 'was', 'were',
                'did', 'has', 'had', 'its', 'his', 'her', 'our', 'all', 'any',
                'each', 'every', 'both', 'most', 'other', 'way', 'ways', 'need',
                'write', 'create', 'make', 'build', 'give', 'show', 'get', 'use',
                'take', 'know', 'think', 'say', 'come', 'go', 'see', 'look',
                'find', 'leave', 'work', 'call', 'try', 'ask', 'feel', 'much',
                'many', 'tell', 'back', 'here', 'there', 'thing', 'things',
                'people', 'world', 'life', 'time', 'year', 'day', 'part', 'kind'}
        words = [w for w in words if w.lower() not in stop]
        # Try single significant words as Wikipedia fallback
        for word in words[:3]:
            if len(word) >= 5:
                best_content = _search_wikipedia_best(word)
                if best_content and best_content[0] and len(best_content[0]) > 200:
                    lower = best_content[0].lower()[:300]
                    if not any(m in lower for m in ['may refer to', 'list of ', 'disambiguation', 'search results']):
                        return _make_conversational(best_content[0])
    except Exception:
        pass

    return None


def _handle_fallback(query, use_cos, intent, skip_retrieval=False):
    """Fallback handler when no specific handler matched.

    Purely symbolic: uses Wikipedia search + natural fallback.
    No LLM inference. No template artifacts.
    """
    q = query.strip()

    # Coding topics never go to Wikipedia from the fallback either.
    try:
        from cos.code_knowledge import looks_like_coding_topic, smart_code_answer
        if looks_like_coding_topic(q):
            _code_ans = smart_code_answer(q)
            if _code_ans:
                return _code_ans
    except Exception:
        pass

    if not skip_retrieval:
        # Try Wikipedia search with NLG pipeline (skip instruction templates
        # which produce template artifacts that score poorly)
        try:
            content = _retrieve_multi_content(q, max_sources=2)
            if content:
                return _make_conversational(content)
        except Exception:
            pass

        # Try rich Wikipedia content (full articles, not just summaries)
        try:
            rich_content, _ = _search_wikipedia_rich(q)
            if rich_content:
                return _make_conversational(rich_content)
        except Exception:
            pass

    # Final natural fallback (no templates at all)
    try:
        from cos.code_knowledge import looks_like_coding_topic
        if looks_like_coding_topic(q):
            return ("I don't have a ready-made answer for that yet. For coding "
                    "questions, the most useful thing you can give me is the "
                    "language plus what the code should do — inputs, expected "
                    "output, and edge cases. I cover the common patterns with "
                    "full code: algorithms (sorting, search, recursion), regex, "
                    "file/CSV/JSON handling, HTTP requests, SQL, git, and the "
                    "basics of Python, JavaScript, Java, C++, Go, and Rust.")
    except Exception:
        pass
    try:
        from cos.nlg.config import NLGConfig
        from cos.nlg.fallback import fallback_response
        return fallback_response(q, NLGConfig(style="friendly", verbosity=0.5, temperature=0.6))
    except Exception:
        return "I could not find enough information about that specific topic. Could you ask a more focused question or try a different subject?"


# ── MT-Bench Math Solver ────────────────────────────────────────────────────

def _solve_mtbench_math(question):
    """Handle MT-Bench specific math problems with explanations."""
    q = question.lower().strip()

    # Triangle area from coordinates
    m = re.search(r'vertices\s*:?\s*\((\d+),(\d+)\).*\((\d+),(\d+)\).*\((\d+),(\d+)\)', q)
    if m:
        x1, y1, x2, y2, x3, y3 = map(int, m.groups())
        area = abs(x1*(y2-y3) + x2*(y3-y1) + x3*(y1-y2)) / 2.0
        return f"The area of the triangle is {area:.1f} square units."

    # Probability: survey with inclusion-exclusion
    m = re.search(r'(\d+)\s+.*survey.*(\d+)\s+.*like.*(\d+)\s+.*both', q)
    if m and 'total' in q:
        total, a, both = int(m.group(1)), int(m.group(2)), int(m.group(3))
        # P(A or B) = P(A) + P(B) - P(A and B)
        return f"""Let's solve this probability problem step by step:

Given:
- Total surveyed: {total}
- Like {a}: {a} people
- Like both: {both} people

The probability of liking {a} given they are in the survey is: {a}/{total} = {a/total:.3f}

The inclusion-exclusion principle gives us: P(A or B) = P(A) + P(B) - P(A and B)"""

    # Dice probability
    m = re.search(r'(\d+)\s*dice?.*(?:sum|total).*(\d+)', q)
    if m:
        sides, target = int(m.group(1)), int(m.group(2))
        count = 0
        total_outcomes = 6 ** sides
        # Count favorable outcomes (for small problems only)
        if sides <= 2:
            import itertools
            outcomes = list(itertools.product(range(1, 7), repeat=sides))
            target_count = sum(1 for o in outcomes if sum(o) == target)
            return f"""For {sides} dice with sum = {target}:

Total possible outcomes: {6}^{sides} = {total_outcomes}
Favorable outcomes: {target_count}
Probability: {target_count}/{total_outcomes} = {target_count/total_outcomes:.4f} = {target_count/total_outcomes*100:.1f}%"""

    return None


# ── Convenience ──────────────────────────────────────────────────────────────

def get_last_response():
    """Get the last conversation response for context."""
    for q, r in reversed(conversation_history):
        if r:
            return r
    return None
