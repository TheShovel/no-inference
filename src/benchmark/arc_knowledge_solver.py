#!/usr/bin/env python3
"""
ARC-Easy Knowledge Graph Solver — targets 50%+.

Extracts (subject, predicate, object) triples from training data into a
hash-indexed knowledge base, then uses direct fact lookup and fuzzy matching
at test time, with fallback to the text-matching solver.

Strategy:
  1. Extract subject+predicate from each training question via pattern matching
  2. Store fact: hash(normalize(subject) + normalize(predicate)) -> answer_text
  3. Also index by subject alone and by content words for fuzzy retrieval
  4. At test time, try KB lookup first; fall back to text-matching solver
  5. Text similarity for matching KB objects to choices
"""

import json
import re
import time
from collections import defaultdict, Counter


# ── Stop words ────────────────────────────────────────────────────
STOP = frozenset(
    'a an the is are was were be been being am do does did has have had '
    'shall will would can could may might must need ought dare '
    'to of in on at for with by from into about like through across '
    'among between during before after above below between out off over '
    'under again further then once here there when where why how '
    'all each every both few more most other some such no nor not only '
    'own same so than too very just because as until while'
    .split()
)

# Auxiliary verbs that can signal a predicate boundary
AUX_VERBS = frozenset(
    'is are was were be been being am do does did has have had '
    'can could will would shall should may might must need dare '
    'ought used'
    .split()
)

