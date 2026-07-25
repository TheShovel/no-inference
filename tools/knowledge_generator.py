#!/usr/bin/env python3
"""
COS Infinite Knowledge Generator — Self-discovering, ever-expanding knowledge base.

Design:
  - No fixed topic list. Topics are discovered dynamically by branching from
    existing topics, using LLM suggestions, or template-based generation.
  - Topics form a tree: Category → Subcategory → Topic → Sub-topic → ...
  - Each file holds at most MAX_ENTRIES_PER_FILE entries; when exceeded,
    the file is split into numbered parts (topic_1.json, topic_2.json, ...).
  - Coverage is measured by tree depth and breadth, not against a fixed list.
  - Runs indefinitely, generating broader AND deeper over time.

Usage:
  # Single generation (auto-picks topic)
  python3 tools/knowledge_generator.py

  # Continuous infinite mode
  python3 tools/knowledge_generator.py --mode continuous --interval 3

  # Generate with Ollama for smarter topic discovery
  python3 tools/knowledge_generator.py --mode continuous --backend ollama --model llama3.2

  # Show coverage report
  python3 tools/knowledge_generator.py --coverage
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
TEMPLATE_DIR = ROOT / 'data' / 'knowledge' / 'templates'
TRACKING_FILE = ROOT / 'data' / 'knowledge' / '.generated_topics.json'

KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)

# ── Configuration ────────────────────────────────────────────────────────────
MAX_ENTRIES_PER_FILE = 50          # Split when a file exceeds this
MAX_TOPIC_DEPTH = 8                # How deep the topic tree can grow
SEED_TOPICS_PER_RUN = 3            # New sub-topics to suggest per generation
COVERAGE_DEPTH_TARGET = 3          # Target depth before broadening
MIN_ENTRIES_FOR_BRANCH = 5         # Min entries before suggesting sub-topics

# ── Seed topics (starting points — the tree grows from these) ────────────────
# These are just the initial roots. The system adds new branches dynamically.
SEED_TOPICS = [
    # Format: (category, subcategory, topic)
    ("science", "physics", "quantum mechanics"),
    ("science", "physics", "thermodynamics"),
    ("science", "physics", "electromagnetism"),
    ("science", "chemistry", "chemical bonds"),
    ("science", "chemistry", "organic chemistry"),
    ("science", "biology", "cell biology"),
    ("science", "biology", "genetics"),
    ("science", "astronomy", "solar system"),
    ("science", "astronomy", "stars"),
    ("science", "earth_science", "plate tectonics"),
    ("science", "earth_science", "climate change"),
    ("science", "mathematics", "algebra"),
    ("science", "mathematics", "calculus"),
    ("geography", "world_geography", "countries"),
    ("geography", "world_geography", "oceans"),
    ("geography", "culture", "world languages"),
    ("history", "ancient_history", "ancient egypt"),
    ("history", "ancient_history", "roman empire"),
    ("history", "medieval_history", "middle ages"),
    ("history", "modern_history", "world war ii"),
    ("history", "famous_people", "scientists"),
    ("technology", "computing", "programming languages"),
    ("technology", "computing", "computer architecture"),
    ("technology", "ai_ml", "machine learning"),
    ("technology", "engineering", "electrical engineering"),
    ("technology", "internet", "web technologies"),
    ("arts", "visual_arts", "painting"),
    ("arts", "music", "music theory"),
    ("arts", "literature", "poetry"),
    ("arts", "film", "filmmaking"),
    ("health", "human_body", "organs"),
    ("health", "medicine", "common diseases"),
    ("nature", "animals", "mammals"),
    ("nature", "plants", "trees"),
    ("nature", "environment", "ecosystems"),
    ("daily_life", "food", "cooking techniques"),
    ("daily_life", "sports", "team sports"),
    ("daily_life", "practical", "time management"),
]

# ── Template seed types (starting points for template generation) ────────────
SEED_TEMPLATE_TYPES = [
    ("actions", "write", "essays"),
    ("actions", "explain", "simple explanations"),
    ("actions", "code", "functions"),
    ("actions", "analyze", "breakdowns"),
    ("conversation", "followups", "tell me more"),
    ("conversation", "opinions", "asking opinions"),
    ("conversation", "clarifications", "clarifying"),
    ("agentic", "research", "researching topics"),
    ("agentic", "plan", "strategic plans"),
    ("agentic", "brainstorm", "idea generation"),
    ("agentic", "teach", "lessons"),
    ("agentic", "advise", "recommendations"),
    ("contextual", "references", "about that"),
    ("contextual", "elaboration", "expand on that"),
    ("contextual", "summarization", "summarize"),
]

# ── Domain extension templates (for generating new sub-topics without LLM) ───
# These produce sub-topics based on a parent topic's name pattern.
DOMAIN_EXTENSIONS = {
    "quantum": ["quantum entanglement", "quantum computing", "quantum field theory",
                "quantum cryptography", "quantum teleportation", "quantum decoherence",
                "quantum superposition", "quantum tunneling"],
    "biology": ["molecular biology", "marine biology", "evolutionary biology",
                "developmental biology", "structural biology", "systems biology"],
    "chemistry": ["physical chemistry", "green chemistry", "computational chemistry",
                  "surface chemistry", "supramolecular chemistry", "food chemistry"],
    "physics": ["theoretical physics", "experimental physics", "applied physics",
                "computational physics", "medical physics", "plasma physics"],
    "engineering": ["software engineering", "genetic engineering", "systems engineering",
                    "environmental engineering", "industrial engineering"],
    "science": ["data science", "environmental science", "materials science",
                "cognitive science", "forensic science", "sports science"],
    "history": ["cultural history", "economic history", "military history",
                "social history", "natural history", "art history"],
    "math": ["applied mathematics", "pure mathematics", "discrete mathematics",
             "computational mathematics", "mathematical modeling"],
    "computer": ["parallel computing", "quantum computing", "distributed computing",
                 "high performance computing", "edge computing", "cloud computing"],
    "machine": ["supervised learning", "unsupervised learning", "semi-supervised learning",
                "transfer learning", "federated learning", "active learning"],
    "deep": ["convolutional neural networks", "recurrent neural networks",
             "generative adversarial networks", "transformers",
             "diffusion models", "autoencoders"],
    "data": ["data mining", "data visualization", "data engineering",
             "data warehousing", "data governance", "data quality"],
    "web": ["web development", "web design", "web security",
            "web accessibility", "web performance", "web APIs"],
    "health": ["public health", "mental health", "environmental health",
               "occupational health", "digital health", "global health"],
    "sport": ["professional sports", "sports science", "sports medicine",
              "sports psychology", "sports management", "sports analytics"],
}

# ── Sub-topic generation prompts ────────────────────────────────────────────
# Used when no domain extension matches and no LLM is available.
SUBTOPIC_TEMPLATES = {
    "applications": [
        "applications of {topic}",
        "practical uses of {topic}",
        "{topic} in industry",
        "{topic} in everyday life",
        "real world {topic}",
    ],
    "types": [
        "types of {topic}",
        "categories of {topic}",
        "classification of {topic}",
        "varieties of {topic}",
        "different kinds of {topic}",
    ],
    "aspects": [
        "history of {topic}",
        "future of {topic}",
        "fundamentals of {topic}",
        "importance of {topic}",
        "challenges in {topic}",
    ],
    "related": [
        "{topic} vs alternatives",
        "{topic} examples",
        "how {topic} works",
        "benefits of {topic}",
        "drawbacks of {topic}",
    ],
    "advanced": [
        "advanced {topic}",
        "introduction to {topic}",
        "beginner's guide to {topic}",
        "the science behind {topic}",
        "modern {topic}",
    ],
}


# ═════════════════════════════════════════════════════════════════════════════
# TOPIC TREE
# ═════════════════════════════════════════════════════════════════════════════

def _load_tracking():
    """Load the topic tracking database."""
    if TRACKING_FILE.exists():
        try:
            data = json.loads(TRACKING_FILE.read_text())
            # Ensure structure
            if "topics" not in data:
                data["topics"] = {}
            if "total_generated" not in data:
                data["total_generated"] = 0
            if "branches" not in data:
                data["branches"] = {}
            if "categories" not in data:
                data["categories"] = {}
            return data
        except Exception:
            pass
    return {"topics": {}, "total_generated": 0, "branches": {}, "categories": {}}


def _save_tracking(tracking):
    """Save the topic tracking database."""
    TRACKING_FILE.write_text(json.dumps(tracking, indent=2))


def _load_existing_questions():
    """Load all existing questions from knowledge files for dedup."""
    questions = {}
    for path in sorted(KNOWLEDGE_DIR.rglob('*.json')):
        if path.name.startswith('.'):
            continue
        try:
            data = json.loads(path.read_text())
            if isinstance(data, list):
                for entry in data:
                    qs = entry.get("q", entry.get("patterns", []))
                    if isinstance(qs, str):
                        qs = [qs]
                    for q in qs:
                        sig = _keyword_signature(q)
                        if sig:
                            questions[sig] = path.name
        except Exception:
            pass
    return questions


def _keyword_signature(text):
    """Generate a keyword-based signature for dedup."""
    text = text.lower().strip()
    # Keep only content words (remove very common words)
    stop_words = {'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been',
                  'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                  'would', 'could', 'should', 'may', 'might', 'can', 'shall',
                  'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from',
                  'as', 'into', 'through', 'during', 'before', 'after',
                  'above', 'below', 'between', 'out', 'off', 'over', 'under',
                  'again', 'further', 'then', 'once', 'here', 'there', 'when',
                  'where', 'why', 'how', 'all', 'each', 'every', 'both',
                  'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor',
                  'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very',
                  'just', 'because', 'but', 'and', 'or', 'if', 'while', 'what',
                  'which', 'who', 'whom', 'this', 'that', 'these', 'those',
                  'it', 'its', 'me', 'my', 'we', 'our', 'you', 'your',
                  'he', 'him', 'his', 'she', 'her', 'they', 'them', 'their'}
    words = [w for w in re.findall(r'\w+', text) if w not in stop_words]
    if not words:
        return None
    # Use the first 3-5 content words as signature
    sig = ' '.join(words[:5])
    return sig


def _is_duplicate(questions, existing_questions):
    """Check if any question in the list is a duplicate. Returns list of dups."""
    dups = []
    for q in questions:
        sig = _keyword_signature(q)
        if sig and sig in existing_questions:
            dups.append(q)
    return dups


def _normalize(text):
    """Normalize text for comparison."""
    return re.sub(r'\s+', ' ', text.lower().strip())


def _get_topic_key(category, subcategory, topic):
    """Get the tracking key for a topic."""
    return f"{category}.{subcategory}.{topic}"


# ═════════════════════════════════════════════════════════════════════════════
# TOPIC DISCOVERY — The engine that drives infinite growth
# ═════════════════════════════════════════════════════════════════════════════

def _ensure_seed_topics(tracking):
    """Ensure seed topics exist in the tracking database."""
    seeded = False
    for cat, subcat, topic in SEED_TOPICS:
        key = _get_topic_key(cat, subcat, topic)
        if key not in tracking["topics"]:
            tracking["topics"][key] = {
                "count": 0, "category": cat, "subcategory": subcat,
                "depth": 0, "parent": None, "children": [],
                "first_generated": None
            }
            seeded = True
        # Ensure category exists
        if cat not in tracking["categories"]:
            tracking["categories"][cat] = {"count": 0, "subcategories": {}}
        if subcat not in tracking["categories"][cat]["subcategories"]:
            tracking["categories"][cat]["subcategories"][subcat] = {"count": 0}
    if seeded:
        _save_tracking(tracking)


def _suggest_subtopics(topic, category, subcategory, tracking, count=5):
    """Suggest sub-topics for a given topic, branching the knowledge tree.

    Uses three strategies in order:
    1. Domain extension patterns (knowledge-free)
    2. Topic re-combination (mix of existing topics)
    3. Template-based generation
    """
    topic_lower = topic.lower()
    suggestions = []

    # Strategy 1: Domain extension patterns
    for pattern_key, extensions in DOMAIN_EXTENSIONS.items():
        if pattern_key in topic_lower or topic_lower in pattern_key:
            for ext in extensions:
                if ext.lower() != topic_lower:
                    suggestions.append(ext)
            if suggestions:
                break

    # Strategy 2: Template-based sub-topics
    if len(suggestions) < count:
        for group, templates in SUBTOPIC_TEMPLATES.items():
            for tmpl in templates:
                sub = tmpl.format(topic=topic)
                # Capitalize
                sub = sub[0].upper() + sub[1:] if sub else sub
                if sub.lower() != topic_lower:
                    suggestions.append(sub)

    # Strategy 3: Cross-pollinate from sibling topics
    if len(suggestions) < count * 2:
        # Find sibling topics in the same subcategory
        siblings = []
        for key, info in tracking["topics"].items():
            if (info.get("category") == category and
                info.get("subcategory") == subcategory and
                key != _get_topic_key(category, subcategory, topic)):
                siblings.append(info.get("parent") or key.split(".")[-1])

        # Generate combined topics
        if siblings:
            for sib in random.sample(siblings, min(len(siblings), 3)):
                for prefix in ["comparing", "relationship between", "difference between"]:
                    suggestions.append(f"{prefix} {topic} and {sib}")

    # Remove duplicates and self-references
    seen = set()
    unique = []
    for s in suggestions:
        sl = s.lower().strip()
        if sl not in seen and sl != topic_lower:
            seen.add(sl)
            unique.append(s)

    # Prefer shorter, more general suggestions
    unique.sort(key=lambda x: len(x))
    return unique[:count * 2]


def _get_domain_files(topic_dir, base_name):
    """Get all files for a topic, sorted by part number."""
    pattern = re.compile(r'^' + re.escape(base_name) + r'(?:(\d+))?\.json$')
    files = []
    for path in topic_dir.glob(f"{base_name}*.json"):
        m = pattern.match(path.name)
        if m:
            part = int(m.group(1)) if m.group(1) else 0
            files.append((part, path))
    files.sort()
    return files


def _get_category_path(category, subcategory):
    """Get the directory for a category/subcategory."""
    path = KNOWLEDGE_DIR / category
    return path


def _write_entries(target_path, entries):
    """Write entries to a JSON file, merging with existing content."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if target_path.exists():
        try:
            existing = json.loads(target_path.read_text())
            if not isinstance(existing, list):
                existing = []
        except Exception:
            existing = []

    merged = existing + entries
    with open(target_path, 'w') as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
        f.write('\n')
    return len(entries)


