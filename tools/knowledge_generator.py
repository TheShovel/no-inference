#!/usr/bin/env python3
"""
COS Knowledge Generator — Automatically generates knowledge entries
and writes them to data/knowledge/.

Can use:
  - Ollama (local LLM, default)
  - OpenAI API
  - Built-in template generator (offline, no LLM needed)

Usage:
  # Generate 10 entries on a specific topic
  python3 tools/knowledge_generator.py --topic "quantum physics" --count 10

  # Generate continuously, covering broad topics
  python3 tools/knowledge_generator.py --mode continuous --interval 5

  # Generate using OpenAI instead of Ollama
  python3 tools/knowledge_generator.py --backend openai --topic "biology"
"""

import json
import os
import re
import sys
import time
import random
import hashlib
import argparse
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
KNOWLEDGE_DIR = ROOT / 'data' / 'knowledge'
TRACKING_FILE = ROOT / 'data' / 'knowledge' / '.generated_topics.json'

# Ensure the knowledge directory exists
KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)

# ── Topic coverage — broad categories to generate across ─────────────────────
TOPIC_CATEGORIES = {
    "science": {
        "physics": [
            "quantum mechanics", "thermodynamics", "electromagnetism",
            "nuclear physics", "relativity", "optics", "acoustics",
            "fluid dynamics", "particle physics", "astrophysics",
            "classical mechanics", "wave theory", "magnetism",
            "electricity", "energy conservation"
        ],
        "chemistry": [
            "periodic table", "chemical bonds", "organic chemistry",
            "inorganic chemistry", "acid base reactions", "oxidation reduction",
            "chemical kinetics", "thermochemistry", "biochemistry",
            "polymer chemistry", "nuclear chemistry", "analytical chemistry",
            "electrochemistry", "catalysis", "chemical equilibrium"
        ],
        "biology": [
            "cell biology", "genetics", "evolution", "ecology",
            "human anatomy", "botany", "zoology", "microbiology",
            "neuroscience", "immunology", "photosynthesis",
            "DNA replication", "protein synthesis", "mitosis meiosis",
            "food chains", "biomes", "endangered species"
        ],
        "astronomy": [
            "solar system", "stars", "galaxies", "black holes",
            "exoplanets", "cosmology", "nebulas", "comets asteroids",
            "space exploration", "mars missions", "telescopes",
            "big bang theory", "dark matter", "dark energy"
        ],
        "earth_science": [
            "plate tectonics", "volcanoes", "earthquakes", "weather patterns",
            "climate change", "oceanography", "minerals", "rock cycle",
            "erosion", "natural disasters", "water cycle",
            "atmospheric science", "geological time scale"
        ],
        "mathematics": [
            "algebra", "geometry", "calculus", "statistics",
            "probability", "number theory", "trigonometry",
            "linear algebra", "differential equations", "set theory",
            "graph theory", "topology", "fractals"
        ],
    },
    "geography": {
        "world_geography": [
            "countries", "capital cities", "rivers", "mountains",
            "oceans", "deserts", "lakes", "islands",
            "waterfalls", "canyons", "peninsulas", "archipelagos",
            "natural wonders", "time zones", "population centers"
        ],
        "culture": [
            "world languages", "religions", "festivals",
            "cultural traditions", "cuisine", "architecture styles",
            "traditional clothing", "holidays", "customs"
        ],
    },
    "history": {
        "ancient_history": [
            "ancient egypt", "ancient greece", "roman empire",
            "mesopotamia", "indus valley", "ancient china",
            "maya civilization", "inca empire", "persian empire",
            "ancient india", "phoenicians", "babylon"
        ],
        "medieval_history": [
            "middle ages", "crusades", "byzantine empire",
            "mongol empire", "ottoman empire", "feudalism",
            "vikings", "samurai", "knights", "medieval europe"
        ],
        "modern_history": [
            "world war i", "world war ii", "cold war",
            "industrial revolution", "french revolution",
            "american revolution", "space race", "exploration age",
            "renaissance", "scientific revolution", "enlightenment"
        ],
        "famous_people": [
            "scientists", "explorers", "inventors", "philosophers",
            "artists", "musicians", "writers", "political leaders",
            "activists", "mathematicians", "physicians"
        ],
    },
    "technology": {
        "computing": [
            "computer architecture", "programming languages",
            "operating systems", "databases", "computer networks",
            "cybersecurity", "cloud computing", "data structures",
            "algorithms", "software engineering", "compilers"
        ],
        "ai_ml": [
            "machine learning", "neural networks", "deep learning",
            "natural language processing", "computer vision",
            "robotics", "expert systems", "reinforcement learning",
            "transformers", "computer graphics", "virtual reality"
        ],
        "engineering": [
            "electrical engineering", "mechanical engineering",
            "civil engineering", "chemical engineering",
            "aerospace engineering", "biomedical engineering",
            "materials science", "telecommunications"
        ],
        "internet": [
            "web technologies", "blockchain", "cryptography",
            "social media", "search engines", "email protocols",
            "dns", "networking protocols", "iot"
        ],
    },
    "conversation": {
        "small_talk": [
            "greetings", "farewells", "introductions",
            "common phrases", "polite expressions", "idioms",
        ],
        "self_awareness": [
            "system capabilities", "system limitations",
            "help information", "about COS"
        ],
    },
    "arts": {
        "visual_arts": [
            "painting", "sculpture", "photography", "architecture",
            "famous paintings", "art movements", "art techniques"
        ],
        "music": [
            "music theory", "musical instruments", "music genres",
            "famous composers", "orchestra", "music production"
        ],
        "literature": [
            "literary genres", "famous authors", "poetry",
            "novels", "drama", "literary devices"
        ],
        "film": [
            "film genres", "filmmaking", "cinematography",
            "famous directors", "animation", "documentary"
        ],
    },
    "health": {
        "human_body": [
            "organs", "skeletal system", "muscular system",
            "circulatory system", "nervous system", "immune system",
            "digestive system", "respiratory system", "endocrine system"
        ],
        "medicine": [
            "common diseases", "treatments", "vaccines",
            "first aid", "nutrition", "mental health",
            "sleep science", "exercise science"
        ],
    },
    "nature": {
        "animals": [
            "mammals", "birds", "reptiles", "amphibians",
            "fish", "insects", "marine life", "prehistoric animals",
            "animal behavior", "habitats", "food chains"
        ],
        "plants": [
            "trees", "flowers", "fungi", "photosynthesis",
            "plant adaptations", "medicinal plants"
        ],
        "environment": [
            "ecosystems", "conservation", "renewable energy",
            "pollution", "sustainability", "climate"
        ],
    },
    "daily_life": {
        "food": [
            "cooking techniques", "cuisines", "ingredients",
            "beverages", "food science", "nutrition facts"
        ],
        "sports": [
            "team sports", "individual sports", "olympic games",
            "sports rules", "famous athletes", "sports history"
        ],
        "practical": [
            "home maintenance", "gardening", "budgeting",
            "time management", "communication skills",
            "study techniques", "problem solving methods"
        ],
    },
}