# Main verbs frequently used as predicates in science questions
MAIN_VERBS = frozenset(
    'cause causes caused causing produce produces produced producing '
    'form forms formed forming create creates created creating '
    'occur occurs occurred occurring happen happens happened happening '
    'change changes changed changing convert converts converted converting '
    'transform transforms transformed transforming '
    'become becomes became becoming provide provides provided providing '
    'require requires required requiring need needs needed needing '
    'use uses used using make makes made making '
    'contain contains contained containing include includes included including '
    'involve involves involved involving '
    'determine determines determined determining '
    'affect affects affected affecting '
    'result results resulted resulting '
    'allow allows allowed allowing '
    'prevent prevents prevented preventing '
    'increase increases increased increasing '
    'decrease decreases decreased decreasing '
    'measure measures measured measuring '
    'transport transports transported transporting '
    'carry carries carried carrying '
    'pump pumps pumped pumping '
    'filter filters filtered filtering '
    'absorb absorbs absorbed absorbing '
    'release releases released releasing '
    'remove removes removed removing '
    'supply supplies supplied supplying '
    'break breaks broke broken breaking '
    'grow grows grew grown growing '
    'live lives lived living '
    'eat eats ate eaten eating '
    'feed feeds fed feeding '
    'transfer transfers transferred transferring '
    'reflect reflects reflected reflecting '
    'refract refracts refracted refracting '
    'conduct conducts conducted conducting '
    'insulate insulates insulated insulating '
    'protect protects protected protecting '
    'support supports supported supporting '
    'connect connects connected connecting '
    'separate separates separated separating '
    'divide divides divided dividing '
    'classify classifies classified classifying '
    'identify identifies identified identifying '
    'define defines defined defining '
    'describe describes described describing '
    'explain explains explained explaining '
    'represent represents represented representing '
    'indicate indicates indicated indicating '
    'suggest suggests suggested suggesting '
    'show shows showed shown showing '
    'illustrate illustrates illustrated illustrating '
    'relate relates related relating '
    'depend depends depended depending '
    'vary varies varied varying '
    'differ differs differed differing '
    'work works worked working '
    'begin begins began begun beginning '
    'start starts started starting '
    'stop stops stopped stopping '
    'move moves moved moving '
    'flow flows flowed flowing '
    'run runs ran running '
    'turn turns turned turning '
    'keep keeps kept keeping '
    'hold holds held holding '
    'push pushes pushed pushing '
    'pull pulls pulled pulling '
    'lift lifts lifted lifting '
    'fall falls fell fallen falling '
    'rise rises rose risen rising '
    'set sets set setting '
    'cut cuts cut cutting '
    'burn burns burned burning '
    'melt melts melted melting '
    'freeze freezes froze frozen freezing '
    'boil boils boiled boiling '
    'evaporate evaporates evaporated evaporating '
    'condense condenses condensed condensing '
    'solidify solidifies solidified solidifying '
    'dissolve dissolves dissolved dissolving '
    'mix mixes mixed mixing '
    'stir stirs stirred stirring '
    'heat heats heated heating '
    'cool cools cooled cooling '
    'expand expands expanded expanding '
    'contract contracts contracted contracting '
    'stretch stretches stretched stretching '
    'compress compresses compressed compressing '
    'attract attracts attracted attracting '
    'repel repels repelled repelling '
    'spin spins spun spinning '
    'rotate rotates rotated rotating '
    'revolve revolves revolved revolving '
    'orbit orbits orbited orbiting '
    'emit emits emitted emitting '
    'radiate radiates radiated radiating '
    'scatter scatters scattered scattering '
    'collect collects collected collecting '
    'accumulate accumulates accumulated accumulating '
    'deposit deposits deposited depositing '
    'erode erodes eroded eroding '
    'weather weathers weathered weathering '
    'sediment sediments sedimented sedimenting '
    'crystallize crystallizes crystallized crystallizing '
    'precipitate precipitates precipitated precipitating '
    'neutralize neutralizes neutralized neutralizing '
    'oxidize oxidizes oxidized oxidizing '
    'reduce reduces reduced reducing '
    'synthesize synthesizes synthesized synthesizing '
    'decompose decomposes decomposed decomposing '
    'digest digests digested digesting '
    'secrete secretes secreted secreting '
    'excrete excretes excreted excreting '
    'inhale inhales inhaled inhaling '
    'exhale exhales exhaled exhaling '
    'contract contracts contracted contracting '
    'relax relaxes relaxed relaxing '
    'constrict constricts constricted constricting '
    'dilate dilates dilated dilating '
    'clot clots clotted clotting '
    'heal heals healed healing '
    'repair repairs repaired repairing '
    'replace replaces replaced replacing '
    'destroy destroys destroyed destroying '
    'kill kills killed killing '
    'survive survives survived surviving '
    'adapt adapts adapted adapting '
    'evolve evolves evolved evolving '
    'mutate mutates mutated mutating '
    'reproduce reproduces reproduced reproducing '
    'mate mates mated mating '
    'hatch hatches hatched hatching '
    'migrate migrates migrated migrating '
    'hibernate hibernates hibernated hibernating '
    'pollinate pollinates pollinated pollinating '
    'germinate germinates germinated germinating '
    'fertilize fertilizes fertilized fertilizing '
    'photosynthesize photosynthesizes photosynthesized '
    'respire respires respired respiring '
    'circulate circulates circulated circulating '
    'coordinate coordinates coordinated coordinating '
    'regulate regulates regulated regulating '
    'control controls controlled controlling '
    'respond responds responded responding '
    'detect detects detected detecting '
    'perceive perceives perceived perceiving '
    .split()
)

ALL_VERBS = AUX_VERBS | MAIN_VERBS


# ── Utilities ─────────────────────────────────────────────────────

def _words(text):
    """Lowercased word tokens (letters only)."""
    return re.findall(r'[a-z]+', text.lower())


def _normalize(phrase):
    """Normalize: lowercase, remove stop words, keep word order."""
    words = [w for w in _words(phrase) if w not in STOP and len(w) > 1]
    return ' '.join(words)


def _content_words(text):
    """Content words as a frozenset for overlap matching."""
    return frozenset(_normalize(text).split())


def _word_overlap(a_words, b_words):
    """Jaccard overlap of two word sets/frozensets."""
    if not a_words or not b_words:
        return 0.0
    intersection = a_words & b_words
    if not intersection:
        return 0.0
    return len(intersection) / len(a_words | b_words)


def _trigrams(text):
    """Character trigrams for text matching."""
    return frozenset(text[i:i+3] for i in range(len(text) - 2))