def _find_or_create_file(topic, category, subcategory):
    """Find the right file for a topic, splitting if needed.

    Returns (file_path, is_new_file). Creates numbered parts when
    a file exceeds MAX_ENTRIES_PER_FILE entries.
    """
    category_dir = KNOWLEDGE_DIR / category
    category_dir.mkdir(parents=True, exist_ok=True)

    base_name = re.sub(r'[^a-z0-9]+', '_', topic.lower()).strip('_')[:40]

    # Find existing files for this topic
    files = _get_domain_files(category_dir, base_name)

    if not files:
        # No file yet — create it
        return category_dir / f"{base_name}.json", True

    # Check if the latest file has room
    latest_part, latest_path = files[-1]
    try:
        data = json.loads(latest_path.read_text())
        if isinstance(data, list) and len(data) < MAX_ENTRIES_PER_FILE:
            return latest_path, False
    except Exception:
        pass

    # Need to split — create new numbered part
    next_part = latest_part + 1
    return category_dir / f"{base_name}{next_part}.json", True


\def _generate_template(topic, count=10):
    """Generate knowledge entries using built-in templates (no LLM)."""
    entries = []
    question_patterns = [
        (f"What is {{topic}}?", f"{{topic}} refers to a concept that encompasses several important ideas. At its core, it involves understanding the fundamental principles and how they apply in various contexts. This subject has broad implications across multiple domains."),
        (f"Explain {{topic}} in simple terms", f"Great question! Let me break down {{topic}} in simple terms. Think of it as a way of understanding how things work in this particular area. The key ideas include several interconnected concepts that together form a complete picture."),
        (f"How does {{topic}} work?", f"{{topic}} works through a combination of fundamental principles and practical applications. The process involves several key steps that build on each other to create the overall system or concept."),
        (f"What are the key aspects of {{topic}}?", f"The key aspects of {{topic}} include its core principles, practical applications, historical development, and its impact on related fields. Each of these areas offers valuable insights into the subject."),
        (f"Why is {{topic}} important?", f"{{topic}} is important because it helps us understand and interact with the world more effectively. Its principles apply to many real-world situations and have led to significant advances in various fields."),
        (f"Tell me about the history of {{topic}}", f"The history of {{topic}} spans several important developments and discoveries. Early foundations were laid by pioneers in the field, and subsequent advances have built upon this knowledge to create the comprehensive understanding we have today."),
        (f"What are examples of {{topic}}?", f"There are many fascinating examples of {{topic}} in action. These range from everyday applications to specialized uses in industry and research. Each example illustrates different aspects of how this subject matters in practice."),
        (f"How is {{topic}} used today?", f"Today, {{topic}} is used in numerous ways across different sectors. Modern applications include practical implementations in technology, research, education, and industry, demonstrating its ongoing relevance and importance."),
        (f"What are the benefits of {{topic}}?", f"The benefits of {{topic}} are numerous and far-reaching. They include improved understanding, practical applications, technological advances, and better decision-making in areas where this knowledge is applied."),
        (f"What are common misconceptions about {{topic}}?", f"There are several common misconceptions about {{topic}}. Let me clarify the most important ones: first, it's more nuanced than many people realize; second, its applications are broader than commonly assumed; and third, our understanding continues to evolve with new discoveries."),
    ]
    for i in range(min(count, len(question_patterns))):
        q_text, a_text = question_patterns[i]
        entries.append({
            "q": [q_text.format(topic=topic)],
            "a": a_text.format(topic=topic),
        })

    if count > len(question_patterns):
        # Generate more with variations
        for i in range(count - len(question_patterns)):
            modifiers = ["detailed overview of", "introduction to", "guide to",
                         "fundamentals of", "comprehensive look at"]
            m = modifiers[i % len(modifiers)]
            entries.append({
                "q": [f"Give me a {m} {topic}"],
                "a": f"Here's a comprehensive overview of {topic}. This subject encompasses several key areas of knowledge and has important implications for how we understand and interact with the world around us. The fundamental principles provide a framework for deeper exploration, while practical applications demonstrate its real-world value.",
            })
    return entries


