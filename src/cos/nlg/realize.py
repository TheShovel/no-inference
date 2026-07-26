"""NLG Sentence Realization — generate syntactic variants per fact type.

Provides pattern-based sentence generation for typed facts. Each fact type
has multiple surface realizations depending on style and context.
"""

import re
from typing import List, Optional
from .models import Fact, DiscourseState
from .config import NLGConfig
from .util import pick, maybe, lower_first, upper_first, require_style


# ── Sentence patterns per fact type per style ──────────────────────────────

_PATTERNS = {
    "definition": {
        "friendly": [
            "{subject} {verb} {obj}.",
            "{subject} {verb} {obj}.",
            "{subject} {verb} {obj}.",
            "In essence, {subject} {verb} {obj}.",
            "Simply put, {subject} {verb} {obj}.",
        ],
        "neutral": [
            "{subject} {verb} {obj}.",
            "{subject} {verb} {obj}.",
            "{subject} refers to {obj}.",
        ],
        "concise": [
            "{subject}: {obj}.",
        ],
    },
    "location": {
        "friendly": [
            "You can find it {prep} {place}.",
            "It's located {prep} {place}.",
            "It sits {prep} {place}.",
        ],
        "neutral": [
            "{subject} is located {prep} {place}.",
            "{subject} is found {prep} {place}.",
        ],
        "concise": [
            "{prep} {place}.",
        ],
    },
    "property": {
        "friendly": [
            "{subject} has {obj}.",
            "{subject} includes {obj}.",
            "{subject} is known for {obj}.",
        ],
        "neutral": [
            "{subject} has {obj}.",
            "{subject} includes {obj}.",
        ],
        "concise": [
            "Has {obj}.",
        ],
    },
    "composition": {
        "friendly": [
            "It's made from {obj}.",
            "It's made up of {obj}.",
            "It consists of {obj}.",
        ],
        "neutral": [
            "It's made of {obj}.",
            "{subject} consists of {obj}.",
        ],
        "concise": [
            "Made of {obj}.",
        ],
    },
    "purpose": {
        "friendly": [
            "It's used for {obj}.",
            "People use it to {obj}.",
            "It serves as {obj}.",
        ],
        "neutral": [
            "It's used for {obj}.",
            "{subject} serves as {obj}.",
        ],
        "concise": [
            "Used {obj}.",
        ],
    },
    "action": {
        "friendly": [
            "{subject} {verb} {obj}.",
            "{subject} {verb} {obj}.",
        ],
        "neutral": [
            "{subject} {verb} {obj}.",
        ],
        "concise": [
            "{verb} {obj}.",
        ],
    },
    "comparison": {
        "friendly": [
            "It's like {obj}.",
            "Think of it as {obj}.",
            "You could compare it to {obj}.",
        ],
        "neutral": [
            "It is similar to {obj}.",
        ],
        "concise": [
            "Like {obj}.",
        ],
    },
    "unknown": {
        "friendly": ["{obj}.", "{obj_lower}."],
        "neutral": ["{obj}."],
        "concise": ["{obj}."],
    },
}