def _text_sim(a, b):
    """Text similarity: trigram Jaccard + word overlap."""
    a_low = a.lower().strip()
    b_low = b.lower().strip()
    if a_low == b_low:
        return 1.0

    tri_a = _trigrams(a_low)
    tri_b = _trigrams(b_low)
    tri_sim = 0.0
    if tri_a and tri_b:
        inter = len(tri_a & tri_b)
        union = len(tri_a) + len(tri_b) - inter
        tri_sim = inter / union if union > 0 else 0.0

    word_a = _content_words(a)
    word_b = _content_words(b)
    word_sim = _word_overlap(word_a, word_b)

    return 0.4 * tri_sim + 0.6 * word_sim


def _find_best_choice(text, choices_texts, labels):
    """Find which choice best matches a given answer text."""
    best_score = 0.0
    best_label = labels[0]
    for label, ct in zip(labels, choices_texts):
        score = _text_sim(text, ct)
        if score > best_score:
            best_score = score
            best_label = label
    return best_label, best_score


# ── Verb detection ────────────────────────────────────────────────

def _is_verb(w):
    """Check if a word is likely a verb."""
    return w in ALL_VERBS or w.endswith('ed') or w.endswith('ing')


def _find_verb_index(tokens, start=0):
    """Find the index of the first verb in tokens starting from `start`."""
    for i in range(start, len(tokens)):
        if tokens[i] in ALL_VERBS or tokens[i].endswith('ed') or tokens[i].endswith('ing'):
            return i
    return -1


# ── Sentence splitting ────────────────────────────────────────────

def _get_last_sentence(text):
    """Get the last sentence of a question (the actual question part)."""
    ql = text.lower()
    ql = ' '.join(ql.split())
    sentences = re.split(r'(?<=[.!])\s+', ql)
    main = sentences[-1].strip().rstrip('?').strip() if sentences else ql
    return main


# ── Subject / Predicate Extraction ───────────────────────────────

def _extract_after_which(text):
    """
    Extract from 'Which X ...' patterns.
    Returns (subject, predicate) or (None, None).
    """
    rest = text[6:].strip()  # remove 'which '
    tokens = rest.split()
    if not tokens:
        return None, None

    verb_idx = _find_verb_index(tokens)

    if verb_idx > 0:
        subj = ' '.join(tokens[:verb_idx])
        pred = ' '.join(tokens[verb_idx:])
        return subj, pred
    elif verb_idx == 0:
        subj = tokens[0]
        pred = ' '.join(tokens[1:]) if len(tokens) > 1 else 'is'
        return subj, pred
    else:
        # No verb found - take first 1-2 words as subject
        subj = tokens[0]
        pred = ' '.join(tokens[1:]) if len(tokens) > 1 else 'is'
        return subj, pred