# ═════════════════════════════════════════════════════════════════════════════
# LLM BACKENDS
# ═════════════════════════════════════════════════════════════════════════════

def _call_ollama(prompt, model="llama3.2", temperature=0.7):
    """Call Ollama API for text generation."""
    url = "http://localhost:11434/api/generate"
    data = json.dumps({
        "model": model,
        "prompt": prompt,
        "temperature": temperature,
        "stream": False,
    }).encode()
    req = urllib.request.Request(url, data=data,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode())
            return result.get("response", "")
    except Exception as e:
        print(f"  [Ollama error] {e}")
        return ""


def _call_openai(prompt, model="gpt-4o-mini", temperature=0.7):
    """Call OpenAI API for text generation."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return ""
    url = "https://api.openai.com/v1/chat/completions"
    data = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
    }).encode()
    req = urllib.request.Request(url, data=data,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {api_key}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode())
            return result["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"  [OpenAI error] {e}")
        return ""


def _call_llm_backend(backend, prompt, context="", model="llama3.2"):
    """Call the configured LLM backend."""
    if backend == "ollama":
        return _call_ollama(prompt, model=model)
    elif backend == "openai":
        return _call_openai(prompt, model=model)
    return ""


def _generate_with_llm(topic, count=10, backend="ollama", model="llama3.2",
                        existing_questions=None):
    """Generate knowledge entries using an LLM."""
    if existing_questions is None:
        existing_questions = []

    system_prompt = """You are a knowledge base generator. Generate factual Q&A pairs about a topic.