# ── LLM Backends ─────────────────────────────────────────────────────────────

def _call_ollama(prompt, model="llama3.2", temperature=0.7):
    """Call Ollama API for text generation."""
    url = "http://localhost:11434/api/generate"
    data = json.dumps({
        "model": model,
        "prompt": prompt,
        "temperature": temperature,
        "stream": False,
    }).encode()
    try:
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())
            return result.get("response", "").strip()
    except (urllib.error.URLError, urllib.error.HTTPError, ConnectionRefusedError) as e:
        print(f"  [ERROR] Ollama not available: {e}")
        return None


def _call_openai(prompt, model="gpt-4o-mini", temperature=0.7):
    """Call OpenAI API. Requires OPENAI_API_KEY env var."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("  [ERROR] OPENAI_API_KEY not set")
        return None

    url = "https://api.openai.com/v1/chat/completions"
    data = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
    }).encode()

    try:
        req = urllib.request.Request(url, data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            })
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())
            return result["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"  [ERROR] OpenAI API call failed: {e}")
        return None


def _generate_template(topic, count=5, existing_questions=None):
    """Generate knowledge entries using built-in templates (no LLM needed).

    Creates simple factual Q&A pairs based on the topic name.
    Useful as a fallback when no LLM is available.
    """
    existing = set(existing_questions or [])
    entries = []

    # Template patterns
    templates = {
        "what_is": [
            "What is {topic}?",
            "What does {topic} mean?",
            "How would you define {topic}?",
        ],
        "how": [
            "How does {topic} work?",
            "How is {topic} used?",
            "How does {topic} affect daily life?",
        ],
        "why": [
            "Why is {topic} important?",
            "Why does {topic} happen?",
            "Why do people study {topic}?",
        ],
        "examples": [
            "What are some examples of {topic}?",
            "What are the main types of {topic}?",
            "What are the key characteristics of {topic}?",
        ],
        "history": [
            "When was {topic} discovered?",
            "Who discovered {topic}?",
            "What is the history of {topic}?",
        ],
    }

    # Generic answers (will be customized per topic)
    def _generic_answer(q, topic):
        topic_lower = topic.lower()
        if "what is" in q.lower() or "what does" in q.lower() or "define" in q.lower():
            return f"{topic.title()} refers to a fundamental concept in this field. It involves understanding the core principles and mechanisms that define it, and it plays a crucial role in how related systems and processes function."
        elif "how does" in q.lower() or "how is" in q.lower() or "how do" in q.lower():
            return f"{topic.title()} operates through a series of well-understood mechanisms. The basic principles involve interactions between component parts, regulated by established laws and patterns. Understanding it requires studying both the individual elements and their relationships."
        elif "why is" in q.lower() or "why does" in q.lower():
            return f"{topic.title()} is important because it forms a foundation for understanding broader concepts in this domain. Its principles apply to many real-world situations and help us predict, explain, and influence outcomes."
        elif "examples" in q.lower() or "types" in q.lower() or "characteristics" in q.lower():
            return f"There are several important aspects of {topic_lower} to understand. Each has unique characteristics and applications. Studying these variations helps build a complete picture of the subject."
        elif "discovered" in q.lower() or "history" in q.lower():
            return f"The development of our understanding of {topic_lower} spans many years of research and discovery by numerous scientists and thinkers. Each contribution built upon previous knowledge, leading to our current understanding."
        return f"{topic.title()} is a significant subject with many interesting aspects to explore. It encompasses a wide range of phenomena and has practical applications in various fields."

    # Generate entries using templates
    for i in range(count):
        template_type = random.choice(list(templates.keys()))
        question_template = random.choice(templates[template_type])
        question = question_template.format(topic=topic)

        # Check for duplicates
        q_lower = question.lower().strip().rstrip("?")
        if q_lower in existing:
            continue

        answer = _generic_answer(question, topic)
        entries.append({"q": [question], "a": answer})
        existing.add(q_lower)

    return entries


# ── LLM-based generation ─────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a knowledge base generator. Generate factual Q&A pairs about the given topic.

Each entry must be:
1. FACTUALLY ACCURATE — based on well-established knowledge
2. EDUCATIONAL — teaches something useful
3. CONCISE — answers should be 1-3 paragraphs
4. SELF-CONTAINED — doesn't reference "this topic" or "this concept"

OUTPUT FORMAT (JSON array):
[
  {
    "q": ["question 1", "alternative phrasing 1", "alternative phrasing 2"],
    "a": "The answer. Should be informative and complete."
  }
]

Guidelines:
- Include 2-3 alternative phrasings for each question (different ways users might ask)
- Answers should read like a knowledgeable friend explaining, not a textbook
- Never use placeholder language like "this concept" or "this field"
- Be specific — include numbers, dates, names where relevant
- If unsure about exact numbers, use approximate language (e.g., "about", "approximately")
- Cover: what it is, how it works, why it matters, key examples"""