def _extract_subject_predicate(question):
    """
    Extract (subject, predicate) from a science question.

    Returns two normalized strings, or (None, None) if extraction fails.
    Handles the most common ARC-Easy question patterns.
    """
    q = question.strip()
    ql = q.lower()
    ql = ' '.join(ql.split())

    # Multi-sentence: focus on last sentence
    main = _get_last_sentence(ql)
    main_stripped = main.strip()

    subj = None
    pred = None

    # ── Pattern 1: "What is/are [subject]?" (definition) ──
    m = re.match(r'what\s+(?:is|are|was|were)\s+(.+)', main_stripped)
    if m:
        subj = m.group(1).strip()
        pred = 'definition'
        return _normalize(subj), _normalize(pred)

    # ── Pattern 2: "Which of the following ..." ──
    m = re.match(r'which\s+of\s+the\s+following\s+(.+)', main_stripped)
    if m:
        rest = m.group(1).strip()
        subj_m = re.match(r'is\s+(?:an\s+)?(?:example|type|kind)?\s*(?:of\s+)?(.+)', rest)
        if subj_m:
            subj = subj_m.group(1).strip()
            pred = 'example'
        else:
            subj = 'of the following'
            pred = rest
        return _normalize(subj), _normalize(pred)

    # ── Pattern 3: "Which [subject] [predicate]?" ──
    if main_stripped.startswith('which '):
        subj, pred = _extract_after_which(main_stripped)
        if subj and pred:
            return _normalize(subj), _normalize(pred)

    # ── Pattern 4: "What does/do [subject] [predicate]?" ──
    # Use verb boundary to split: what does/do [subject_phrase] [verb_phrase]
    m = re.match(r'what\s+(?:does|do)\s+(.+)', main_stripped)
    if m:
        after_aux = m.group(1).strip()
        tokens = after_aux.split()
        verb_idx = _find_verb_index(tokens)
        if verb_idx > 0:
            subj = ' '.join(tokens[:verb_idx])
            pred = ' '.join(tokens[verb_idx:])
        elif verb_idx == 0:
            subj = tokens[0]
            pred = ' '.join(tokens[1:]) if len(tokens) > 1 else 'general'
        else:
            subj = after_aux
            pred = 'general'
        if subj:
            return _normalize(subj), _normalize(pred)

    # ── Pattern 5: "What [verb] [rest]?" (verb must look like a real verb)
    # e.g., "What causes tides on Earth?" -> (tides earth, cause)
    m = re.match(r'what\s+(\w+)\s+(.+)', main_stripped)
    if m:
        verb_candidate = m.group(1)
        rest = m.group(2).strip()
        if _is_verb(verb_candidate) and verb_candidate not in AUX_VERBS:
            subj = rest
            pred = verb_candidate
            return _normalize(subj), _normalize(pred)

    # ── Pattern 5b: "What [subject] [predicate]?" (like Which)
    # e.g., "What organ pumps blood?" -> (organ, pumps blood)
    # e.g., "What plant uses sunlight for energy?" -> (plant, uses sunlight for energy)
    if main_stripped.startswith('what '):
        rest = main_stripped[5:].strip()
        tokens = rest.split()
        verb_idx = _find_verb_index(tokens)
        if verb_idx > 0:
            subj = ' '.join(tokens[:verb_idx])
            pred = ' '.join(tokens[verb_idx:])
            return _normalize(subj), _normalize(pred)

    # ── Pattern 6: "Where are/is [subject] [predicate]?" ──
    m = re.match(r'where\s+(?:are|is|were|was)\s+(.+?)\s+(.+)', main_stripped)
    if m:
        subj = m.group(1).strip()
        pred = 'located ' + m.group(2).strip()
        return _normalize(subj), _normalize(pred)

    # ── Pattern 7: "Where does/do [subject] [predicate]?" ──
    m = re.match(r'where\s+(?:does|do|can|will)\s+(.+?)\s+(.+)', main_stripped)
    if m:
        subj = m.group(1).strip()
        pred = m.group(2).strip()
        return _normalize(subj), _normalize(pred)

    # ── Pattern 8: "How does/do [subject] [predicate]?" ──
    m = re.match(r'how\s+(?:does|do|is|are|can|will)\s+(.+?)\s+(.+)', main_stripped)
    if m:
        subj = m.group(1).strip()
        pred = m.group(2).strip()
        return _normalize(subj), _normalize(pred)

    # ── Pattern 9: "When/If/After... [context], what/which..." ──
    m = re.match(r'(?:when|if|after|before|during|while|although)\s+(.+?),?\s+'
                 r'(?:what|which)\s+(.+?)\s+(.+)', main_stripped)
    if m:
        context = m.group(1).strip()
        subj = m.group(2).strip()
        pred = context + ' ' + m.group(3).strip()
        return _normalize(subj), _normalize(pred)

    # ── Pattern 10: "In [context], [subject] [predicate]?" ──
    m = re.match(r'in\s+(.+?),\s+(.+)', main_stripped)
    if m:
        context = m.group(1).strip()
        rest = m.group(2).strip()
        tokens = rest.split()
        verb_idx = _find_verb_index(tokens)
        if verb_idx > 0:
            subj = ' '.join(tokens[:verb_idx])
            pred = context + ' ' + ' '.join(tokens[verb_idx:])
        else:
            subj = tokens[0] if tokens else rest
            pred = context + ' ' + rest
        return _normalize(subj), _normalize(pred)

    # ── Pattern 11: Statement completion ──
    # "Rocks are classified as igneous, metamorphic, or sedimentary according to"
    # "When a switch is used in an electrical circuit, the switch can"

    # Remove leading context phrases like "when X, " or "in X, "
    clean = main_stripped
    m = re.match(r'(?:when|if|in|after|before|during|while|for|with|as)\s+.+?,\s*', clean)
    if m:
        clean = clean[m.end():]

    tokens = clean.split()
    if not tokens:
        return None, None

    verb_idx = _find_verb_index(tokens)
    if verb_idx > 0:
        subj = ' '.join(tokens[:verb_idx])
        pred = ' '.join(tokens[verb_idx:])
        return _normalize(subj), _normalize(pred)
    elif verb_idx == 0:
        subj = tokens[0]
        pred = ' '.join(tokens[1:]) if len(tokens) > 1 else 'general'
        return _normalize(subj), _normalize(pred)
    else:
        # No verb found - use first 1-2 content words as subject
        content = [w for w in tokens if w not in STOP]
        if content:
            subj = ' '.join(content[:2])
            pred = ' '.join(content[2:]) if len(content) > 2 else 'general'
            return _normalize(subj), _normalize(pred)

    return None, None