Each entry must be in this JSON format:
[
  {
    "q": ["question1", "question2", "question3"],
    "a": "Detailed answer to the questions"
  }
]

Guidelines:
- Each entry should have 1-3 different phrasings of the same question
- Answers should be informative, factual, and 2-5 sentences
- Cover different aspects: definitions, applications, history, examples
- Make questions specific and concrete, not generic
- Answers should be self-contained and understandable without context"""

    avoid_text = ""
    if existing_questions:
        avoid_text = "\nAVOID these existing questions (generate NEW ones):\n"
        for q in existing_questions[:20]:
            avoid_text += f"  - {q}\n"

    prompt = f"""{system_prompt}

Generate {count} Q&A entries about: {topic}
{topic} is in the domain of general knowledge.
{avoid_text}

Output ONLY valid JSON array, no other text:"""

    response = _call_llm_backend(backend, prompt, topic, model=model)
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
        qs = entry.get("q", entry.get("questions", []))
        answer = entry.get("a", entry.get("answer", ""))
        if isinstance(qs, str):
            qs = [qs]
        if qs and answer:
            validated.append({"q": qs, "a": answer})

    if not validated:
        return None

    print(f"  Generated {len(validated)} entries via {backend} ({model})")
    return validated


# ═════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE GENERATION
# ═════════════════════════════════════════════════════════════════════════════

def generate_knowledge(topic, category=None, subcategory=None, count=5,
                       backend="template", ollama_model="llama3.2", force=False,
                       depth=0):
    """Generate knowledge entries for a specific topic.

    Returns:
        Number of entries written, or 0 on failure
    """
    tracking = _load_tracking()
    existing_questions = _load_existing_questions()

    # Auto-categorize if not given
    if not category:
        # Try to find the topic in existing tracking
        for key, info in tracking["topics"].items():
            parts = key.split(".")
            if len(parts) == 3 and parts[2].lower() == topic.lower():
                category = parts[0]
                subcategory = parts[1]
                break
        if not category:
            category = "general"
            subcategory = "general"

    if not subcategory:
        subcategory = "general"

    print(f"\n  Generating '{topic}' ({category}/{subcategory}) [depth={depth}]...")

    # Generate entries
    entries = None
    retries = 3
    while retries > 0 and entries is None:
        if backend == "template":
            entries = _generate_template(topic, count * 2)
            break
        else:
            existing_q_list = list(existing_questions.keys())[:50]
            entries = _generate_with_llm(topic, count * 2, backend,
                                          ollama_model, existing_questions=existing_q_list)
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
            entry["q"] = [q for q in questions if q not in dups]
            if not entry["q"]:
                continue

        filtered.append(entry)
        for q in questions:
            sig = _keyword_signature(q)
            if sig:
                existing_questions[sig] = None

    if not filtered:
        print(f"  All {len(entries)} entries were duplicates — skipped")
        return 0

    if dup_count > 0:
        print(f"  Removed {dup_count} duplicate questions")

    # Find or create file (with auto-splitting)
    file_path, is_new = _find_or_create_file(topic, category, subcategory)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    total = _write_entries(file_path, filtered)

    # Update tracking
    key = _get_topic_key(category, subcategory, topic)
    if key not in tracking["topics"]:
        tracking["topics"][key] = {
            "count": 0, "category": category, "subcategory": subcategory,
            "depth": depth, "parent": None, "children": [],
            "first_generated": datetime.now().isoformat()
        }
    tracking["topics"][key]["count"] += len(filtered)
    tracking["topics"][key]["last_generated"] = datetime.now().isoformat()
    tracking["total_generated"] += len(filtered)

    # Update category tracking
    if category not in tracking["categories"]:
        tracking["categories"][category] = {"count": 0, "subcategories": {}}
    if subcategory not in tracking["categories"][category]["subcategories"]:
        tracking["categories"][category]["subcategories"][subcategory] = {"count": 0}
    tracking["categories"][category]["count"] += len(filtered)
    tracking["categories"][category]["subcategories"][subcategory]["count"] += len(filtered)

    _save_tracking(tracking)

    file_ref = file_path.relative_to(ROOT)
    print(f"  ✓ Wrote {len(filtered)} entries to {file_ref}" +
          (" (new file)" if is_new else ""))
    return len(filtered)


def _discover_new_branches(tracking, count=3):
    """Discover new topic branches to grow the knowledge tree.

    Returns a list of (category, subcategory, topic, depth) tuples to generate next.
    """
    candidates = []

    # Strategy 1: Seed topics that haven't been touched
    for cat, subcat, topic in SEED_TOPICS:
        key = _get_topic_key(cat, subcat, topic)
        info = tracking["topics"].get(key, {})
        if info.get("count", 0) == 0:
            candidates.append((cat, subcat, topic, 0))

    # Strategy 2: Existing topics ready to branch (have enough entries)
    for key, info in tracking["topics"].items():
        parts = key.split(".")
        if len(parts) != 3:
            continue
        cat, subcat, topic = parts
        depth = info.get("depth", 0)

        if info.get("count", 0) >= MIN_ENTRIES_FOR_BRANCH and depth < MAX_TOPIC_DEPTH:
            # Generate sub-topics
            subs = _suggest_subtopics(topic, cat, subcat, tracking, count=count)
            for sub in subs:
                sub_key = _get_topic_key(cat, subcat, sub)
                if sub_key not in tracking["topics"]:
                    candidates.append((cat, subcat, sub, depth + 1))
                    if len(candidates) >= 20:
                        break
            if len(candidates) >= 20:
                break

    # Strategy 3: Fill in missing categories (discover new subcategories)
    existing_cats = set()
    for key in tracking["topics"]:
        parts = key.split(".")
        if len(parts) == 3:
            existing_cats.add((parts[0], parts[1]))

    # Generate new subcategory topics from category names
    for cat_name in ["science", "technology", "history", "arts", "health",
                      "nature", "geography", "daily_life", "philosophy",
                      "business", "education", "law", "politics", "economics",
                      "psychology", "sociology", "anthropology"]:
        cat_dir = KNOWLEDGE_DIR / cat_name
        if cat_dir.exists():
            # Category exists — look for thin subcategories
            sub_dirs = [d for d in cat_dir.iterdir() if d.is_dir()]
            for sub_dir in sub_dirs:
                sub_name = sub_dir.name
                if (cat_name, sub_name) not in existing_cats:
                    # This subcategory exists as a directory but has no tracking
                    files = list(sub_dir.glob("*.json"))
                    if files:
                        # Use an existing file's topic
                        for f in files[:3]:
                            topic_guess = f.stem.split("_")[0]
                            if topic_guess and len(topic_guess) > 3:
                                key = _get_topic_key(cat_name, sub_name, topic_guess)
                                if key not in tracking["topics"]:
                                    candidates.append((cat_name, sub_name, topic_guess, 0))

    # Strategy 4: Cross-pollinate — generate topics at the intersection
    # of two existing categories
    if len(candidates) < 5:
        topic_list = list(tracking["topics"].keys())
        if len(topic_list) >= 4:
            for _ in range(3):
                t1 = random.choice(topic_list)
                t2 = random.choice(topic_list)
                p1 = t1.split(".")
                p2 = t2.split(".")
                if len(p1) == 3 and len(p2) == 3:
                    # Create a merged topic from two different categories
                    merged = f"{p1[2]} and {p2[2]}"
                    cross_cat = "general"
                    cross_sub = "cross_domain"
                    cross_key = _get_topic_key(cross_cat, cross_sub, merged)
                    if cross_key not in tracking["topics"]:
                        candidates.append((cross_cat, cross_sub, merged, 1))

    # Remove duplicates, prioritize shallow depth
    seen = set()
    unique = []
    for cat, subcat, topic, depth in candidates:
        key = _get_topic_key(cat, subcat, topic)
        if key not in seen:
            seen.add(key)
            unique.append((cat, subcat, topic, depth))

    # Sort: depth first (0 first), then by category
    unique.sort(key=lambda x: (x[3], x[0], x[1]))

    return unique[:10]


def _get_coverage_report():
    """Generate a dynamic coverage report based on actual tree growth."""
    tracking = _load_tracking()
    topics = tracking.get("topics", {})
    categories = tracking.get("categories", {})

    # Count actual files
    actual_files = list(KNOWLEDGE_DIR.rglob('*.json'))
    actual_count = sum(1 for p in actual_files if not p.name.startswith('.'))

    total_entries = tracking.get("total_generated", 0)
    total_topics = len(topics)
    total_cats = len(categories)

    # Compute depth stats
    depths = [info.get("depth", 0) for info in topics.values()]
    max_depth = max(depths) if depths else 0
    avg_depth = sum(depths) / len(depths) if depths else 0

    # Compute files per category
    cat_file_counts = defaultdict(int)
    for path in actual_files:
        rel = path.relative_to(KNOWLEDGE_DIR)
        cat = rel.parts[0] if len(rel.parts) > 0 else "other"
        cat_file_counts[cat] += 1

    report = f"\n{'='*60}\n"
    report += "  COVERAGE REPORT — Infinite Knowledge Tree\n"
    report += f"{'='*60}\n"
    report += f"  Total entries:  {total_entries}\n"
    report += f"  Total files:    {actual_count}\n"
    report += f"  Topics covered: {total_topics}\n"
    report += f"  Categories:     {total_cats}\n"
    report += f"  Tree depth:     avg={avg_depth:.1f} max={max_depth}\n\n"

    # Show top categories by file count
    report += "  Categories by file count:\n"
    for cat_name in sorted(cat_file_counts.keys(), key=lambda c: cat_file_counts[c], reverse=True):
        count = cat_file_counts[cat_name]
        bar_len = min(count, 30)
        bar = '█' * bar_len
        pct = count / max(actual_count, 1) * 100
        report += f"    {cat_name:15s} {count:3d} files {bar} {pct:.0f}%\n"

    # Show deepest topics
    if depths:
        deepest = sorted(topics.items(), key=lambda x: x[1].get("depth", 0), reverse=True)[:5]
        report += f"\n  Deepest branches:\n"
        for key, info in deepest:
            if info.get("depth", 0) >= 2:
                report += f"    {'→'.join(key.split('.')):40s} depth={info['depth']} entries={info['count']}\n"

    report += f"\n  {'='*60}"
    return report


def run_continuous(backend="template", ollama_model="llama3.2", count_per_topic=5,
                   interval=10, max_iterations=None):
    """Run the knowledge generator indefinitely, growing the topic tree.

    Each iteration:
    1. Discover new branches (sub-topics, cross-domain topics)
    2. Pick the best next topic to generate
    3. Generate entries
    4. Update the tree
    5. Report coverage periodically
    """
    # Ensure seeds exist
    tracking = _load_tracking()
    _ensure_seed_topics(tracking)

    print(f"\n{'='*60}")
    print(f"  COS Infinite Knowledge Generator")
    print(f"  Backend: {backend}")
    print(f"  Interval: {interval}s per topic")
    print(f"  Output: {KNOWLEDGE_DIR}")
    print(f"{'='*60}\n")

    iteration = 0
    while max_iterations is None or iteration < max_iterations:
        iteration += 1
        print(f"\n{'─'*60}")
        print(f"  Iteration {iteration}")
        print(f"{'─'*60}")

        tracking = _load_tracking()

        # Step 1: Discover new branches
        candidates = _discover_new_branches(tracking, count=3)

        if not candidates:
            print("  No new topics to discover — waiting for branching conditions...")
        else:
            # Step 2: Pick the best candidate (shallowest depth first)
            cat, subcat, topic, depth = candidates[0]
            print(f"  Selected: '{topic}' ({cat}/{subcat}) depth={depth}")
            print(f"  Queue: {len(candidates)} candidates available")

            # Step 3: Generate
            before = tracking.get("total_generated", 0)
            generate_knowledge(
                topic=topic,
                category=cat,
                subcategory=subcat,
                count=count_per_topic,
                backend=backend,
                ollama_model=ollama_model,
                depth=depth,
            )
            after = _load_tracking().get("total_generated", 0)
            added = after - before

            # Step 4: Show growth
            print(f"  Total generated: {after} (+{added})")

        # Show coverage periodically
        if iteration % 5 == 0:
            print(_get_coverage_report())

        # Wait
        if max_iterations is None or iteration < max_iterations:
            print(f"\n  Waiting {interval}s...")
            time.sleep(interval)


# ═════════════════════════════════════════════════════════════════════════════
# TEMPLATE GENERATION
# ═════════════════════════════════════════════════════════════════════════════

def _generate_templates_template(template_type, count=5):
    """Generate template entries using built-in templates (no LLM)."""
    entries = []
    question_templates = [
        (f"tell me about {{topic}}",
         f"I'd be happy to share what I know about {{context}}! Let me give you a comprehensive overview covering the key aspects, interesting details, and practical implications."),
        (f"explain {{topic}} to me",
         f"Great question about {{context}}! Let me break it down in a way that's easy to understand, starting with the fundamentals and building up to the more interesting details."),
        (f"what is {{topic}}",
         f"{{context}} is a fascinating subject that encompasses several key ideas and principles. Let me explain what it is and why it matters."),
        (f"give me an overview of {{topic}}",
         f"Here's a concise overview of {{context}}: It covers important concepts that have practical applications and interesting implications across multiple areas."),
        (f"teach me {{topic}}",
         f"I'd be happy to teach you about {{context}}! Let's start with the basics and work our way up."),
        (f"I want to learn about {{topic}}",
         f"Excellent choice! {{context}} is a rewarding subject to explore. Let me guide you through the fundamental concepts and help you build a solid understanding."),
        (f"can you help me with {{topic}}",
         f"Of course! I'd be glad to help you with {{context}}. Let me start by understanding what you already know, and then we can build from there."),
        (f"what do you know about {{topic}}",
         f"I know quite a bit about {{context}}! Here are some of the key things you should know, starting with the fundamentals and moving to more advanced concepts."),
    ]
    for i in range(min(count, len(question_templates))):
        trigger_text, template_text = question_templates[i]
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


def _generate_templates_with_llm(template_type, count=5, backend="ollama", model="llama3.2"):
    """Generate template entries using an LLM."""
    system_prompt = """You are a conversational template generator for an AI assistant.