def _call_llm_backend(backend, prompt, topic, model="llama3.2"):
    """Call the specified LLM backend with the prompt."""
    if backend == "ollama":
        return _call_ollama(prompt, model=model)
    elif backend == "openai":
        return _call_openai(prompt)
    else:
        return None


def _generate_with_llm(topic, count=5, backend="ollama", existing_questions=None, model="llama3.2"):
    """Generate knowledge entries using an LLM."""
    existing_list = list(existing_questions or [])[:20]  # Send up to 20 existing as examples
    existing_hint = ""
    if existing_list:
        existing_hint = f"\n\nAVOID these existing questions:\n" + "\n".join(f"- {q}" for q in existing_list[:10])

    prompt = f"""{SYSTEM_PROMPT}

TOPIC: {topic}

Generate {count} diverse Q&A pairs about this topic.
Cover different aspects: what it is, how it works, history, applications, interesting facts.
{existing_hint}

Output ONLY valid JSON, no other text:"""

    response = _call_llm_backend(backend, prompt, topic, model=model)
    if not response:
        return None

    # Parse JSON from response
    try:
        # Find JSON array in the response
        json_match = re.search(r'\[.*\]', response, re.DOTALL)
        if json_match:
            entries = json.loads(json_match.group(0))
        else:
            entries = json.loads(response)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"  [ERROR] Failed to parse LLM output: {e}")
        print(f"  Raw response (first 200 chars): {response[:200]}")
        return None

    # Validate
    if not isinstance(entries, list):
        print(f"  [ERROR] LLM didn't return an array")
        return None

    validated = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        questions = entry.get("q", entry.get("patterns", []))
        answer = entry.get("a", entry.get("answer", ""))
        if isinstance(questions, str):
            questions = [questions]
        if questions and answer:
            validated.append({"q": questions, "a": answer})

    if not validated:
        print(f"  [ERROR] No valid entries in LLM output")
        return None

    print(f"  Generated {len(validated)} entries via {backend}")
    return validated


# ── Deduplication ────────────────────────────────────────────────────────────

def _normalize(text):
    """Normalize text for comparison."""
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _keyword_signature(text):
    """Extract key content words for duplicate detection."""
    words = _normalize(text).split()
    # Remove common stop words
    stop_words = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
                  'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                  'would', 'could', 'should', 'may', 'might', 'shall', 'can',
                  'what', 'when', 'where', 'which', 'who', 'whom', 'why',
                  'how', 'this', 'that', 'these', 'those', 'it', 'its',
                  'of', 'in', 'on', 'at', 'to', 'for', 'with', 'by', 'from',
                  'as', 'into', 'through', 'during', 'before', 'after',
                  'and', 'or', 'but', 'not', 'no', 'so', 'if', 'about',
                  'up', 'out', 'off', 'over', 'than', 'then', 'also',
                  'very', 'just', 'more', 'some', 'such', 'only', 'other'}
    return ' '.join(sorted(w for w in words if w not in stop_words and len(w) > 2))


def _load_existing_questions():
    """Load all existing questions from the knowledge base for dedup."""
    questions = {}  # normalized_q -> (file_path, entry_index)

    for path in sorted(KNOWLEDGE_DIR.rglob('*.json')):
        if path.name.startswith('.'):
            continue
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            if not isinstance(data, list):
                continue
            for i, entry in enumerate(data):
                qs = entry.get('q', entry.get('patterns', []))
                if isinstance(qs, str):
                    qs = [qs]
                for q in qs:
                    sig = _keyword_signature(q)
                    if sig:
                        questions[sig] = (path, i)
        except (json.JSONDecodeError, IOError):
            continue

    return questions


def _is_duplicate(new_questions, existing_questions):
    """Check if any of the new questions are duplicates of existing ones.
    Returns list of duplicate question texts.
    """
    duplicates = []
    for q in new_questions:
        sig = _keyword_signature(q)
        if sig in existing_questions:
            duplicates.append(q)
        # Also check high overlap (>= 70% keyword match)
        new_words = set(sig.split())
        for existing_sig in existing_questions:
            existing_words = set(existing_sig.split())
            if new_words and existing_words:
                overlap = len(new_words & existing_words) / max(len(new_words), len(existing_words))
                if overlap > 0.7:
                    duplicates.append(q)
                    break
    return duplicates