def _extract_full_question_kb(question):
    """
    Alternative extraction using the full question without last-sentence focusing.
    """
    ql = question.lower()
    ql = ' '.join(ql.split()).rstrip('?')

    # Try "Which [subject] [predicate]?" on full text
    if ql.startswith('which '):
        subj, pred = _extract_after_which(ql)
        if subj and pred:
            return subj, pred

    # Try "What does/do [subject] [predicate]?"
    m = re.match(r'what\s+(?:does|do)\s+(.+?)\s+(.+)', ql)
    if m:
        subj = m.group(1).strip()
        pred = m.group(2).strip()
        return _normalize(subj), _normalize(pred)

    # Try "What is/are [subject]?"
    m = re.match(r'what\s+(?:is|are|was|were)\s+(.+)', ql)
    if m:
        subj = m.group(1).strip()
        pred = 'definition'
        return _normalize(subj), _normalize(pred)

    return None, None


# ── Knowledge Base ────────────────────────────────────────────────

class KnowledgeBase:
    """Hash-indexed fact store: (subject, predicate) → answer."""

    def __init__(self):
        self.facts = {}           # (subj_norm, pred_norm) → answer_text
        self.subj_index = defaultdict(list)   # subj_norm → [(pred_norm, answer)]
        self.word_index = defaultdict(list)   # content_word → [(subj_norm, pred_norm, answer)]
        self.entries = 0

    def add_fact(self, subject, predicate, answer_text, question):
        """Add a fact to the KB."""
        if not subject or not predicate:
            return False

        key = (subject, predicate)
        if key not in self.facts:
            self.facts[key] = answer_text
            self.subj_index[subject].append((predicate, answer_text))
            # Index by individual content words in subject + predicate
            all_words = set(subject.split()) | set(predicate.split())
            for w in all_words:
                if len(w) > 2:
                    self.word_index[w].append((subject, predicate, answer_text))
            self.entries += 1
            return True
        return False

    def lookup_exact(self, subject, predicate):
        """Look up a fact by exact (subject, predicate)."""
        key = (subject, predicate)
        return self.facts.get(key)

    def lookup_subject(self, subject):
        """Look up facts by subject alone."""
        return self.subj_index.get(subject, [])

    def lookup_fuzzy(self, subject, predicate, min_overlap=0.3):
        """Fuzzy fact lookup: word overlap on subject and predicate."""
        if not subject and not predicate:
            return []

        subj_words = set(subject.split())
        pred_words = set(predicate.split())
        all_words = subj_words | pred_words

        results = []
        seen = set()

        candidates = defaultdict(float)
        for w in all_words:
            if len(w) > 2 and w in self.word_index:
                for s, p, a in self.word_index[w]:
                    key = (s, p)
                    candidates[key] += 1.0

        for (s, p), count in candidates.items():
            key = (s, p)
            if key in seen:
                continue
            seen.add(key)

            s_words = set(s.split())
            p_words = set(p.split())

            s_overlap = _word_overlap(subj_words, s_words) if subj_words and s_words else 0
            p_overlap = _word_overlap(pred_words, p_words) if pred_words and p_words else 0

            score = 0.6 * s_overlap + 0.4 * p_overlap

            if score >= min_overlap:
                results.append((score, self.facts.get(key, '')))

        results.sort(reverse=True, key=lambda x: x[0])
        return results