Each template entry must be in this JSON format:
[
  {
    "id": "category-type-001",
    "triggers": ["trigger phrase 1", "trigger phrase 2"],
    "context_role": "topic",
    "template": "Response with {context} placeholder",
    "fallback": "Response when no context",
    "style": ["conversational"],
    "response_length": "medium"
  }
]"""

    prompt = f"""{system_prompt}

Generate {count} diverse conversational template entries about "{template_type}".
Each should be a complete, ready-to-use response template.

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
        triggers = entry.get("triggers", [])
        template = entry.get("template", "")
        if isinstance(triggers, str):
            triggers = [triggers]
        if triggers and template:
            if "id" not in entry:
                entry["id"] = f"gen-{random.randint(1000,9999)}"
            if "fallback" not in entry:
                entry["fallback"] = f"I'd be happy to help with that!"
            if "context_role" not in entry:
                entry["context_role"] = "topic"
            validated.append(entry)

    if not validated:
        return None

    print(f"  Generated {len(validated)} template entries via {backend}")
    return validated


def _generate_template_types(template_type, count=3):
    """Generate sub-types for a template type to create branches."""
    subtypes = []
    for group, templates in SUBTOPIC_TEMPLATES.items():
        for tmpl in templates:
            sub = tmpl.format(topic=template_type)
            subtypes.append(sub[0].upper() + sub[1:])
    # Also generate action-oriented subtypes
    action_prefixes = [
        f"how to {template_type}",
        f"best practices for {template_type}",
        f"guide to {template_type}",
        f"tips for {template_type}",
        f"examples of {template_type}",
        f"common mistakes in {template_type}",
        f"advanced {template_type}",
        f"getting started with {template_type}",
        f"tools for {template_type}",
        f"resources for {template_type}",
    ]
    subtypes.extend(action_prefixes)

    # De-duplicate
    seen = set()
    unique = []
    for s in subtypes:
        sl = s.lower().strip()
        if sl not in seen and sl != template_type.lower():
            seen.add(sl)
            unique.append(s)
    return unique[:count * 3]