# ── Output writer ────────────────────────────────────────────────────────────

def _get_category_path(category_name):
    """Get the path for a category directory, creating if needed."""
    cat_dir = KNOWLEDGE_DIR / category_name
    cat_dir.mkdir(parents=True, exist_ok=True)
    return cat_dir


def _get_topic_file(category, subcategory, topic):
    """Get the filename for a specific topic within a category.
    Creates a clean filename from the topic name.
    """
    # Create a clean filename
    filename = re.sub(r'[^a-z0-9]+', '_', topic.lower()).strip('_')
    if not filename:
        filename = subcategory
    filename = filename[:40] + '.json'

    cat_dir = _get_category_path(category)
    return cat_dir / filename


def _write_entries(target_path, entries):
    """Write entries to a knowledge file, merging with existing content."""
    existing_data = []
    if target_path.exists():
        try:
            with open(target_path, 'r') as f:
                existing_data = json.load(f)
                if not isinstance(existing_data, list):
                    existing_data = []
        except (json.JSONDecodeError, IOError):
            existing_data = []

    # Merge: new entries go first, then existing
    # Filter out entries from existing that match new ones
    new_sigs = set()
    for entry in entries:
        for q in (entry.get('q', entry.get('patterns', [])) if isinstance(entry.get('q', entry.get('patterns', [])), list) else [entry.get('q', entry.get('patterns', ''))]):
            sig = _keyword_signature(q)
            if sig:
                new_sigs.add(sig)

    filtered_existing = []
    for entry in existing_data:
        keep = True
        for q in (entry.get('q', entry.get('patterns', [])) if isinstance(entry.get('q', entry.get('patterns', [])), list) else [entry.get('q', entry.get('patterns', ''))]):
            sig = _keyword_signature(q)
            if sig in new_sigs:
                keep = False
                break
        if keep:
            filtered_existing.append(entry)

    merged = entries + filtered_existing

    # Write
    with open(target_path, 'w') as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
        f.write('\n')

    # Remove empty files
    if not merged:
        target_path.unlink(missing_ok=True)

    return len(merged)


# ── Coverage tracking ────────────────────────────────────────────────────────

def _load_tracking():
    """Load topic tracking data."""
    if TRACKING_FILE.exists():
        try:
            with open(TRACKING_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {"topics": {}, "total_generated": 0, "last_run": None}


def _save_tracking(tracking):
    """Save topic tracking data."""
    tracking["last_run"] = datetime.now().isoformat()
    TRACKING_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TRACKING_FILE, 'w') as f:
        json.dump(tracking, f, indent=2)


def _get_coverage_report():
    """Generate a report of topic coverage."""
    tracking = _load_tracking()
    covered = tracking.get("topics", {})

    # Count actual files
    actual_files = list(KNOWLEDGE_DIR.rglob('*.json'))
    actual_count = sum(1 for p in actual_files if not p.name.startswith('.'))

    # Build report
    report = f"\n{'='*60}\n"
    report += "  COVERAGE REPORT\n"
    report += f"{'='*60}\n"
    report += f"  Total generated: {tracking.get('total_generated', 0)}\n"
    report += f"  Total files: {actual_count}\n"
    report += f"  Topics covered: {len(covered)}\n\n"

    # Show coverage by category
    for category, subcategories in TOPIC_CATEGORIES.items():
        total_in_cat = sum(len(topics) for topics in subcategories.values())
        covered_in_cat = sum(1 for t, info in covered.items()
                           if info.get('category') == category)
        pct = covered_in_cat / total_in_cat * 100 if total_in_cat > 0 else 0
        bar = '█' * int(pct / 5) + '░' * (20 - int(pct / 5))
        report += f"  {category:15s} {covered_in_cat:3d}/{total_in_cat:<3d} {bar} {pct:.0f}%\n"

    report += f"\n  {'='*60}"
    return report


def _pick_next_topic(tracking):
    """Pick the next topic to generate, prioritizing uncovered areas."""
    covered = tracking.get("topics", {})

    # Collect all topics with their coverage status
    all_topics = []
    uncovered = []

    for category, subcategories in TOPIC_CATEGORIES.items():
        for subcategory, topics in subcategories.items():
            for topic_name in topics:
                key = f"{category}.{subcategory}.{topic_name}"
                all_topics.append((category, subcategory, topic_name, key))
                if key not in covered:
                    uncovered.append((category, subcategory, topic_name, key))

    # Count how many entries each covered topic has
    low_coverage = []
    for key, info in covered.items():
        count = info.get('count', 0)
        if count < 3:  # Topics with fewer than 3 entries need more
            # Find the topic details
            for cat, subcat, topic_name, k in all_topics:
                if k == key:
                    low_coverage.append((cat, subcat, topic_name, key))
                    break

    # Priority: uncovered topics first, then low-coverage, then random
    if uncovered:
        chosen = random.choice(uncovered)
        print(f"  Next: NEW topic '{chosen[2]}' ({chosen[0]}/{chosen[1]})")
        return chosen

    if low_coverage:
        chosen = random.choice(low_coverage)
        print(f"  Next: EXPAND topic '{chosen[2]}' ({chosen[0]}/{chosen[1]})")
        return chosen

    # All topics covered — pick a random one to deepen
    chosen = random.choice(all_topics)
    print(f"  Next: DEEPEN topic '{chosen[2]}' ({chosen[0]}/{chosen[1]})")
    return chosen