def realize_fact(
    fact: Fact,
    config: NLGConfig,
    state: Optional[DiscourseState] = None,
    use_pronoun: bool = True,
) -> str:
    """Generate a natural sentence from a Fact.

    Pure function.
    """
    if fact.fact_type == "unknown" or not fact.predicate:
        res = fact.obj.strip()
        if not res.endswith(('.', '!', '?')):
            res += "."
        return upper_first(res)

    style = require_style(config)
    templates = _PATTERNS.get(fact.fact_type)
    if not templates:
        templates = _PATTERNS["unknown"]
    style_templates = list(templates.get(style, templates.get("neutral", [])))

    # ── Ensure "refers to" is only used for true definition predicates ──
    copular = fact.predicate.strip().lower() in ("is", "are", "was", "were")
    obj = fact.obj
    if not copular:
        style_templates = [t for t in style_templates if "refers to" not in t]
        if not style_templates:
            style_templates = ["{subject} {verb} {obj}."]
    # Also filter "refers to" when the object doesn't look like a simple definition
    # (e.g., "often called the Red Planet" should not become "refers to often called...")
    _obj_lower = obj.lower().strip()
    if copular and style_templates:
        _REFERS_TO_SKIP_PATTERNS = (
            'often called', 'sometimes called', 'also called', 'known as',
            'called ', 'referred to as', 'known for', 'famous for',
            'because of', 'due to', 'as a', 'in a', 'on a',
        )
        if any(_obj_lower.startswith(p) for p in _REFERS_TO_SKIP_PATTERNS):
            style_templates = [t for t in style_templates if "refers to" not in t]
            if not style_templates:
                style_templates = ["{subject} {verb} {obj}."]

    # For negated facts, avoid templates that drop negation (e.g., "known for"
    # would turn "has no magnetic field" into "is known for no magnetic field")
    if fact.is_negated:
        style_templates = [t for t in style_templates if "known for" not in t]
        if not style_templates:
            style_templates = ["{subject} {verb} {obj}."]

    template = pick(style_templates, config.temperature)

    subject = fact.subject
    obj_lower = lower_first(obj)

    # Fix: if subject is just an adjective (no noun), use the fact's original subject or topic
    _ADJECTIVES_ONLY = {
        'high-quality', 'low-quality', 'good-quality', 'bad-quality',
        'large-scale', 'small-scale', 'long-term', 'short-term',
        'well-known', 'little-known', 'well-known', 'far-reaching',
    }
    if subject.lower().rstrip('.,;:!?') in _ADJECTIVES_ONLY:
        # Try to extract a better subject from the original sentence
        if fact.original:
            # Look for "X have/has/are" pattern in original
            orig_match = re.match(r'^([A-Z][^.]*?)\s+(?:have|has|are|is|were|was)\b', fact.original)
            if orig_match:
                subject = orig_match.group(1).strip()
        # If still just an adjective, use a generic subject based on the topic
        if subject.lower().rstrip('.,;:!?') in _ADJECTIVES_ONLY:
            subject = "This"  # Fallback to generic subject

    # Escape any literal braces in obj to prevent format() crashes
    obj_safe = obj.replace("{", "{{").replace("}", "}}")
    obj_lower_safe = obj_lower.replace("{", "{{").replace("}", "}}")
    
    # ── Determine correct pronoun for subject from discourse state ──
    subject_pronoun = "it"
    subject_objective = "it"
    subject_possessive = "its"
    if state and use_pronoun:
        entity = state.get_entity(subject)
        if entity:
            subject_pronoun = entity.pronoun
            subject_objective = entity.objective_pronoun
            subject_possessive = entity.possessive_pronoun

    # ── Determine if subject is plural for verb agreement ──
    subj_lower = subject.strip().lower()
    non_plural_s = {
        "this", "thus", "bus", "gas", "was", "its", "paris", "mars", "venus", "uranus",
        "athens", "brussels", "dallas", "texas", "kansas", "photosynthesis", "physics",
        "mathematics", "cosmos", "series", "species", "apparatus", "corpus"
    }
    # Compound subjects are always plural
    _COMPOUND_SUBJECTS = ('both', 'all', 'some', 'many', 'several', 'each', 'every')
    is_compound_subject = any(subj_lower.startswith(p) for p in _COMPOUND_SUBJECTS)
    is_plural_subject = (
        is_compound_subject
        or (subj_lower.endswith("s") and not subj_lower.endswith("ss") and subj_lower not in non_plural_s)
        or " and " in subj_lower or " & " in subj_lower
    )

    # Fix verb agreement (is -> are, was -> were, has -> have, includes -> include) if subject is plural
    verb = fact.predicate

    # ── For property/action facts: use actual predicate when it's a specific transitive verb ──
    # This preserves "Benefits include..." while still letting "Paris has..." use the template.
    _SPECIFIC_TRANSITIVE_VERBS = {
        "include", "contain", "comprise", "feature", "require",
        "support", "involve", "use", "produce", "generate",
        "enable", "allow", "prevent", "protect", "destroy",
        "connect", "combine", "convert", "represent", "describe",
        "cover", "span", "offer", "provide", "occur", "appear",
        "function", "operate", "perform", "serve", "act",
    }
    actual_verb_lower = fact.predicate.strip().lower()

    # Fix: if predicate is "include" but object starts with "been", use "have" instead
    # (e.g., "Carrot seeds include been found" -> "Carrot seeds have been found")
    _fixed_include_been = False
    if actual_verb_lower == "include" and obj_lower.startswith("been"):
        verb = "have" if is_plural_subject else "has"
        actual_verb_lower = verb.lower()
        template = "{subject} {verb} {obj}."
        _fixed_include_been = True

    if fact.fact_type in ("property", "action") and (
        actual_verb_lower in _SPECIFIC_TRANSITIVE_VERBS
        or actual_verb_lower in ("are", "were")  # copular plural predicate — use direct SVO
    ):
        # Use a direct subject-verb-object pattern to honour the actual verb
        template = "{subject} {verb} {obj}."
        # Also mark so "known for" skip filters don't override this SVO template
        if actual_verb_lower in ("are", "were"):
            _fixed_include_been = True

    if is_plural_subject:
        if verb in ("is", "are"):
            verb = "are"
        elif verb in ("was", "were"):
            verb = "were"
        elif verb in ("has", "have"):
            verb = "have"
        elif verb in ("includes", "include"):
            verb = "include"
        elif verb in ("contains", "contain"):
            verb = "contain"
        elif verb in ("features", "feature"):
            verb = "feature"

    # For property facts with "has" predicate, avoid "known for" templates
    # when the object is a measurement or concrete thing (not an abstract quality)
    # Skip if we already fixed "include been" to use SVO pattern
    if not _fixed_include_been and fact.fact_type == "property" and actual_verb_lower == "has":
        _KNOWN_FOR_SKIP = (
            'a diameter', 'a population', 'a mass', 'a height', 'a width',
            'a length', 'a weight', 'a temperature', 'a speed', 'a distance',
            'a year', 'a day', 'an atmosphere', 'the tallest', 'the largest',
            'the smallest', 'two small', 'no global', 'a large proportion',
            'a small proportion', 'a significant', 'a substantial',
        )
        if any(_obj_lower.startswith(p) for p in _KNOWN_FOR_SKIP):
            _filtered = [t for t in style_templates if "known for" not in t]
            if _filtered:
                style_templates = _filtered
                template = pick(style_templates, config.temperature)

    # Also skip "known for" when the subject looks like a compound subject
    # (e.g., "Both X and Y" or "X, Y, and Z") - these need plural verbs
    _COMPOUND_SUBJECTS = ('both', 'all', 'some', 'many', 'several', 'each', 'every')
    if not _fixed_include_been and subj_lower.startswith(_COMPOUND_SUBJECTS):
        _filtered = [t for t in style_templates if "known for" not in t]
        if _filtered:
            style_templates = _filtered
            template = pick(style_templates, config.temperature)

    # Also skip "known for" when the subject has an adjective prefix
    # (e.g., "High-quality carrots" -> should use "has" not "is known for")
    _ADJECTIVE_PREFIXES = ('high-', 'low-', 'good-', 'bad-', 'large-', 'small-', 'big-')
    if not _fixed_include_been and any(subj_lower.startswith(p) for p in _ADJECTIVE_PREFIXES):
        _filtered = [t for t in style_templates if "known for" not in t]
        if _filtered:
            style_templates = _filtered
            template = pick(style_templates, config.temperature)

    # Also skip "known for" when the object contains "been" or "have been"
    # (e.g., "seeds have been found" should not become "seeds is known for been found")
    if not _fixed_include_been and ('been' in _obj_lower or 'have been' in _obj_lower):
        _filtered = [t for t in style_templates if "known for" not in t]
        if _filtered:
            style_templates = _filtered
            template = pick(style_templates, config.temperature)

    # For singular subjects, normalise template "includes" -> "has" so we don't get
    # "Paris includes a population" when the predicate is 'has'
    if not is_plural_subject and actual_verb_lower == "has":
        template = template.replace("{subject} includes ", "{subject} has ")

    # Replace third person singular verb in template if subject is plural
    if is_plural_subject:
        template = template.replace("{subject} includes ", "{subject} include ")
        template = template.replace("{subject} has ", "{subject} have ")
        template = template.replace("{subject} contains ", "{subject} contain ")

    # ── Resolve "refers to"/"refer to" based on subject number ──
    if "refers to" in template and is_plural_subject:
        template = template.replace("refers to", "refer to")

    # Replace hardcoded "It's"/"It " patterns with correct pronoun
    template = template.replace("It's ", subject_pronoun + "'s ")
    template = template.replace("It ", subject_pronoun + " ")

    # If the subject starts with a capitalized word and the template starts
    # with a prefix like "You could say", lowercase the subject's first word
    # for natural flow: "You could say the Eiffel Tower" not "You could say The Eiffel Tower"
    _PROPER_NOUNS_REALIZE = {
        'albert', 'einstein', 'curie', 'eiffel', 'mars', 'earth', 'jupiter',
        'saturn', 'venus', 'uranus', 'neptune', 'mercury', 'france', 'paris',
        'london', 'germany', 'vienna', 'bonn', 'austria', 'beethoven',
        'olympus', 'phobos', 'deimos', 'brain', 'neural', 'chemistry',
        'physics', 'biology', 'mathematics', 'calculus', 'algebra',
        'relativity', 'darwin', 'newton', 'galileo', 'tesla',
        'hawking', 'feynman', 'copernicus', 'kepler', 'shakespeare',
        'homer', 'plato', 'aristotle', 'confucius', 'buddha',
    }
    _PREFIXES = (
        "You could say ", "Well, ", "Actually, ", "So, ",
        "What's more, ", "Beyond that, ", "On top of that, ",
        "Also, ", "Notably, ", "Interestingly, ",
    )
    for prefix in _PREFIXES:
        if template.startswith(prefix + "{subject}"):
            # Lowercase the first letter of the subject for natural flow:
            # "You could say the Eiffel Tower" not "You could say The Eiffel Tower"
            # "You could say machine learning" not "You could say Machine learning"
            # "You could say he developed" not "You could say He developed"
            # But keep proper nouns capitalized: "You could say Albert Einstein"
            _subj_words = subject.split()
            if _subj_words:
                _first_word_lower = _subj_words[0].lower()
                if _first_word_lower in ("the", "a", "an"):
                    # Article: always lowercase
                    template = template.replace(prefix + "{subject}", prefix + lower_first(subject), 1)
                elif _first_word_lower in ("he", "she", "it", "they", "we", "you"):
                    # Pronouns: always lowercase after a prefix
                    template = template.replace(prefix + "{subject}", prefix + _first_word_lower, 1)
                elif _first_word_lower in _PROPER_NOUNS_REALIZE:
                    # Known proper noun: keep capitalized
                    pass
                elif _subj_words[0][0].isupper() and len(_subj_words) > 1:
                    # Multi-word subject where first word might be common noun
                    # (e.g., "Machine learning", "French fries") -> lowercase first word
                    template = template.replace(prefix + "{subject}", prefix + lower_first(subject), 1)
                elif _subj_words[0][0].isupper() and len(_subj_words) == 1:
                    # Single word subject: lowercase unless it's a known proper noun
                    # (e.g., "Photosynthesis" -> "photosynthesis", "Sunlight" -> "sunlight")
                    # but "Mars" -> "Mars", "Einstein" -> "Einstein"
                    template = template.replace(prefix + "{subject}", prefix + _first_word_lower, 1)
            break

    # Try to build the sentence from the template
    try:
        if fact.fact_type == "location":
            # Parse location
            loc_match = re.match(
                r'(?:located|situated|found|based)\s+(in|on|at|near)\s+(.+)',
                obj, re.IGNORECASE
            )
            if not loc_match:
                loc_match = re.match(r'(in|on|at|near)\s+(.+)', obj, re.IGNORECASE)
            if loc_match:
                prep = loc_match.group(1)
                place = loc_match.group(2).replace("{", "{{").replace("}", "}}")
            else:
                prep = "in"
                place = obj_safe
            sentence = template.format(subject=subject, verb=verb, subject_lower=lower_first(subject),
                                       obj=obj_safe, obj_pro=lower_first(obj_safe),
                                       prep=prep, place=place)
        elif fact.fact_type == "composition":
            comp_match = re.match(r'(?:made|composed|consisting)\s+(?:of|from|with|using)\s+(.+)', obj, re.IGNORECASE)
            clean_obj = comp_match.group(1) if comp_match else obj
            clean_obj_safe = clean_obj.replace("{", "{{").replace("}", "}}")
            sentence = template.format(subject=subject, verb=verb, subject_lower=lower_first(subject),
                                       obj=lower_first(clean_obj_safe), obj_pro=lower_first(clean_obj_safe))
        else:
            sentence = template.format(subject=subject, verb=verb, subject_lower=lower_first(subject),
                                       obj=obj_safe, obj_pro=obj_lower_safe, obj_lower=obj_lower_safe,
                                       place=obj_safe)
    except (KeyError, ValueError):
        # Fallback: simple subject-verb-object or object
        if not verb or fact.fact_type == "unknown":
            sentence = obj
        else:
            sentence = f"{subject} {verb} {obj}."

    # Capitalize and ensure ending punctuation
    sentence = upper_first(sentence.strip())
    if not sentence.endswith(('.', '!', '?')):
        sentence += "."

    # Fix duplication: "Eiffel Tower is The Eiffel Tower is..." -> "Eiffel Tower is..."
    if verb:
        dup_match = re.match(
            r'(' + re.escape(subject) + r'\s+' + re.escape(verb) + r'\s+)The\s+' + re.escape(subject) + r'\s+',
            sentence, re.IGNORECASE
        )
        if dup_match:
            sentence = sentence[:dup_match.end(1)] + sentence[dup_match.end():]
            sentence = upper_first(sentence.strip())

    return sentence