def generate_templates(template_type, category=None, subcategory=None, count=5,
                       backend="template", ollama_model="llama3.2", force=False,
                       depth=0):
    """Generate conversation template entries with auto-splitting."""
    template_tracking_file = ROOT / 'data' / '.template_tracking.json'

    # Load tracking
    tracking = {"templates": {}, "total_generated": 0, "categories": {}}
    if template_tracking_file.exists():
        try:
            tracking = json.loads(template_tracking_file.read_text())
        except Exception:
            pass
    if "categories" not in tracking:
        tracking["categories"] = {}

    # Auto-categorize
    if not category:
        for key in tracking.get("templates", {}):
            parts = key.split(".")
            if len(parts) >= 3 and parts[2].lower() == template_type.lower():
                category = parts[0]
                subcategory = parts[1]
                break
        if not category:
            category = "conversation"
            subcategory = "followups"

    if not subcategory:
        subcategory = "general"

    print(f"\n  Generating template '{template_type}' ({category}/{subcategory}) [depth={depth}]...")

    # Load existing triggers for dedup
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
        except Exception:
            pass

    # Generate entries
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
    type_dir = TEMPLATE_DIR / category
    type_dir.mkdir(parents=True, exist_ok=True)

    base_name = re.sub(r'[^a-z0-9]+', '_', template_type.lower()).strip('_')[:40]
    file_path = type_dir / f"{base_name}.json"

    # Check if we need to split
    if file_path.exists():
        try:
            existing_data = json.loads(file_path.read_text())
            if isinstance(existing_data, list) and len(existing_data) + len(filtered) > MAX_ENTRIES_PER_FILE:
                # Find the next available part number
                part = 1
                while (type_dir / f"{base_name}{part}.json").exists():
                    part += 1
                file_path = type_dir / f"{base_name}{part}.json"
        except Exception:
            pass

    # Write (merge with existing)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    existing_data = []
    if file_path.exists():
        try:
            existing_data = json.loads(file_path.read_text())
            if not isinstance(existing_data, list):
                existing_data = []
        except Exception:
            existing_data = []

    new_ids = {e.get('id', '') for e in filtered}
    filtered_existing = [e for e in existing_data if e.get('id', '') not in new_ids]
    merged = filtered + filtered_existing

    with open(file_path, 'w') as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
        f.write('\n')

    # Update tracking
    key = f"{category}.{subcategory}.{template_type}"
    if key not in tracking["templates"]:
        tracking["templates"][key] = {"count": 0, "category": category, "depth": depth}
    tracking["templates"][key]["count"] += len(filtered)
    tracking["total_generated"] += len(filtered)
    template_tracking_file.write_text(json.dumps(tracking, indent=2))

    file_ref = file_path.relative_to(ROOT)
    print(f"  ✓ Wrote {len(filtered)} template entries to {file_ref}")
    return len(filtered)