# ── Main generation loop ─────────────────────────────────────────────────────

def generate_knowledge(topic, category=None, subcategory=None, count=5,
                       backend="ollama", ollama_model="llama3.2", force=False):
    """Generate knowledge entries for a specific topic.

    Args:
        topic: The topic to generate about
        category: Category name (auto-detected if not given)
        subcategory: Subcategory name (auto-detected if not given)
        count: Number of entries to generate
        backend: LLM backend (ollama, openai, or template)
        ollama_model: Ollama model name
        force: Skip dedup check

    Returns:
        Number of entries written, or 0 on failure
    """
    tracking = _load_tracking()
    existing_questions = _load_existing_questions()

    print(f"\n  Generating '{topic}' ({category or 'auto'}/{subcategory or 'auto'})...")

    # Generate entries
    entries = None
    retries = 3
    while retries > 0 and entries is None:
        if backend == "template":
            entries = _generate_template(topic, count * 2, set(existing_questions.keys()))
            break
        else:
            existing_q_list = list(existing_questions.keys())[:50]
            entries = _generate_with_llm(topic, count * 2, backend, existing_q_list, model=ollama_model)
        if entries is None:
            if backend != "template":
                print(f"  LLM failed, retrying... ({retries-1} left)")
                time.sleep(2)
            retries -= 1

    if entries is None:
        print(f"  [FAILED] Could not generate entries for '{topic}'")
        return 0

    # Filter duplicates
    filtered = []
    dup_count = 0
    for entry in entries:
        questions = entry.get("q", entry.get("patterns", []))
        if isinstance(questions, str):
            questions = [questions]

        dups = _is_duplicate(questions, existing_questions) if not force else []
        if dups:
            dup_count += 1
            if len(questions) == 1:
                continue
            # Remove just the duplicate phrasings
            entry["q"] = [q for q in questions if q not in dups]
            if not entry["q"]:
                continue

        filtered.append(entry)
        # Add new questions to existing set
        for q in questions:
            sig = _keyword_signature(q)
            if sig:
                existing_questions[sig] = None

    if not filtered:
        print(f"  All {len(entries)} entries were duplicates — skipped")
        return 0

    if dup_count > 0:
        print(f"  Removed {dup_count} duplicate questions")

    # Determine file path
    if category and subcategory:
        filename = re.sub(r'[^a-z0-9]+', '_', topic.lower()).strip('_')[:40] + '.json'
        target_path = KNOWLEDGE_DIR / category / filename
    else:
        # Auto-categorize
        for cat_name, subcats in TOPIC_CATEGORIES.items():
            for subcat_name, topics in subcats.items():
                if topic.lower() in [t.lower() for t in topics]:
                    category = cat_name
                    subcategory = subcat_name
                    break
        if not category:
            category = "general"
            subcategory = "general"

        filename = re.sub(r'[^a-z0-9]+', '_', topic.lower()).strip('_')[:40] + '.json'
        target_path = KNOWLEDGE_DIR / category / filename

    # Write
    target_path.parent.mkdir(parents=True, exist_ok=True)
    total = _write_entries(target_path, filtered)

    # Update tracking
    key = f"{category}.{subcategory}.{topic}"
    if key not in tracking["topics"]:
        tracking["topics"][key] = {"count": 0, "category": category}
    tracking["topics"][key]["count"] += len(filtered)
    tracking["total_generated"] += len(filtered)
    _save_tracking(tracking)

    print(f"  ✓ Wrote {len(filtered)} entries to {target_path.relative_to(ROOT)}")
    return len(filtered)


def run_continuous(backend="ollama", ollama_model="llama3.2", count_per_topic=5,
                   interval=10, max_iterations=None):
    """Run the knowledge generator continuously, covering broad topics.

    Args:
        backend: LLM backend
        ollama_model: Ollama model name
        count_per_topic: Entries per topic
        interval: Seconds between generations
        max_iterations: Max iterations (None = infinite)
    """
    print(f"\n{'='*60}")
    print(f"  COS Knowledge Generator — Continuous Mode")
    print(f"  Backend: {backend}")
    print(f"  Interval: {interval}s per topic")
    print(f'  Output: {KNOWLEDGE_DIR}')
    print(f"{'='*60}\n")

    iteration = 0
    while max_iterations is None or iteration < max_iterations:
        iteration += 1
        print(f"\n{'─'*60}")
        print(f"  Iteration {iteration}")
        print(f"{'─'*60}")

        # Pick the next topic
        tracking = _load_tracking()
        category, subcategory, topic_name, key = _pick_next_topic(tracking)

        # Generate
        before = tracking.get("total_generated", 0)
        generate_knowledge(
            topic=topic_name,
            category=category,
            subcategory=subcategory,
            count=count_per_topic,
            backend=backend,
            ollama_model=ollama_model,
        )
        after = _load_tracking().get("total_generated", 0)
        added = after - before

        # Show coverage
        if iteration % 5 == 0 or added > 0:
            print(_get_coverage_report())

        # Wait
        if max_iterations is None or iteration < max_iterations:
            print(f"\n  Waiting {interval}s before next generation...")
            time.sleep(interval)


# ── Template Generation ─────────────────────────────────────────────────────
# Knowledge templates are stored in data/knowledge/templates/ and define
# conversational response patterns. Each template has triggers, a response
# template with {context} placeholders, and a fallback.

