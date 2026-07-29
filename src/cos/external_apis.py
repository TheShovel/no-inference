"""
External API integrations for COS — no API keys required.

Provides functions to fetch real-time data from free public APIs:
  - Weather (wttr.in)
  - Time zones (WorldTimeAPI)
  - Dictionary (Free Dictionary API)
  - Exchange rates (Frankfurter API)
  - Jokes (Official Joke API, icanhazdadjoke)
  - Numbers trivia (Numbers API)
"""

import json
import re
from urllib.request import Request, urlopen
from urllib.error import URLError


def _fetch(url, timeout=8):
    """Fetch a URL and return the response text."""
    try:
        req = Request(url, headers={'User-Agent': 'COS/1.0 (no-inference)'})
        with urlopen(req, timeout=timeout) as resp:
            return resp.read().decode()
    except (URLError, OSError, ValueError) as e:
        return None


# ── Weather ──────────────────────────────────────────────────────────────────

def get_weather(location):
    """Get current weather for a location using wttr.in (returns plain text)."""
    if not location or len(location) < 2:
        return None
    text = _fetch(f'https://wttr.in/{location}?format=%C+%t+%w+%h')
    if text:
        cleaned = text.strip()
        if cleaned and not cleaned.startswith('Unknown'):
            return f"The current weather in {location.title()} is: {cleaned}."
    return None


def get_weather_full(location):
    """Get a full weather report (multi-line)."""
    if not location or len(location) < 2:
        return None
    text = _fetch(f'https://wttr.in/{location}?0&lang=en')
    if text and 'Unknown' not in text[:50]:
        lines = [l for l in text.split('\n') if l.strip() and 'Follow' not in l and 'wttr' not in l.lower()]
        return '\n'.join(lines[:25]).strip()
    return None


# ── Time ─────────────────────────────────────────────────────────────────────

def get_time(timezone='UTC'):
    """Get current time for a timezone using WorldTimeAPI with fallback to time.is."""
    tz = timezone.strip().replace(' ', '_')
    
    # Primary: WorldTimeAPI
    data = _fetch(f'http://worldtimeapi.org/api/timezone/{tz}')
    if not data:
        # Try alternative endpoint
        data = _fetch(f'http://worldtimeapi.org/api/timezone/{tz}')
    if data:
        try:
            parsed = json.loads(data)
            dt = parsed.get('datetime', '')
            tz_name = parsed.get('timezone', tz)
            if dt:
                time_part = dt.split('T')[1].split('.')[0] if 'T' in dt else dt
                return f"The current time in {tz_name} is {time_part}."
        except (json.JSONDecodeError, IndexError):
            pass
    
    # Fallback: use UTC from time API
    data = _fetch(f'http://worldtimeapi.org/api/ip')
    if data:
        try:
            parsed = json.loads(data)
            dt = parsed.get('datetime', '')
            if dt:
                time_part = dt.split('T')[1].split('.')[0] if 'T' in dt else dt
                return f"The current time in {parsed.get('timezone', 'UTC')} is {time_part}."
        except (json.JSONDecodeError, IndexError):
            pass
    
    return None


def list_timezones():
    """List available timezone regions."""
    data = _fetch('http://worldtimeapi.org/api/timezone')
    if data:
        try:
            zones = json.loads(data)
            # Group by region
            regions = set()
            for z in zones:
                region = z.split('/')[0] if '/' in z else z
                regions.add(region)
            return f"Available timezone regions: {', '.join(sorted(regions))}."
        except json.JSONDecodeError:
            pass
    return None


# ── Dictionary ───────────────────────────────────────────────────────────────

def define_word(word):
    """Get dictionary definition for a word using Free Dictionary API."""
    if not word or len(word) < 2:
        return None
    data = _fetch(f'https://api.dictionaryapi.dev/api/v2/entries/en/{word}')
    if not data:
        return None
    try:
        parsed = json.loads(data)
        if isinstance(parsed, list) and len(parsed) > 0:
            entry = parsed[0]
            word_name = entry.get('word', word)
            meanings = entry.get('meanings', [])
            parts = [f"Definitions for '{word_name}':"]
            for m in meanings[:3]:
                pos = m.get('partOfSpeech', '')
                defs = m.get('definitions', [])
                for d in defs[:2]:
                    definition = d.get('definition', '')
                    example = d.get('example', '')
                    line = f"  ({pos}) {definition}"
                    if example:
                        line += f" — \"{example}\""
                    parts.append(line)
            return '\n'.join(parts)
    except (json.JSONDecodeError, IndexError):
        pass
    return None


# ── Exchange Rates ───────────────────────────────────────────────────────────

def get_exchange_rate(base='USD', target='EUR'):
    """Get exchange rate using Frankfurter API (free, no key)."""
    base = base.upper()[:3]
    target = target.upper()[:3]
    data = _fetch(f'https://api.frankfurter.app/latest?from={base}&to={target}')
    if data:
        try:
            parsed = json.loads(data)
            rates = parsed.get('rates', {})
            if target in rates:
                rate = rates[target]
                return f"1 {base} = {rate} {target}"
        except json.JSONDecodeError:
            pass
    return None


def list_currencies():
    """Get list of supported currencies."""
    data = _fetch('https://api.frankfurter.app/currencies')
    if data:
        try:
            currencies = json.loads(data)
            items = [f"{code}: {name}" for code, name in list(currencies.items())[:20]]
            return f"Supported currencies: {', '.join(items)}"
        except json.JSONDecodeError:
            pass
    return None


# ── Jokes ────────────────────────────────────────────────────────────────────