# ── Opening generation ─────────────────────────────────────────────────────

_OPENINGS = {
    "how": {
        "friendly": ["", "", ""],
        "neutral": [""],
        "concise": [""],
    },
    "who": {
        "friendly": ["", ""],
        "neutral": [""],
        "concise": [""],
    },
    "explain": {
        "friendly": ["", ""],
        "neutral": [""],
        "concise": [""],
    },
    "define": {
        "friendly": ["", ""],
        "neutral": [""],
        "concise": [""],
    },
    "where": {
        "friendly": ["", ""],
        "neutral": [""],
        "concise": [""],
    },
    "factual": {
        "friendly": ["", ""],
        "neutral": [""],
        "concise": [""],
    },
}


def classify_query(query: str) -> str:
    """Classify query into a communicative type."""
    q = query.lower().strip()
    if any(p in q for p in ['how do i', 'how can i', 'how to', 'how would i']):
        return 'how'
    if any(p in q for p in ['who is', 'who was', 'who are', 'who were']):
        return 'who'
    if any(p in q for p in ['define', 'what is the definition', 'what does', 'mean']):
        return 'define'
    if any(p in q for p in ['explain', 'describe', 'tell me about', 'what is', "what's", 'what are']):
        return 'explain'
    if any(p in q for p in ['where is', 'where are', 'where was', 'where can']):
        return 'where'
    return 'factual'


def get_opening(query: str, config: NLGConfig) -> str:
    """Get an intent-aware opening phrase."""
    qtype = classify_query(query)
    style = require_style(config)
    pool = _OPENINGS.get(qtype, _OPENINGS['factual']).get(style, _OPENINGS['factual']['neutral'])
    return pick(pool, config.temperature)


# ── Closings ───────────────────────────────────────────────────────────────

_CLOSINGS = {
    "friendly": [
        "",
        "",
    ],
    "neutral": [
        "",
        "",
    ],
    "concise": [],
}


def get_closing(config: NLGConfig) -> str:
    """Get a style-appropriate closing."""
    if config.verbosity < 0.3:
        return ""
    closings = _CLOSINGS.get(config.style, _CLOSINGS["neutral"])
    return pick(closings, config.temperature)