# ── Solver ────────────────────────────────────────────────────────

class ARCKBSolver:
    """
    ARC-Easy solver using a knowledge graph extracted from training data,
    with fallback to text-matching.
    """

    def __init__(self, train_path):
        self.kb = KnowledgeBase()
        self.fallback = None
        self._build(train_path)

    # ── Build KB ──────────────────────────────────────────────────

    def _build(self, train_path):
        print(f"  Loading training data: {train_path}")
        with open(train_path) as f:
            lines = f.readlines()
        N = len(lines)
        print(f"  {N} training examples...")

        fact_count = 0
        multi_facts = 0

        for line in lines:
            item = json.loads(line)
            question = item['question']
            choices = item['choices']

            key = item.get('answerKey', item.get('answer', ''))
            try:
                ai = choices['label'].index(key)
                answer_text = choices['text'][ai]
            except (ValueError, IndexError):
                continue

            # Primary extraction (last sentence focus)
            subj, pred = _extract_subject_predicate(question)
            if subj and pred:
                if self.kb.add_fact(subj, pred, answer_text, question):
                    fact_count += 1

            # Alternative extraction (full question)
            full_subj, full_pred = _extract_full_question_kb(question)
            if full_subj and full_pred and (full_subj, full_pred) != (subj, pred):
                if self.kb.add_fact(full_subj, full_pred, answer_text, question):
                    fact_count += 1
                    multi_facts += 1

        print(f"  Extracted {fact_count} facts from {N} examples"
              f" ({multi_facts} multi-fact)")
        print(f"  KB: {self.kb.entries} entries, "
              f"{len(self.kb.subj_index)} unique subjects")

        # Quick overlap check with test
        try:
            with open('/tmp/arc_easy.jsonl') as f:
                test_lines = [json.loads(l) for l in f]
        except FileNotFoundError:
            print("  (no test file found for overlap check)")
            return

        exact = 0
        fuzzy = 0
        subj_only = 0
        for t_item in test_lines:
            subj, pred = _extract_subject_predicate(t_item['question'])
            if not subj or not pred:
                continue
            if self.kb.lookup_exact(subj, pred):
                exact += 1
            elif self.kb.lookup_fuzzy(subj, pred, 0.5):
                fuzzy += 1
            elif self.kb.lookup_subject(subj):
                subj_only += 1

        print(f"  Test overlap: {exact} exact + {fuzzy} fuzzy + {subj_only} subj-only"
              f" = {exact+fuzzy+subj_only}/{len(test_lines)}")

    # ── Solve ─────────────────────────────────────────────────────

    def solve(self, question, choices):
        """
        Solve a single ARC-Easy question.
        Returns a label like 'A', 'B', 'C', or 'D'.
        """
        labels = choices['label']
        texts = choices['text']

        # Extract subject/predicate from the test question
        subj, pred = _extract_subject_predicate(question)

        best_overall_label = None
        best_overall_score = 0.0

        if subj and pred:
            # ── Phase 1: Exact KB lookup ──
            obj = self.kb.lookup_exact(subj, pred)
            if obj:
                label, score = _find_best_choice(obj, texts, labels)
                if score >= 0.30:
                    best_overall_label = label
                    best_overall_score = score + 0.2  # Boost exact matches

            # ── Phase 2: Subject-only lookup ──
            if best_overall_score < 0.5:
                subj_facts = self.kb.lookup_subject(subj)
                if subj_facts:
                    for pred_key, obj_text in subj_facts:
                        pred_sim = _word_overlap(
                            set(pred.split()),
                            set(pred_key.split())
                        ) if pred and pred_key else 0

                        label, score = _find_best_choice(obj_text, texts, labels)
                        if pred_sim > 0.25:
                            score = score * (0.6 + 0.4 * pred_sim)
                        elif pred_sim > 0:
                            score = score * 0.9

                        if score > best_overall_score:
                            best_overall_score = score
                            best_overall_label = label

            # ── Phase 3: Fuzzy KB lookup ──
            if best_overall_score < 0.4:
                fuzzy_results = self.kb.lookup_fuzzy(subj, pred, min_overlap=0.20)
                if fuzzy_results:
                    for fscore, obj_text in fuzzy_results[:5]:
                        label, score = _find_best_choice(obj_text, texts, labels)
                        combined = score * (0.3 + 0.7 * fscore)
                        if combined > best_overall_score:
                            best_overall_score = combined
                            best_overall_label = label

        # ── Phase 4: If KB found a decent match, use it ──
        if best_overall_label is not None and best_overall_score >= 0.30:
            return best_overall_label

        # ── Phase 5: Fallback to text-matching solver ──
        return self._fallback_solve(question, choices)

    # ── Fallback ──────────────────────────────────────────────────

    def _fallback_solve(self, question, choices):
        """Fallback: use the existing ARCEasySolver."""
        if self.fallback is None:
            try:
                from arc_solver import ARCEasySolver
                self.fallback = ARCEasySolver('/tmp/arc_easy_train.jsonl')
            except Exception:
                return self._simple_fallback(question, choices)

        return self.fallback.solve(question, choices)

    def _simple_fallback(self, question, choices):
        """Minimal fallback: pick choice with highest word overlap with question."""
        labels = choices['label']
        texts = choices['text']
        q_words = _content_words(question)

        best_label = labels[0]
        best_score = 0.0
        for label, text in zip(labels, texts):
            a_words = _content_words(text)
            score = _word_overlap(q_words, a_words)
            if score > best_score:
                best_score = score
                best_label = label
        return best_label

    # ── Benchmark ─────────────────────────────────────────────────

    def run_benchmark(self, test_path):
        """Run on test data and return accuracy percentage."""
        with open(test_path) as f:
            test_items = [json.loads(line) for line in f]

        correct = 0
        total = len(test_items)

        print(f"\n{'=' * 60}")
        print(f"  ARC-Easy Knowledge Graph Benchmark ({total} questions)")
        print(f"{'=' * 60}")

        for i, item in enumerate(test_items):
            question = item['question']
            choices = item['choices']
            expected = item.get('answerKey', item.get('answer', ''))

            pred = self.solve(question, choices)

            if pred == expected:
                correct += 1

            if (i + 1) % 200 == 0 or i < 5 or i == total - 1:
                pct = correct / (i + 1) * 100
                mark = '✓' if pred == expected else '✗'
                print(f"  {mark} [{i+1}/{total}] pred={pred} exp={expected} ({pct:.1f}%)")

        score = correct / total * 100 if total > 0 else 0
        print(f"\n  {'=' * 60}")
        print(f"  ARC-Easy KB: {correct}/{total} = {score:.1f}%")
        print(f"  {'=' * 60}")
        return score


# ── Main ──────────────────────────────────────────────────────────

def main():
    import sys
    train = sys.argv[1] if len(sys.argv) > 1 else '/tmp/arc_easy_train.jsonl'
    test = sys.argv[2] if len(sys.argv) > 2 else '/tmp/arc_easy.jsonl'
    print("=" * 60)
    print("  ARC-Easy Knowledge Graph Solver")
    print("=" * 60)
    start = time.time()
    solver = ARCKBSolver(train)
    score = solver.run_benchmark(test)
    print(f"  Time: {time.time() - start:.1f}s")
    return score


if __name__ == '__main__':
    main()