def get_joke():
    """Get a random joke from Official Joke API."""
    data = _fetch('https://official-joke-api.appspot.com/random_joke')
    if data:
        try:
            joke = json.loads(data)
            setup = joke.get('setup', '')
            punchline = joke.get('punchline', '')
            if setup and punchline:
                return f"{setup}\n{punchline}"
        except json.JSONDecodeError:
            pass
    return None


def get_dad_joke():
    """Get a dad joke from icanhazdadjoke."""
    try:
        req = Request('https://icanhazdadjoke.com/',
                      headers={'User-Agent': 'COS/1.0 (no-inference)',
                               'Accept': 'application/json'})
        with urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
            joke = data.get('joke', '')
            if joke:
                return joke
    except Exception:
        pass
    return None


# ── Numbers Trivia ──────────────────────────────────────────────────────────

def number_trivia(number):
    """Get a trivia fact about a number using Numbers API."""
    try:
        n = int(number)
        data = _fetch(f'http://numbersapi.com/{n}/trivia')
        if data:
            return data.strip()
    except (ValueError, TypeError):
        pass
    return None


def date_fact(month, day):
    """Get a fact about a specific date."""
    try:
        m, d = int(month), int(day)
        data = _fetch(f'http://numbersapi.com/{m}/{d}/date')
        if data:
            return data.strip()
    except (ValueError, TypeError):
        pass
    return None


# ─️ Category Router ──────────────────────────────────────────────────────────

API_HANDLERS = {
    'weather': {
        'patterns': [
            r'weather\s+(?:in|at|for|of)\s+(.+)',
            r'(?:what|how).{0,30}weather\s+(?:in|at|for|of)\s+(.+)',
            r'(?:what|how).{0,30}temperature\s+(?:in|at|for|of)\s+(.+)',
            r'weather\s+(.+?)(?:\?|$)',
            r'(?:what.?(?:s|\s+is)\s+the\s+weather|how\s+(?:is|s)\s+the\s+weather)\s+(?:in|at|for|of)\s+(.+)',
            r'(?:what.?(?:s|\s+is)\s+the\s+temperature|how\s+(?:hot|cold)\s+is\s+it)\s+(?:in|at|for)\s+(.+)',
        ],
        'handler': lambda q, m: get_weather(m.group(1).rstrip('?!.').strip()),
    },
    'weather_general': {
        'patterns': [
            r'(?:what.?(?:s|\s+is)\s+the\s+weather\s*$)',
            r'(?:what.?(?:s|\s+is)\s+the\s+temperature\s*$)',
            r'how\s+(?:is|s)\s+the\s+weather\s*$',
            r'how\s+(?:hot|cold)\s+is\s+it\s*$',
        ],
        'handler': lambda q, m: "I'd be happy to check the weather! Please specify a location, e.g., 'weather in London'.",
    },
    'time': {
        'patterns': [
            r'(?:what\s+time|current\s+time|time\s+(?:in|at|for))\s+(.+?)(?:\?|$)',
            r'(?:what.?(?:s|\s+is)\s+the\s+time\s+(?:in|at|for))\s+(.+?)(?:\?|$)',
        ],
        'handler': lambda q, m: get_time(m.group(1)),
    },
    'define': {
        'patterns': [
            r'(?:define|definition\s+of|what\s+does\s+)\s+([A-Za-z]+)\s+(?:mean\s+)?(?:\?|$)',
            r'what\s+is\s+(?:the\s+)?(?:definition|meaning)\s+of\s+([A-Za-z]+)(?:\?|$)',
            r'(?:what|tell\s+me)\s+(?:does\s+)?([A-Za-z]+)\s+mean(?:\?|$)',
        ],
        'handler': lambda q, m: define_word(m.group(1)),
    },
    'exchange_rate': {
        'patterns': [
            r'(?:exchange\s+rate|currency\s+(?:conver|rate))\s+(?:\w+)?\s*(?:from\s+)?(\w{3})\s+(?:to|in|for)\s+(\w{3})',
            r'how\s+much\s+is\s+(\d+(?:\.\d+)?)\s+(\w{3})\s+(?:in|to)\s+(\w{3})',
        ],
        'handler': lambda q, m: get_exchange_rate(m.group(1) if m.lastindex >= 1 else 'USD',
                                                   m.group(2) if m.lastindex >= 2 else ''),
    },
    'joke': {
        'patterns': [
            r'(?:tell\s+(?:me\s+)?(?:a\s+)?|got\s+(?:any\s+)?|hear\s+(?:a\s+)?)?joke',
            r'(?:make\s+me\s+)?laugh',
            r'dad\s+joke',
        ],
        'handler': lambda q, m: get_joke(),
    },
    'number_trivia': {
        'patterns': [
            r'(?:trivia|fact)\s+(?:about|for|on)\s+(\d+)',
            r'(?:what.?(?:s|\s+is)\s+(?:a\s+)?)?(?:trivia|interesting|fun)\s+(?:fact|trivia)\s+(?:about|for|on)\s+(\d+)',
            r'(\d+)\s+(?:trivia|fact)',
        ],
        'handler': lambda q, m: number_trivia(m.group(1)),
    },
}


def is_api_query(query):
    """Check if a query can be handled by an external API."""
    q = query.lower().strip()
    for category, info in API_HANDLERS.items():
        for pattern in info['patterns']:
            m = re.search(pattern, q)
            if m:
                return True
    return False


def handle_api_query(query):
    """Try to handle a query with an external API. Returns response or None."""
    q = query.lower().strip()
    for category, info in API_HANDLERS.items():
        for pattern in info['patterns']:
            m = re.search(pattern, q)
            if m:
                try:
                    result = info['handler'](q, m)
                    if result:
                        return result
                except Exception:
                    pass
    return None
