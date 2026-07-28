#!/usr/bin/env python3
"""
Knowledge Base Generator — automatically creates KB entries from Wikipedia.

Usage:
  python3 src/generate_kb.py --topics "Machine learning, Quantum computing, CRISPR"
  python3 src/generate_kb.py --file topics.txt
  python3 src/generate_kb.py --all (generates from 1000+ popular topics)

Generates files in data/knowledge/generated/
"""

import json
import os
import re
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent.parent / 'data' / 'knowledge' / 'generated'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


_CACHE = {}  # topic -> extract

def fetch_wikipedia(topic: str) -> dict:
    """Fetch Wikipedia summary for a topic with caching."""
    if topic in _CACHE:
        return _CACHE[topic]
    url = (
        'https://en.wikipedia.org/api/rest_v1/page/summary/'
        + urllib.parse.quote(topic.replace(' ', '_'))
    )
    req = urllib.request.Request(url, headers={'User-Agent': 'COS-Generator/1.0'})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            # Reject disambiguation pages
            extract = data.get('extract', '').lower()
            if any(m in extract[:200] for m in ['may refer to', 'may also refer', 'disambiguation', 'not found']):
                _CACHE[topic] = {}
                return {}
            _CACHE[topic] = data
            return data
    except Exception as e:
        _CACHE[topic] = {}
        return {}


def search_wikipedia(query: str) -> list:
    """Search Wikipedia for a topic."""
    search_url = (
        'https://en.wikipedia.org/w/api.php?'
        'action=query&list=search&srwhat=text'
        '&srsearch=' + urllib.parse.quote(query) +
        '&srlimit=3&format=json'
    )
    req = urllib.request.Request(search_url, headers={'User-Agent': 'COS-Generator/1.0'})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return data.get('query', {}).get('search', [])
    except Exception:
        return []


def generate_query_variations(topic: str) -> list:
    """Generate natural question variations for a topic."""
    t = topic.lower().strip()
    variations = []
    
    # Direct patterns
    variations.append(t)
    variations.append(f"what is {t}")
    variations.append(f"tell me about {t}")
    variations.append(f"explain {t}")
    variations.append(f"what is {t} and how does it work")
    variations.append(f"tell me about the history of {t}")
    variations.append(f"how does {t} work")
    variations.append(f"{t} explained")
    variations.append(f"describe {t}")
    
    # "What is..." patterns
    if t.startswith(('the ', 'a ', 'an ')):
        base = re.sub(r'^(the|a|an)\s+', '', t)
        variations.append(f"what is {base}")
        variations.append(f"tell me about {base}")
    
    # Combine into single-word root
    words = t.split()
    if len(words) > 2:
        # Try shorter forms
        for i in range(1, min(3, len(words))):
            short = ' '.join(words[-i:])
            if short != t:
                variations.append(short)
                variations.append(f"what is {short}")
                variations.append(f"tell me about {short}")
    
    # Remove duplicates preserving order
    seen = set()
    result = []
    for v in variations:
        if v not in seen:
            seen.add(v)
            result.append(v)
    return result


def create_entry(topic: str, extract: str) -> dict:
    """Create a KB entry from Wikipedia extract."""
    if not extract or len(extract) < 100:
        return None
    
    # Get first paragraph (best summary)
    first_para = extract.split('\n')[0].strip() if '\n' in extract else extract
    if len(first_para) < 80:
        # Take first 500 chars as summary
        first_para = extract[:500].rsplit('. ', 1)[0] + '.' if '. ' in extract[:500] else extract[:500]
    
    # Clean up the text
    first_para = re.sub(r'\s+', ' ', first_para).strip()
    if not first_para.endswith(('.', '!', '?')):
        first_para += '.'
    
    return {
        'q': generate_query_variations(topic),
        'a': first_para.strip()
    }


def process_topic(topic: str) -> bool:
    """Process a single topic: search, fetch, create entry."""
    topic = topic.strip()
    if not topic or len(topic) < 3:
        return False
    
    # Skip if already exists
    safe_name = re.sub(r'[^a-zA-Z0-9_]+', '_', topic.lower())[:50]
    out_path = OUTPUT_DIR / f"{safe_name}.json"
    if out_path.exists():
        return False
    
    # Search first to find the right article
    results = search_wikipedia(topic)
    if not results:
        print(f"  No results for: {topic}")
        return False
    
    # Get the best result
    page_title = results[0]['title']
    data = fetch_wikipedia(page_title)
    if not data:
        print(f"  Could not fetch: {topic}")
        return False
    
    extract = data.get('extract', '')
    entry = create_entry(topic, extract)
    if not entry:
        print(f"  Insufficient content: {topic}")
        return False
    
    json.dump([entry], open(out_path, 'w'), indent=2)
    print(f"  Created: {topic} -> {safe_name}.json ({len(extract)} chars)")
    return True


# ── Popular topics list ──────────────────────────────────────────────────