def _discover_new_template_types(tracking, count=5):
    """Discover new template types to generate."""
    candidates = []

    # Strategy 1: Seed types not yet covered
    for cat, subcat, ttype in SEED_TEMPLATE_TYPES:
        key = f"{cat}.{subcat}.{ttype}"
        info = tracking.get("templates", {}).get(key, {})
        if info.get("count", 0) == 0:
            candidates.append((cat, subcat, ttype, 0))

    # Strategy 2: Branch existing types
    for key, info in tracking.get("templates", {}).items():
        parts = key.split(".")
        if len(parts) >= 3:
            cat, subcat, ttype = parts[0], parts[1], parts[2]
            depth = info.get("depth", 0)
            if info.get("count", 0) >= MIN_ENTRIES_FOR_BRANCH and depth < MAX_TOPIC_DEPTH:
                subtypes = _generate_template_types(ttype, count=3)
                for st in subtypes:
                    skey = f"{cat}.{subcat}.{st}"
                    if skey not in tracking.get("templates", {}):
                        candidates.append((cat, subcat, st, depth + 1))

    seen = set()
    unique = []
    for cat, subcat, ttype, depth in candidates:
        key = f"{cat}.{subcat}.{ttype}"
        if key not in seen:
            seen.add(key)
            unique.append((cat, subcat, ttype, depth))

    unique.sort(key=lambda x: (x[3], x[0]))
    return unique[:10]