TEMPLATE_CATEGORIES = {
    "actions": {
        "write": ["essays", "emails", "stories", "poems", "reports", "articles", "summaries", "outlines", "letters"],
        "explain": ["simple explanations", "detailed explanations", "analogies", "step-by-step guides", "comparisons"],
        "create": ["recipes", "routines", "schedules", "lists", "charts", "diagrams"],
        "code": ["functions", "algorithms", "debugging", "optimization", "architecture"],
        "analyze": ["breakdowns", "critiques", "evaluations", "comparisons", "root cause"],
    },
    "conversation": {
        "followups": ["tell me more", "continue", "go on", "give an example", "elaborate"],
        "opinions": ["asking opinions", "sharing perspectives", "agreeing", "disagreeing", "discussing"],
        "clarifications": ["clarifying", "rephrasing", "simplifying", "defining terms"],
        "meta": ["system capabilities", "help", "about COS", "status"],
    },
    "agentic": {
        "research": ["researching topics", "gathering info", "fact-checking", "deep dives"],
        "plan": ["strategic plans", "project plans", "study plans", "action plans"],
        "brainstorm": ["idea generation", "creative thinking", "problem solving", "innovation"],
        "critique": ["feedback", "review", "assessment", "evaluation"],
        "teach": ["lessons", "tutorials", "explanations", "guided learning"],
        "debate": ["arguments", "counterarguments", "discussion", "dialectic"],
        "advise": ["recommendations", "guidance", "suggestions", "best practices"],
    },
    "contextual": {
        "references": ["about that", "regarding that", "on that topic", "related to that"],
        "continuation": ["continue the conversation", "pick up where we left off", "resume"],
        "elaboration": ["expand on that", "go deeper", "more detail", "further explanation"],
        "transformation": ["make it simpler", "make it formal", "make it casual", "translate style"],
        "summarization": ["summarize", "tl;dr", "recap", "key points"],
    },
}

TEMPLATE_DIR = ROOT / 'data' / 'knowledge' / 'templates'


TEMPLATE_SYSTEM_PROMPT = """You are a conversational template generator for an AI assistant. Generate response templates that the AI can use in conversations.

Each template entry must be in this JSON format:
[
  {
    "id": "category-type-001",
    "triggers": ["trigger phrase 1", "trigger phrase 2", "trigger phrase 3"],
    "context_role": "topic",
    "template": "The response text with {context} placeholder where the conversation topic goes",
    "fallback": "Response when there is no conversation context available",
    "style": ["conversational", "informative"],
    "response_length": "medium"
  }
]

Guidelines:
- Each entry needs 2-4 trigger phrases (different ways users might ask)
- The template should use {context} where the current topic should be inserted
- The fallback is used when there's no previous conversation context
- Templates should sound natural and conversational, like a helpful assistant
- Cover different angles: definitions, examples, comparisons, applications
- Response lengths: "short" (<100 words), "medium" (100-300 words), "long" (300+ words)
- Style tags describe the tone: conversational, educational, formal, casual, creative, analytical"""


def _generate_templates_with_llm(template_type, count=5, backend="ollama", model="llama3.2"):
    """Generate template entries using an LLM."""
    prompt = f"""{TEMPLATE_SYSTEM_PROMPT}

Generate {count} diverse conversational template entries about "{template_type}".

These are response templates for when a user asks about {template_type}.
Each should be a complete, ready-to-use response that the AI can fill in with the conversation topic.

Output ONLY valid JSON array, no other text:"""

    response = _call_llm_backend(backend, prompt, template_type, model=model)
    if not response:
        return None

    try:
        json_match = re.search(r'\[.*\]', response, re.DOTALL)
        if json_match:
            entries = json.loads(json_match.group(0))
        else:
            entries = json.loads(response)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"  [ERROR] Failed to parse LLM output: {e}")
        return None

    if not isinstance(entries, list):
        return None

    validated = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        triggers = entry.get("triggers", [])
        template = entry.get("template", "")
        if isinstance(triggers, str):
            triggers = [triggers]
        if triggers and template:
            if "id" not in entry:
                entry["id"] = f"gen-{random.randint(1000,9999)}"
            if "fallback" not in entry:
                entry["fallback"] = f"I'd be happy to help with that! What specifically would you like to know about?"
            if "context_role" not in entry:
                entry["context_role"] = "topic"
            if "response_length" not in entry:
                entry["response_length"] = "medium"
            if "style" not in entry:
                entry["style"] = ["conversational"]
            validated.append(entry)

    if not validated:
        return None

    print(f"  Generated {len(validated)} template entries via {backend}")
    return validated


def _generate_templates_template(template_type, count=5):
    """Generate template entries using built-in templates (no LLM)."""
    entries = []

    question_templates = [
        (f"tell me about {{topic}}", f"I'd be happy to share what I know about {{context}}! Let me give you a comprehensive overview covering the key aspects, interesting details, and practical implications."),
        (f"explain {{topic}} to me", f"Great question about {{context}}! Let me break it down in a way that's easy to understand, starting with the fundamentals and building up to the more interesting details."),
        (f"what is {{topic}}", f"{{context}} is a fascinating subject that encompasses several key ideas and principles. Let me explain what it is and why it matters."),
        (f"give me an overview of {{topic}}", f"Here's a concise overview of {{context}}: It covers important concepts that have practical applications and interesting implications across multiple areas."),
        (f"teach me {{topic}}", f"I'd be happy to teach you about {{context}}! Let's start with the basics and work our way up. First, let's understand what makes this subject unique."),
    ]

    for i in range(min(count, len(question_templates))):
        trigger_text, template_text = question_templates[i]
        trigger_topic = template_type
        entries.append({
            "id": f"gen-{template_type[:8]}-{i+1:03d}",
            "triggers": [trigger_text.format(topic=template_type)],
            "context_role": "topic",
            "template": template_text,
            "fallback": f"I'd be happy to talk about {template_type}! What would you like to know?",
            "style": ["conversational", "educational"],
            "response_length": "medium",
        })

    return entries