POPULAR_TOPICS = [
    # Science
    "Photosynthesis", "Gravity", "Quantum mechanics", "Evolution", "DNA",
    "Cell biology", "Genetics", "Protein", "Enzyme", "Virus", "Bacteria",
    "Atom", "Molecule", "Chemical reaction", "Electricity", "Magnetism",
    "Thermodynamics", "Relativity", "Light", "Sound", "Force", "Energy",
    "Fossil", "Natural selection", "Species", "Ecosystem", "Biodiversity",
    "Climate", "Weather", "Ocean", "Volcano", "Earthquake", "Mountain",
    "Planet", "Star", "Galaxy", "Solar System", "Moon",
    "Black hole", "Neutron star", "Supernova", "Nebula", "Comet",
    "Asteroid", "Telescope", "Space exploration", "NASA",
    
    # Technology
    "Artificial intelligence", "Machine learning", "Deep learning",
    "Neural network", "Natural language processing", "Computer vision",
    "Robotics", "Data science", "Algorithm", "Database", "Operating system",
    "Computer network", "Internet", "World Wide Web", "Web browser",
    "Programming language", "Python", "JavaScript", "Java", "C++",
    "HTML", "CSS", "SQL", "React", "Node.js", "Django",
    "Cybersecurity", "Cryptography", "Blockchain", "Cloud computing",
    "Virtual reality", "Augmented reality", "3D printing", "Autonomous car",
    "Electric vehicle", "Renewable energy", "Solar power", "Wind power",
    "Nuclear power", "Battery", "Semiconductor", "Transistor",
    
    # Medicine & Health
    "Human body", "Brain", "Heart", "Lungs", "Liver", "Kidney",
    "Immune system", "Nervous system", "Circulatory system",
    "Respiratory system", "Digestive system", "Skeletal system",
    "Vaccine", "Antibiotic", "Cancer", "Diabetes", "Heart disease",
    "Mental health", "Depression", "Anxiety", "Sleep", "Dream",
    "Memory", "Learning", "Attention", "Perception",
    "Nutrition", "Exercise", "Diet", "Vitamin", "Mineral",
    
    # History
    "Ancient Egypt", "Ancient Greece", "Ancient Rome", "Roman Empire",
    "Byzantine Empire", "Mongol Empire", "Ottoman Empire",
    "Middle Ages", "Renaissance", "Reformation", "Enlightenment",
    "Industrial Revolution", "French Revolution", "American Revolution",
    "Russian Revolution", "World War I", "World War II",
    "Cold War", "Vietnam War", "Korean War",
    "Silk Road", "Age of Discovery", "Colonialism",
    "Democracy", "Communism", "Capitalism", "Socialism",
    
    # Philosophy
    "Stoicism", "Epicureanism", "Existentialism", "Nihilism",
    "Absurdism", "Utilitarianism", "Deontology", "Virtue ethics",
    "Plato", "Aristotle", "Socrates", "Immanuel Kant",
    "Friedrich Nietzsche", "Jean-Paul Sartre", "Simone de Beauvoir",
    "Confucianism", "Taoism", "Buddhism", "Hinduism",
    
    # Psychology
    "Classical conditioning", "Operant conditioning", "Cognitive bias",
    "Confirmation bias", "Dunning-Kruger effect", "Placebo effect",
    "Nocebo effect", "Synesthesia", "Déjà vu", "Phantom limb",
    "Uncanny valley", "Flow state", "Neuroplasticity",
    "Attachment theory", "Maslow hierarchy of needs",
    "Cognitive behavioral therapy", "Psychoanalysis",
    
    # Nature
    "Rainforest", "Desert", "Ocean", "Coral reef", "Wetland",
    "Tundra", "Taiga", "Grassland", "Savanna",
    "Endangered species", "Extinction", "Conservation",
    "Pollination", "Germination", "Photosynthesis",
    "Food web", "Food chain", "Carbon cycle", "Nitrogen cycle",
    "Water cycle", "Climate change", "Global warming",
    
    # Arts & Culture
    "Impressionism", "Cubism", "Surrealism", "Abstract art",
    "Renaissance art", "Baroque", "Gothic architecture",
    "Classical music", "Jazz", "Rock music", "Hip hop",
    "Literature", "Poetry", "Drama", "Film", "Photography",
    
    # Mathematics
    "Algebra", "Geometry", "Calculus", "Statistics", "Probability",
    "Number theory", "Set theory", "Logic", "Topology",
    "Fibonacci sequence", "Prime number", "Pythagorean theorem",
]

# ── Main ─────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Generate KB entries from Wikipedia')
    parser.add_argument('--topics', type=str, help='Comma-separated list of topics')
    parser.add_argument('--file', type=str, help='File with one topic per line')
    parser.add_argument('--all', action='store_true', help='Generate from popular topics list')
    args = parser.parse_args()
    
    if args.topics:
        topics = [t.strip() for t in args.topics.split(',') if t.strip()]
    elif args.file:
        topics = [l.strip() for l in open(args.file) if l.strip()]
    elif args.all:
        topics = POPULAR_TOPICS
    else:
        print("Usage: python3 src/generate_kb.py --all")
        print("       python3 src/generate_kb.py --topics \"Topic1, Topic2\"")
        print("       python3 src/generate_kb.py --file topics.txt")
        return
    
    total = len(topics)
    created = 0
    skipped = 0
    
    print(f"Processing {total} topics...")
    for i, topic in enumerate(topics, 1):
        if process_topic(topic):
            created += 1
        else:
            skipped += 1
        time.sleep(0.5)  # Be nice to Wikipedia
    
    print(f"\nDone! Created: {created}, Skipped: {skipped}, Total: {total}")


if __name__ == '__main__':
    main()