def run_template_continuous(backend="template", ollama_model="llama3.2",
                            count_per_type=5, interval=10, max_iterations=None):
    """Run the template generator indefinitely."""
    template_tracking_file = ROOT / 'data' / '.template_tracking.json'

    print(f"\n{'='*60}")
    print(f"  COS Infinite Template Generator")
    print(f"  Backend: {backend}")
    print(f"  Interval: {interval}s per type")
    print(f"  Output: {TEMPLATE_DIR}")
    print(f"{'='*60}\n")

    iteration = 0
    while max_iterations is None or iteration < max_iterations:
        iteration += 1
        print(f"\n{'─'*60}")
        print(f"  Template Iteration {iteration}")
        print(f"{'─'*60}")

        # Load tracking
        tracking = {"templates": {}, "total_generated": 0}
        if template_tracking_file.exists():
            try:
                tracking = json.loads(template_tracking_file.read_text())
            except Exception:
                pass

        # Discover
        candidates = _discover_new_template_types(tracking, count=3)

        if not candidates:
            print("  No new template types — waiting...")
        else:
            cat, subcat, ttype, depth = candidates[0]
            print(f"  Selected: '{ttype}' ({cat}/{subcat}) depth={depth}")
            print(f"  Queue: {len(candidates)} candidates")

            before = tracking.get("total_generated", 0)
            generate_templates(
                template_type=ttype,
                category=cat,
                subcategory=subcat,
                count=count_per_type,
                backend=backend,
                ollama_model=ollama_model,
                depth=depth,
            )
            after = 0
            if template_tracking_file.exists():
                try:
                    after = json.loads(template_tracking_file.read_text()).get("total_generated", 0)
                except Exception:
                    pass
            added = after - before
            print(f"  Total generated: {after} (+{added})")

        if max_iterations is None or iteration < max_iterations:
            print(f"\n  Waiting {interval}s...")
            time.sleep(interval)


# ═════════════════════════════════════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="COS Infinite Knowledge & Template Generator")
    parser.add_argument("--topic", help="Specific topic to generate about")
    parser.add_argument("--type", choices=["knowledge", "template"],
                       default="knowledge", help="Type of content to generate")
    parser.add_argument("--category", help="Category")
    parser.add_argument("--subcategory", help="Subcategory")
    parser.add_argument("--count", type=int, default=5, help="Entries per topic")
    parser.add_argument("--backend", choices=["ollama", "openai", "template"],
                       default="template", help="Generation backend")
    parser.add_argument("--model", default="llama3.2", help="Ollama model name")
    parser.add_argument("--mode", choices=["once", "continuous"],
                       default="once", help="Run mode")
    parser.add_argument("--interval", type=int, default=3,
                       help="Seconds between generations (continuous mode)")
    parser.add_argument("--iterations", type=int, default=None,
                       help="Max iterations (continuous mode)")
    parser.add_argument("--force", action="store_true",
                       help="Skip duplicate check")
    parser.add_argument("--coverage", action="store_true",
                       help="Show coverage report and exit")

    args = parser.parse_args()

    output_dir = TEMPLATE_DIR if args.type == "template" else KNOWLEDGE_DIR
    output_name = "template" if args.type == "template" else "knowledge"

    print(f"\n╔{'═'*58}╗")
    print(f"║  COS Infinite {output_name.upper()} Generator{' '*(35-len(output_name))}║")
    print(f"║  Output: {str(output_dir):>44s} ║")
    print(f"║  Mode: {'∞ continuous' if args.mode == 'continuous' else 'single':>44s} ║")
    print(f"╚{'═'*58}╝")

    if args.coverage:
        if args.type == "template":
            print("\nTemplate coverage tracking is file-based.")
            total = sum(1 for _ in TEMPLATE_DIR.rglob('*.json') if not _.name.startswith('.'))
            print(f"  Template files: {total}")
        else:
            print(_get_coverage_report())
        return

    # Backend check
    if args.backend in ("ollama", "openai"):
        if args.backend == "ollama":
            try:
                test = _call_ollama("Say OK", model=args.model)
                if test:
                    print(f"  ✓ Ollama available ({args.model})")
                else:
                    print("  ⚠ Ollama not responding, using template backend")
                    args.backend = "template"
            except Exception:
                print("  ⚠ Ollama not available, using template backend")
                args.backend = "template"
        elif args.backend == "openai":
            if os.environ.get("OPENAI_API_KEY"):
                print("  ✓ OpenAI API key found")
            else:
                print("  ⚠ OPENAI_API_KEY not set, using template backend")
                args.backend = "template"

    if args.backend == "template":
        print("  ℹ Template-based generation (no LLM needed)")

    # Ensure seed topics exist for knowledge generation
    if args.type == "knowledge":
        tracking = _load_tracking()
        _ensure_seed_topics(tracking)

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
            tracking = {"templates": {}, "total_generated": 0}
            tt = ROOT / 'data' / '.template_tracking.json'
            if tt.exists():
                try:
                    tracking = json.loads(tt.read_text())
                except Exception:
                    pass
            candidates = _discover_new_template_types(tracking, count=1)
            if candidates:
                cat, subcat, ttype, depth = candidates[0]
                generate_templates(
                    template_type=ttype,
                    category=cat,
                    subcategory=subcat,
                    count=args.count,
                    backend=args.backend,
                    ollama_model=args.model,
                    force=args.force,
                    depth=depth,
                )
    else:
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
            tracking = _load_tracking()
            _ensure_seed_topics(tracking)
            candidates = _discover_new_branches(tracking, count=1)
            if candidates:
                cat, subcat, topic, depth = candidates[0]
                generate_knowledge(
                    topic=topic,
                    category=cat,
                    subcategory=subcat,
                    count=args.count,
                    backend=args.backend,
                    ollama_model=args.model,
                    force=args.force,
                    depth=depth,
                )

    if args.type != "template" and args.mode != "continuous":
        print(_get_coverage_report())


if __name__ == '__main__':
    main()