def generate_templates(template_type, category=None, subcategory=None, count=5,
                       backend="ollama", ollama_model="llama3.2", force=False):
    """Generate conversation template entries."""
    tracking_file = ROOT / 'data' / '.template_tracking.json'

    # Load tracking
    tracking = {"templates": {}, "total_generated": 0}
    if tracking_file.exists():
        try:
            tracking = json.loads(tracking_file.read_text())
        except:
            pass

    print(f"\n  Generating template '{template_type}' ({category or 'auto'}/{subcategory or 'auto'})...")

    # Load existing templates for dedup
    existing_triggers = set()
    for path in sorted(TEMPLATE_DIR.rglob('*.json')):
        if path.name.startswith('.'):
            continue
        try:
            data = json.loads(path.read_text())
            if isinstance(data, list):
                for entry in data:
                    triggers = entry.get('triggers', [])
                    if isinstance(triggers, str):
                        triggers = [triggers]
                    for t in triggers:
                        existing_triggers.add(t.lower().strip())
        except:
            pass

    # Generate
    entries = None
    retries = 3
    while retries > 0 and entries is None:
        if backend == "template":
            entries = _generate_templates_template(template_type, count * 2)
            break
        else:
            entries = _generate_templates_with_llm(template_type, count * 2, backend, ollama_model)
        if entries is None:
            if backend != "template":
                print(f"  LLM failed, retrying... ({retries-1} left)")
                time.sleep(2)
            retries -= 1

    if entries is None:
        print(f"  [FAILED] Could not generate templates for '{template_type}'")
        return 0

    # Filter duplicates
    filtered = []
    dup_count = 0
    for entry in entries:
        triggers = entry.get('triggers', [])
        if isinstance(triggers, str):
            triggers = [triggers]
        
        # Check for duplicates
        new_triggers = []
        for t in triggers:
            tl = t.lower().strip()
            if tl in existing_triggers:
                dup_count += 1
            else:
                new_triggers.append(t)
                existing_triggers.add(tl)
        
        if not new_triggers:
            continue
        entry['triggers'] = new_triggers
        filtered.append(entry)

    if not filtered:
        print(f"  All {len(entries)} entries were duplicates — skipped")
        return 0

    if dup_count > 0:
        print(f"  Removed {dup_count} duplicate triggers")

    # Determine file path
    if category and subcategory:
        filename = f"{subcategory}.json"
        target_path = TEMPLATE_DIR / category / filename
    else:
        # Auto-categorize: match by key name or value
        tl = template_type.lower()
        for cat_name, subcats in TEMPLATE_CATEGORIES.items():
            for subcat_name, types in subcats.items():
                if tl == subcat_name.lower() or tl in [t.lower() for t in types]:
                    category = cat_name
                    subcategory = subcat_name
                    break
        if not category:
            category = "conversation"
            subcategory = "followups"
        target_path = TEMPLATE_DIR / category / f"{subcategory}.json"

    # Merge with existing
    target_path.parent.mkdir(parents=True, exist_ok=True)
    existing_data = []
    if target_path.exists():
        try:
            existing_data = json.loads(target_path.read_text())
            if not isinstance(existing_data, list):
                existing_data = []
        except:
            existing_data = []

    # Remove existing entries with duplicate IDs
    new_ids = {e.get('id', '') for e in filtered}
    filtered_existing = [e for e in existing_data if e.get('id', '') not in new_ids]
    merged = filtered + filtered_existing

    with open(target_path, 'w') as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
        f.write('\n')

    # Update tracking
    key = f"{category}.{subcategory}.{template_type}"
    if key not in tracking["templates"]:
        tracking["templates"][key] = {"count": 0, "category": category}
    tracking["templates"][key]["count"] += len(filtered)
    tracking["total_generated"] += len(filtered)
    tracking_file.write_text(json.dumps(tracking, indent=2))

    print(f"  ✓ Wrote {len(filtered)} template entries to {target_path.relative_to(ROOT)}")
    return len(filtered)


def run_template_continuous(backend="ollama", ollama_model="llama3.2", count_per_type=5,
                            interval=10, max_iterations=None):
    """Run the template generator continuously."""
    tracking_file = ROOT / 'data' / '.template_tracking.json'

    print(f"\n{'='*60}")
    print(f"  COS Template Generator — Continuous Mode")
    print(f"  Backend: {backend}")
    print(f"  Output: {TEMPLATE_DIR}")
    print(f"{'='*60}\n")

    # Collect all template types
    all_types = []
    for cat, subcats in TEMPLATE_CATEGORIES.items():
        for subcat, types in subcats.items():
            for t in types:
                all_types.append((cat, subcat, t))

    iteration = 0
    while max_iterations is None or iteration < max_iterations:
        iteration += 1
        print(f"\n{'─'*60}")
        print(f"  Iteration {iteration}")
        print(f"{'─'*60}")

        # Pick next type
        tracking = json.loads(tracking_file.read_text()) if tracking_file.exists() else {"templates": {}, "total_generated": 0}
        covered = tracking.get("templates", {})

        uncovered = [(c, s, t) for c, s, t in all_types if f"{c}.{s}.{t}" not in covered]
        if uncovered:
            cat, subcat, t = random.choice(uncovered)
            print(f"  Next: NEW template '{t}' ({cat}/{subcat})")
        else:
            cat, subcat, t = random.choice(all_types)
            print(f"  Next: DEEPEN template '{t}' ({cat}/{subcat})")

        generate_templates(
            template_type=t,
            category=cat,
            subcategory=subcat,
            count=count_per_type,
            backend=backend,
            ollama_model=ollama_model,
        )

        if max_iterations is None or iteration < max_iterations:
            print(f"\n  Waiting {interval}s before next generation...")
            time.sleep(interval)


# ── CLI ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="COS Knowledge & Template Generator")
    parser.add_argument("--topic", help="Specific topic to generate about")
    parser.add_argument("--type", choices=["knowledge", "template"],
                       default="knowledge", help="Type of content to generate")
    parser.add_argument("--category", help="Category (science, history, or template category)")
    parser.add_argument("--subcategory", help="Subcategory")
    parser.add_argument("--count", type=int, default=5, help="Entries per topic")
    parser.add_argument("--backend", choices=["ollama", "openai", "template"],
                       default="template", help="Generation backend")
    parser.add_argument("--model", default="llama3.2", help="Ollama model name")
    parser.add_argument("--mode", choices=["once", "continuous"],
                       default="once", help="Run mode")
    parser.add_argument("--interval", type=int, default=10,
                       help="Seconds between generations (continuous mode)")
    parser.add_argument("--iterations", type=int, default=None,
                       help="Max iterations (continuous mode)")
    parser.add_argument("--force", action="store_true",
                       help="Skip duplicate check")
    parser.add_argument("--coverage", action="store_true",
                       help="Show coverage report and exit")

    args = parser.parse_args()

    # Determine output directory
    if args.type == "template":
        output_dir = TEMPLATE_DIR
        output_name = "templates"
    else:
        output_dir = KNOWLEDGE_DIR
        output_name = "knowledge"

    # Print banner
    print(f"\n╔{'═'*58}╗")
    print(f"║  COS {output_name.upper()} Generator{' '*(40-len(output_name))}║")
    print(f"║  Output: {str(output_dir):>44s} ║")
    print(f"╚{'═'*58}╝")

    # Coverage report only
    if args.coverage:
        print(_get_coverage_report())
        return

    # Check LLM backend availability
    if args.backend == "ollama":
        try:
            test = _call_ollama("Say 'OK'", model=args.model)
            if test:
                print(f"  ✓ Ollama available (model: {args.model})")
            else:
                print(f"  ⚠ Ollama not responding, falling back to template")
                args.backend = "template"
        except:
            print(f"  ⚠ Ollama not available, falling back to template")
            args.backend = "template"
    elif args.backend == "openai":
        if os.environ.get("OPENAI_API_KEY"):
            print(f"  ✓ OpenAI API key found")
        else:
            print(f"  ⚠ OPENAI_API_KEY not set, falling back to template")
            args.backend = "template"

    if args.backend == "template":
        print(f"  ℹ Using template-based generation (no LLM)")
    print(f"  ℹ Output directory: {output_dir}")

    # Run
    if args.type == "template":
        if args.mode == "continuous":
            run_template_continuous(
                backend=args.backend,
                ollama_model=args.model,
                count_per_type=args.count,
                interval=args.interval,
                max_iterations=args.iterations,
            )
        elif args.topic:
            generate_templates(
                template_type=args.topic,
                category=args.category,
                subcategory=args.subcategory,
                count=args.count,
                backend=args.backend,
                ollama_model=args.model,
                force=args.force,
            )
        else:
            # Auto-pick a template type
            all_types = []
            for cat, subcats in TEMPLATE_CATEGORIES.items():
                for subcat, types in subcats.items():
                    for t in types:
                        all_types.append((cat, subcat, t))
            if all_types:
                cat, subcat, t = random.choice(all_types)
                generate_templates(
                    template_type=t,
                    category=cat,
                    subcategory=subcat,
                    count=args.count,
                    backend=args.backend,
                    ollama_model=args.model,
                    force=args.force,
                )
    else:
        # Knowledge mode
        if args.mode == "continuous":
            run_continuous(
                backend=args.backend,
                ollama_model=args.model,
                count_per_topic=args.count,
                interval=args.interval,
                max_iterations=args.iterations,
            )
        elif args.topic:
            generate_knowledge(
                topic=args.topic,
                category=args.category,
                subcategory=args.subcategory,
                count=args.count,
                backend=args.backend,
                ollama_model=args.model,
                force=args.force,
            )
        else:
            # Single iteration with auto-topic selection
            tracking = _load_tracking()
            cat, subcat, topic, key = _pick_next_topic(tracking)
            generate_knowledge(
                topic=topic,
                category=cat,
                subcategory=subcat,
                count=args.count,
                backend=args.backend,
                ollama_model=args.model,
                force=args.force,
            )

    # Show final coverage
    if args.type == "template":
        print(f"\n  Template generation complete. See {TEMPLATE_DIR}")
    else:
        print(_get_coverage_report())


if __name__ == "__main__":
    main()
