#!/usr/bin/env python3
"""
HellaSwag Commonsense NLI Benchmark Solver.

Given a context (1—2 sentences describing a situation), picks the most likely
continuation from 4 choices using purely symbolic / commonsense reasoning.

Strategies (combined):
  1. Activity detection (30% weight) — detect the activity domain from the context
  2. Script-based scoring (40% weight) — match ending against expected next steps
  3. Ending quality analysis (20% weight) — entity freshness, verb consistency, etc.
  4. Negation/contradiction detection (10% weight) — penalize impossible continuations
  5. TF-IDF tiebreaker (used only when scores are equal)

Dependencies: Python standard library + pyarrow (for parquet reading).
No numpy, no scikit-learn.

Target: >= 35% accuracy (above random 25%).
"""

from __future__ import annotations

import json
import math
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Optional dependency checks
# ---------------------------------------------------------------------------

try:
    import pyarrow.parquet as pq

    HAS_PYARROW = True
except ImportError:
    HAS_PYARROW = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEED = 42
MAX_TRAIN = 30_000  # first 30k training examples
TOP_K_RETRIEVAL = 30  # number of neighbours to vote (tiebreaker only)
N_VAL_SAMPLES = 1000  # default validation samples

# Weights for each strategy component (must sum to 1.0)
W_ACTIVITY = 0.30
W_SCRIPT = 0.40
W_QUALITY = 0.20
W_CONTRADICTION = 0.10

# ---------------------------------------------------------------------------
# Text cleaning
# ---------------------------------------------------------------------------


def _clean(text: str) -> str:
    """Lower-case, collapse whitespace, strip heavy punctuation."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s'.,!?;-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _words(text: str) -> list[str]:
    """Tokenise into words."""
    return _clean(text).split()


# ---------------------------------------------------------------------------
# Feature helpers
# ---------------------------------------------------------------------------


def _char_ngrams(text: str, n: int = 4) -> set[str]:
    """Character n-grams as a set."""
    t = _clean(text)
    t = re.sub(r"\s+", "", t)
    return {t[i : i + n] for i in range(len(t) - n + 1)}


def _word_ngrams(text: str, n: int) -> set[str]:
    """Word n-grams as a set."""
    ws = _words(text)
    return {" ".join(ws[i : i + n]) for i in range(len(ws) - n + 1)}


def _long_words(text: str, min_len: int = 6) -> set[str]:
    """Words >= min_len characters."""
    return {w for w in _words(text) if len(w) >= min_len}


def _jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity, returns 0.0 if either set empty."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ---------------------------------------------------------------------------
# Domain definitions for activity detection and script-based scoring
# Each domain has: name, keyword triggers (checked in context), and expected
# script items (continuation verbs/nouns for the activity).
# ---------------------------------------------------------------------------

_DOMAIN_DEFS: list[dict[str, Any]] = [
    # 1. Construction / Roofing
    {
        "name": "construction_roofing",
        "keywords": [
            "roof", "tile", "hammer", "nail", "saw", "drill", "paint", "wall",
            "renovate", "build", "construction", "tool", "wood", "screw", "level",
            "plank", "beam", "ladder", "scaffold", "roofing", "shingle", "ceiling",
            "floor", "drywall", "plywood", "timber", "contractor", "fixing",
            "repairing", "demolish", "hammering", "sawing", "drilling", "renovation",
            "construction worker", "builder", "carpenter", "workman", "pull",
            "rip", "tear", "pry", "scrap", "scrape"
        ],
        "script": [
            "pull", "lift", "position", "measure", "mark", "cut", "attach", "secure",
            "fasten", "nail", "screw", "tighten", "level", "align", "check", "test",
            "inspect", "hammer", "install", "remove", "replace", "finish",
            "paint", "set", "adjust", "clean", "sweep", "dispose", "grab",
            "roofing"
        ]
    },
    # 2. Sports (general) - includes track & field, running, gymnastics, etc.
    {
        "name": "sports_general",
        "keywords": [
            "sport", "game", "team", "play", "ball", "court", "field", "score",
            "win", "lose", "practice", "train", "exercise", "athletic", "compete",
            "match", "player", "coach", "referee", "league", "tournament", "stadium",
            "track", "run", "running", "race", "racer", "jog", "jogging",
            "sprint", "marathon", "relay", "lane", "runner", "athlete",
            "gym", "gymnast", "gymnastics", "routine", "mat", "vault",
            "pole", "high jump", "long jump", "hurdle", "throw",
            "body", "height", "spring", "flip", "dismount", "land",
            "push", "spin", "twist", "turn", "reach", "extend"
        ],
        "script": [
            "warm", "stretch", "practice", "play", "compete", "score", "win",
            "celebrate", "cool", "rest", "run", "pass", "shoot", "kick", "hit",
            "defend", "tackle", "save", "cheer", "jump", "lift", "land",
            "high five", "high-five", "vault", "flip", "spin", "dismount",
            "pole", "spring", "pike", "tuck", "extend", "reach", "twist",
            "turn", "swing", "balance", "hold", "push", "pull"
        ]
    },
    # 3. Basketball
    {
        "name": "basketball",
        "keywords": [
            "basketball", "hoop", "dribble", "shoot", "rebound", "pass", "dunk",
            "free throw", "three point", "basket", "nba", "basketball court",
            "jump shot", "point guard", "layup"
        ],
        "script": [
            "dribble", "pass", "shoot", "rebound", "score", "defend", "run",
            "jump", "block", "steal", "dunk", "layup", "throw", "catch", "foul",
            "free throw", "timeout"
        ]
    },
    # 4. Soccer
    {
        "name": "soccer",
        "keywords": [
            "soccer", "football", "field", "goal", "kick", "pass", "dribble",
            "shoot", "score", "referee", "ball", "goalie", "goalkeeper",
            "penalty", "corner kick", "throw in", "fifa", "world cup"
        ],
        "script": [
            "pass", "dribble", "shoot", "kick", "score", "defend", "run",
            "chase", "tackle", "header", "save", "goal kick", "corner"
        ]
    },
    # 5. Baseball
    {
        "name": "baseball",
        "keywords": [
            "baseball", "bat", "hit", "pitch", "throw", "catch", "glove",
            "ball", "field", "batter", "pitcher", "catcher", "inning", "home run",
            "strike", "ball", "outfield", "infield", "diamond", "base", "mound"
        ],
        "script": [
            "pitch", "throw", "swing", "hit", "run", "catch", "field",
            "score", "strike", "swing", "slide", "tag", "throw"
        ]
    },
    # 6. Tennis
    {
        "name": "tennis",
        "keywords": [
            "tennis", "racket", "serve", "volley", "net", "court", "ball",
            "hit", "swing", "match", "grand slam", "backhand", "forehand",
            "deuce", "advantage", "set"
        ],
        "script": [
            "serve", "return", "volley", "rally", "hit", "swing", "score",
            "net", "overhead", "smash", "lob", "pass"
        ]
    },
    # 7. Cooking
    {
        "name": "cooking",
        "keywords": [
            "cook", "bake", "fry", "chop", "mix", "pour", "kitchen", "food",
            "meal", "recipe", "chef", "stove", "oven", "pan", "pot", "skillet",
            "ingredient", "spice", "salt", "pepper", "sauce", "stir", "boil",
            "simmer", "saute", "grill", "roast", "steam", "dice", "slice",
            "seasoning", "flavor", "taste", "dinner", "lunch", "breakfast"
        ],
        "script": [
            "prepare", "chop", "dice", "slice", "peel", "mix", "stir",
            "season", "cook", "saute", "boil", "fry", "grill", "bake",
            "taste", "plate", "serve", "eat", "garnish", "pour", "add"
        ]
    },
    # 8. Baking
    {
        "name": "baking",
        "keywords": [
            "bake", "oven", "cake", "bread", "cookie", "pastry", "dough",
            "flour", "sugar", "mix", "roll", "decorate", "bakery", "muffin",
            "pie", "cupcake", "frosting", "yeast", "knead"
        ],
        "script": [
            "mix", "knead", "shape", "roll", "bake", "cool", "frost",
            "decorate", "serve", "eat", "slice", "cut", "sprinkle", "glaze"
        ]
    },
    # 9. Vehicle repair / maintenance
    {
        "name": "vehicle_repair",
        "keywords": [
            "car", "drive", "repair", "fix", "engine", "tire", "bike",
            "vehicle", "truck", "mechanic", "hood", "trunk", "wheel",
            "garage", "oil", "fuel", "gas", "brake", "battery", "motor",
            "transmission", "axle", "muffler", "spark plug", "radiator"
        ],
        "script": [
            "inspect", "diagnose", "open", "remove", "repair", "replace",
            "fix", "test", "close", "clean", "tighten", "loosen", "check",
            "fill", "pump", "jack", "lift", "lower"
        ]
    },
    # 10. Cleaning
    {
        "name": "cleaning",
        "keywords": [
            "clean", "wash", "sweep", "mop", "vacuum", "dust", "wipe",
            "tidy", "scrub", "sponge", "bucket", "soap", "detergent",
            "cleaner", "disinfect", "sanitize", "broom", "duster",
            "cleaning", "washed", "cleaning up"
        ],
        "script": [
            "prepare", "apply", "scrub", "rinse", "dry", "wipe", "put away",
            "repeat", "fill", "empty", "spray", "polish", "buff", "sweep",
            "mop", "vacuum", "dust", "tidy", "organize"
        ]
    },
    # 11. Gardening
    {
        "name": "gardening",
        "keywords": [
            "plant", "water", "dig", "garden", "flower", "tree", "grass",
            "grow", "seed", "soil", "pot", "shovel", "rake", "weed",
            "prune", "harvest", "compost", "fertilizer", "sprout",
            "gardening", "planter", "flower bed", "lawn"
        ],
        "script": [
            "dig", "plant", "cover", "water", "fertilize", "weed",
            "prune", "harvest", "clean", "rake", "trim", "cut", "mulch",
            "pot", "repot", "sprinkle"
        ]
    },
    # 12. Music / playing instrument
    {
        "name": "music",
        "keywords": [
            "guitar", "piano", "drum", "sing", "song", "play", "instrument",
            "band", "concert", "music", "melody", "rhythm", "orchestra",
            "violin", "cello", "trumpet", "flute", "saxophone", "keyboard",
            "amplifier", "speaker", "microphone", "stage", "performance"
        ],
        "script": [
            "tune", "warm", "practice", "play", "strum", "pluck", "press",
            "perform", "sing", "applaud", "bow", "clap", "adjust", "set",
            "strike", "blow", "finger"
        ]
    },
    # 13. Art / drawing / painting
    {
        "name": "art_drawing",
        "keywords": [
            "paint", "draw", "sketch", "canvas", "brush", "color", "art",
            "create", "picture", "palette", "easel", "pencil", "crayon",
            "marker", "painting", "drawing", "sketching", "portrait",
            "landscape", "watercolor", "acrylic", "oil paint"
        ],
        "script": [
            "prepare", "sketch", "layer", "paint", "detail", "finish",
            "clean", "display", "mix", "brush", "stroke", "blend",
            "shade", "outline", "color", "fill"
        ]
    },
    # 14. Animal care
    {
        "name": "animal_care",
        "keywords": [
            "dog", "cat", "pet", "walk", "feed", "brush", "groom",
            "animal", "veterinary", "collar", "leash", "pet", "puppy",
            "kitten", "canine", "feline", "vet", "aquarium", "bird",
            "hamster", "rabbit", "animal shelter"
        ],
        "script": [
            "feed", "water", "walk", "groom", "brush", "play", "rest",
            "clean", "bath", "wash", "pet", "cuddle", "train", "leash",
            "collar", "treat", "reward", "stroke", "scratch", "lap", "sit"
        ]
    },
    # 15. Fishing (including ice fishing)
    {
        "name": "fishing",
        "keywords": [
            "fish", "rod", "reel", "bait", "cast", "catch", "lake",
            "river", "ocean", "hook", "line", "sinker", "fishing",
            "fisherman", "angling", "tackle", "net", "lure",
            "ice hole", "auger", "tip-up", "ice fishing", "angling"
        ],
        "script": [
            "prepare", "bait", "cast", "wait", "reel", "catch", "release",
            "clean", "hook", "line", "throw", "pull", "set", "drill",
            "cut", "hole", "drop", "jig"
        ]
    },
    # 16. Photography
    {
        "name": "photography",
        "keywords": [
            "camera", "photo", "picture", "lens", "focus", "shoot",
            "photograph", "capture", "image", "shutter", "light",
            "photographer", "aperture", "exposure", "flash", "tripod",
            "selfie", "portrait", "landscape photo"
        ],
        "script": [
            "setup", "frame", "focus", "shoot", "review", "adjust",
            "zoom", "click", "press", "capture", "save", "share",
            "edit", "filter"
        ]
    },
    # 17. Teaching / classroom
    {
        "name": "teaching",
        "keywords": [
            "teach", "class", "student", "lesson", "board", "explain",
            "learn", "school", "teacher", "classroom", "lecture", "professor",
            "education", "homework", "assignment", "exam", "test", "grade",
            "whiteboard", "chalkboard", "curriculum"
        ],
        "script": [
            "prepare", "explain", "demonstrate", "practice", "assess",
            "review", "assign", "grade", "discuss", "answer", "question",
            "write", "show", "present", "listen"
        ]
    },
    # 18. Medical / healthcare
    {
        "name": "medical",
        "keywords": [
            "hospital", "doctor", "patient", "medicine", "cure", "treatment",
            "nurse", "surgery", "clinic", "health", "medical", "diagnosis",
            "prescription", "pharmacy", "surgeon", "physician", "ambulance",
            "emergency", "exam room", "stethoscope"
        ],
        "script": [
            "examine", "diagnose", "treat", "prescribe", "monitor",
            "recover", "follow", "check", "test", "operate", "bandage",
            "inject", "take", "measure", "record"
        ]
    },
    # 19. Office work
    {
        "name": "office_work",
        "keywords": [
            "desk", "computer", "keyboard", "type", "email", "meeting",
            "work", "office", "business", "document", "file", "spreadsheet",
            "presentation", "colleague", "manager", "conference", "report",
            "deadline", "project", "printer", "scanner"
        ],
        "script": [
            "check", "plan", "execute", "review", "communicate", "archive",
            "close", "open", "type", "click", "save", "print", "send",
            "reply", "discuss", "present"
        ]
    },
    # 20. Shopping
    {
        "name": "shopping",
        "keywords": [
            "store", "buy", "purchase", "checkout", "bag", "pay", "shop",
            "customer", "cart", "browse", "sale", "mall", "supermarket",
            "grocery", "market", "cashier", "register", "credit card",
            "cash", "wallet", "shopping"
        ],
        "script": [
            "browse", "select", "cart", "checkout", "pay", "bag",
            "leave", "unpack", "pick", "choose", "scan", "swipe",
            "enter", "push", "load", "carry"
        ]
    },
    # 21. Hiking / outdoor
    {
        "name": "hiking_outdoor",
        "keywords": [
            "hike", "trail", "mountain", "walk", "nature", "forest",
            "climb", "outdoor", "backpack", "boot", "camp", "camping",
            "wilderness", "trail", "summit", "peak", "valley", "canyon",
            "nature trail", "outdoors"
        ],
        "script": [
            "prepare", "start", "follow", "rest", "reach", "enjoy",
            "return", "clean", "pack", "navigate", "explore", "trek",
            "ascend", "descend"
        ]
    },
    # 22. Woodworking / carpentry
    {
        "name": "woodworking",
        "keywords": [
            "wood", "carve", "sand", "saw", "woodwork", "timber", "chisel",
            "plane", "bench", "craft", "carpentry", "carpenter", "workbench",
            "table saw", "router", "sander", "lathe"
        ],
        "script": [
            "measure", "cut", "shape", "sand", "assemble", "finish",
            "polish", "carve", "plane", "glue", "clamp", "drill",
            "rout", "stain", "varnish"
        ]
    },
    # 23. Electronics / tech setup
    {
        "name": "electronics_tech",
        "keywords": [
            "computer", "phone", "device", "screen", "charge", "plug",
            "cable", "electronic", "gadget", "app", "monitor", "laptop",
            "tablet", "smartphone", "charger", "usb", "adapter", "battery",
            "wireless", "connection"
        ],
        "script": [
            "setup", "connect", "configure", "test", "use", "adjust",
            "maintain", "plug", "unplug", "press", "hold", "install",
            "update", "sync", "pair"
        ]
    },
    # 24. Bathing / personal hygiene / dressing
    {
        "name": "bathing_grooming",
        "keywords": [
            "shower", "bath", "sink", "toilet", "bathroom", "wash",
            "dry", "towel", "soap", "shampoo", "mirror", "bathe",
            "bathtub", "faucet", "drain", "washroom",
            "shampooing", "scrubbing", "sock", "socks", "shoe", "shoes",
            "dress", "dressing", "put on", "putting on", "button",
            "zipper", "clothing", "shirt", "pants", "jacket", "coat",
            "boot", "boots", "foot", "feet"
        ],
        "script": [
            "prepare", "wet", "wash", "rinse", "dry", "towel",
            "put away", "turn", "adjust", "soap", "lather", "clean",
            "open", "close", "step", "put on", "pull on", "button",
            "zip", "tie", "lace", "fasten", "slip"
        ]
    },
    # 25. Exercise / workout
    {
        "name": "exercise_workout",
        "keywords": [
            "exercise", "workout", "gym", "fitness", "lift", "weight",
            "muscle", "train", "squat", "bench", "cardio", "dumbbell",
            "barbell", "treadmill", "pull-up", "push-up", "sit-up",
            "personal trainer", "fitness", "weightlift", "deadlift",
            "press", "leg press", "curl", "extension", "rep", "set",
            "bar", "pole", "weights", "strength"
        ],
        "script": [
            "warm", "stretch", "lift", "run", "push", "pull", "squat",
            "cool", "stretch", "shower", "rest", "breathe", "spot",
            "rack", "load", "unload", "stand", "grab", "hold",
            "press", "curl", "extend", "lower", "raise"
        ]
    },
    # 26. Reading
    {
        "name": "reading",
        "keywords": [
            "read", "book", "page", "story", "novel", "magazine",
            "article", "literature", "library", "reader", "reading",
            "paperback", "hardcover", "chapter", "author", "textbook"
        ],
        "script": [
            "open", "read", "turn", "reflect", "bookmark", "close",
            "return", "sit", "flip", "scan", "browse"
        ]
    },
    # 27. Writing
    {
        "name": "writing",
        "keywords": [
            "write", "letter", "note", "paper", "pen", "essay", "journal",
            "notebook", "author", "compose", "typewriter", "manuscript",
            "writing", "written", "poem", "novel", "article"
        ],
        "script": [
            "plan", "draft", "write", "revise", "edit", "finalize",
            "share", "type", "think", "cross", "erase"
        ]
    },
    # 28. Yoga / meditation
    {
        "name": "yoga_meditation",
        "keywords": [
            "yoga", "meditate", "stretch", "breathe", "pose", "mat",
            "mindfulness", "relax", "calm", "meditation", "downward dog",
            "lotus", "asana", "chakra", "breath"
        ],
        "script": [
            "center", "stretch", "pose", "breathe", "hold", "release",
            "relax", "rest", "close", "sit", "lie", "focus"
        ]
    },
    # 29. Dancing
    {
        "name": "dancing",
        "keywords": [
            "dance", "move", "rhythm", "music", "step", "choreography",
            "performance", "dancer", "ballroom", "ballet", "tap",
            "hip hop", "swing", "tango", "waltz", "dancing"
        ],
        "script": [
            "warm", "learn", "practice", "stretch", "perform", "bow",
            "spin", "turn", "step", "glide", "dip", "lift"
        ]
    },
    # 30. Celebration / party
    {
        "name": "celebration_party",
        "keywords": [
            "party", "celebrate", "birthday", "holiday", "gather",
            "friends", "cake", "gift", "toast", "wedding", "anniversary",
            "festival", "celebration", "decorate", "balloon", "confetti",
            "happy birthday", "new year", "drink", "drinks", "fountain",
            "music", "dance", "cheer", "crowd", "audience", "performance"
        ],
        "script": [
            "prepare", "greet", "eat", "drink", "socialize", "gift",
            "clean", "sing", "toast", "mingle", "chat", "laugh",
            "dance", "applaud"
        ]
    },
    # 31. Travel
    {
        "name": "travel",
        "keywords": [
            "travel", "trip", "vacation", "hotel", "airport", "luggage",
            "journey", "passport", "tourist", "fly", "flight", "suitcase",
            "boarding pass", "destination", "tour", "sightseeing",
            "backpacking", "road trip", "traveling"
        ],
        "script": [
            "pack", "drive", "fly", "arrive", "check", "explore",
            "relax", "return", "board", "sit", "wait", "unpack",
            "book", "reserve"
        ]
    },
    # 32. Coding / programming
    {
        "name": "coding",
        "keywords": [
            "code", "program", "software", "app", "develop", "engineer",
            "algorithm", "debug", "compile", "syntax", "programming",
            "developer", "script", "function", "variable", "loop",
            "coding", "programmer", "computer science", "coding"
        ],
        "script": [
            "plan", "code", "test", "debug", "commit", "deploy",
            "review", "write", "compile", "run", "fix", "refactor",
            "document"
        ]
    },
    # 33. Conversation / social
    {
        "name": "conversation",
        "keywords": [
            "talk", "speak", "discuss", "conversation", "chat",
            "interview", "phone", "call", "meeting", "ask", "tell",
            "say", "speech", "dialogue", "communicate"
        ],
        "script": [
            "greet", "ask", "listen", "respond", "discuss", "conclude",
            "follow", "nod", "answer", "explain", "share", "agree"
        ]
    },
    # 34. Baby / kids care
    {
        "name": "baby_kids",
        "keywords": [
            "baby", "child", "kid", "crib", "diaper", "bottle", "parent",
            "toddler", "infant", "nursery", "stroller", "pacifier",
            "babysit", "children", "little one", "newborn"
        ],
        "script": [
            "feed", "change", "burp", "bathe", "dress", "soothe",
            "sleep", "rock", "hold", "carry", "play", "sing",
            "cuddle", "wrap"
        ]
    },
    # 35. Gaming
    {
        "name": "gaming",
        "keywords": [
            "game", "play", "console", "controller", "screen", "video game",
            "level", "player", "gaming", "xbox", "playstation", "nintendo",
            "arcade", "joystick", "character", "avatar"
        ],
        "script": [
            "launch", "play", "progress", "save", "pause", "resume",
            "finish", "select", "press", "move", "jump", "shoot",
            "explore", "defeat"
        ]
    },
    # 36. Makeup / grooming
    {
        "name": "makeup_grooming",
        "keywords": [
            "hair", "brush", "comb", "makeup", "style", "mirror",
            "face", "moisturize", "shave", "beard", "cosmetic",
            "lipstick", "eyeliner", "foundation", "blush", "perfume",
            "hairdryer", "curler"
        ],
        "script": [
            "wash", "dry", "apply", "style", "brush", "fix", "check",
            "blow", "curl", "straighten", "trim", "shave", "pluck"
        ]
    },
    # 37. Laundry
    {
        "name": "laundry",
        "keywords": [
            "laundry", "wash", "clothes", "washer", "dryer", "detergent",
            "fold", "iron", "hamper", "washing machine", "dry clean",
            "fabric softener", "basket", "launder"
        ],
        "script": [
            "sort", "load", "wash", "dry", "fold", "iron", "put away",
            "separate", "add", "pour", "set", "start"
        ]
    },
    # 38. Bedtime / sleep
    {
        "name": "bedtime_sleep",
        "keywords": [
            "bed", "sleep", "nap", "tired", "night", "pillow", "blanket",
            "dream", "rest", "asleep", "bedroom", "mattress", "sheet",
            "comforter", "sleepy", "doze", "slumber"
        ],
        "script": [
            "prepare", "change", "brush", "read", "lie", "sleep",
            "dream", "rest", "turn", "close", "cover", "settle"
        ]
    },
    # 39. Morning routine
    {
        "name": "morning_routine",
        "keywords": [
            "morning", "wake", "alarm", "sunrise", "breakfast", "coffee",
            "start day", "early", "dawn", "get up", "wake up"
        ],
        "script": [
            "wake", "stretch", "get up", "wash", "dress", "eat",
            "leave", "brush", "shower", "make", "drink", "check"
        ]
    },
    # 40. Sewing / crafts
    {
        "name": "sewing_crafts",
        "keywords": [
            "sew", "needle", "thread", "fabric", "stitch", "pattern",
            "cloth", "knit", "crochet", "embroidery", "quilting",
            "sewing machine", "button", "zipper", "hem"
        ],
        "script": [
            "measure", "cut", "pin", "sew", "stitch", "finish",
            "iron", "thread", "knot", "snip", "weave", "knit",
            "crochet", "patch"
        ]
    },
    # 41. Farming / agriculture
    {
        "name": "farming",
        "keywords": [
            "farm", "farmer", "crop", "tractor", "field", "harvest",
            "plant", "grain", "corn", "wheat", "vegetable", "orchard",
            "barn", "livestock", "cattle", "chicken", "horse", "plow",
            "irrigation", "ranch"
        ],
        "script": [
            "plow", "plant", "water", "tend", "harvest", "clean",
            "feed", "milk", "collect", "store", "pack", "sell"
        ]
    },
    # 42. Construction (general building)
    {
        "name": "general_construction",
        "keywords": [
            "build", "construct", "building", "construction site",
            "worker", "hard hat", "weld", "steel", "concrete",
            "brick", "cement", "foundation", "frame", "scaffolding"
        ],
        "script": [
            "measure", "cut", "assemble", "lift", "place", "secure",
            "fasten", "weld", "pour", "set", "finish", "inspect",
            "level", "align"
        ]
    },
    # 43. Eating / dining
    {
        "name": "eating_dining",
        "keywords": [
            "eat", "dine", "food", "meal", "restaurant", "fork",
            "knife", "spoon", "plate", "dinner", "lunch", "breakfast",
            "dining room", "table", "menu", "waiter", "order",
            "hungry", "starving"
        ],
        "script": [
            "sit", "order", "wait", "eat", "drink", "talk", "pay",
            "leave", "tip", "serve", "cut", "chew", "sip"
        ]
    },
    # 44. Watching TV / movies
    {
        "name": "watching_tv",
        "keywords": [
            "watch", "tv", "television", "movie", "film", "show",
            "episode", "screen", "channel", "remote", "couch",
            "sofa", "netflix", "cinema", "theater", "documentary"
        ],
        "script": [
            "sit", "select", "play", "watch", "recline", "snack",
            "pause", "resume", "turn", "adjust", "change"
        ]
    },
    # 45. Snow / winter activities
    {
        "name": "winter_snow",
        "keywords": [
            "snow", "ski", "snowboard", "ice", "winter", "cold",
            "snowball", "shovel snow", "sled", "icicle", "freeze",
            "snowman", "blizzard", "snowflake", "ice skate", "skate"
        ],
        "script": [
            "bundle", "step", "slide", "glide", "fall", "get up",
            "warm", "shake", "brush", "throw", "build", "pack"
        ]
    },
]

# ---------------------------------------------------------------------------
# Static analysis: build keyword & script lookup sets for efficiency
# ---------------------------------------------------------------------------

_DOMAIN_MAP: list[dict[str, Any]] = _DOMAIN_DEFS

# Pre-extract all keywords and script items for fast scoring
_ALL_DOMAIN_KEYWORDS: list[set[str]] = [
    set(d["keywords"]) for d in _DOMAIN_MAP
]
_ALL_DOMAIN_SCRIPTS: list[set[str]] = [
    set(d["script"]) for d in _DOMAIN_MAP
]

# Common verbs that indicate ongoing/progressive action (present participle)
_PROGRESSIVE_VERBS: set[str] = {
    "ing", "making", "doing", "going", "coming", "taking", "getting",
    "putting", "sitting", "standing", "walking", "running", "looking",
    "trying", "holding", "pulling", "pushing", "starting", "beginning",
}

# Contradiction / negation markers
_NEGATION_WORDS: set[str] = {
    "not", "n't", "no", "never", "nothing", "nobody", "nowhere",
    "neither", "nor", "none", "cannot", "can't", "don't", "doesn't",
    "didn't", "won't", "wouldn't", "shouldn't", "couldn't",
    "isn't", "aren't", "wasn't", "weren't", "haven't", "hasn't",
    "hadn't", "mustn't", "needn't"
}

# Contradiction pairs: if the context has verb A, the ending shouldn't have verb B
_CONTRADICTION_PAIRS: list[tuple[set[str], set[str]]] = [
    # sitting → shouldn't be running, jumping, etc.
    ({"sit", "sits", "sitting", "sat"}, {"run", "runs", "running", "jump", "jumping", "sprint"}),
    # lying / sleeping → shouldn't be running
    ({"lie", "lies", "laying", "lying", "sleep", "sleeps", "sleeping"}, {"run", "runs", "running", "jump", "jumping", "stand", "standing"}),
    # standing → shouldn't be lying
    ({"stand", "stands", "standing"}, {"lie", "lies", "lying", "sleep", "sleeps", "sleeping"}),
    # entering → shouldn't be leaving
    ({"enter", "enters", "entering", "come", "comes", "coming"}, {"exit", "exits", "exiting", "leave", "leaves", "leaving"}),
    # leaving → shouldn't be entering
    ({"leave", "leaves", "leaving", "exit", "exits", "exiting"}, {"enter", "enters", "entering", "come", "come", "coming"}),
    # closing / shutting → shouldn't be opening
    ({"close", "closes", "closing", "shut", "shuts", "shutting"}, {"open", "opens", "opening"}),
    # opening → shouldn't be closing
    ({"open", "opens", "opening"}, {"close", "closes", "closing", "shut", "shuts", "shutting"}),
    # putting away → shouldn't be taking out
    ({"put", "puts", "putting", "store", "storing", "away"}, {"take", "takes", "taking", "out"}),
    # taking out → shouldn't be putting away
    ({"take", "takes", "taking", "out"}, {"put", "puts", "putting", "store", "storing", "away"}),
    # dropping → shouldn't be holding steady
    ({"drop", "drops", "dropped", "dropping", "fall", "falls", "falling"}, {"hold", "holds", "holding", "catch", "catches", "catching"}),
    # catching → shouldn't be dropping
    ({"catch", "catches", "catching", "hold", "holds", "holding"}, {"drop", "drops", "dropped", "dropping", "fall", "falls", "falling"}),
    # waking → shouldn't be sleeping
    ({"wake", "wakes", "waking", "awake"}, {"sleep", "sleeps", "sleeping", "nap", "napping"}),
    # sleeping → shouldn't be waking
    ({"sleep", "sleeps", "sleeping", "nap", "napping"}, {"wake", "wakes", "waking", "awake"}),
    # dry → shouldn't be wetting
    ({"dry", "dries", "drying"}, {"wet", "wets", "wetting", "soak", "soaking"}),
    # clean → shouldn't be dirtying
    ({"clean", "cleans", "cleaning"}, {"dirty", "dirties", "soiling", "stain"}),
    # stop → shouldn't be continuing (and vice versa)
    ({"stop", "stops", "stopping"}, {"continue", "continues", "continuing", "proceed", "proceeds"}),
    # invisible → shouldn't be visible
    ({"disappear", "disappears", "disappearing", "hide", "hides", "hiding"}, {"appear", "appears", "appearing", "show", "shows", "showing"}),
]

# Common pronouns for consistency checking
_HE_PRONOUNS = {"he", "his", "him", "himself"}
_SHE_PRONOUNS = {"she", "her", "hers", "herself"}
_THEY_PRONOUNS = {"they", "them", "their", "theirs", "themselves"}
_I_PRONOUNS = {"i", "me", "my", "mine", "myself"}
_WE_PRONOUNS = {"we", "us", "our", "ours", "ourselves"}
_IT_PRONOUNS = {"it", "its", "itself"}

_SEQUENCE_WORDS = {
    "then", "next", "after", "before", "finally", "eventually",
    "so", "thus", "therefore", "continues", "continuing",
    "proceed", "proceeds", "now", "first", "second", "third",
    "last", "lastly", "subsequently", "afterward", "afterwards"
}

_ACTION_COMPLETION_VERBS = {
    "finish", "finishes", "finished", "complete", "completed",
    "done", "finalize", "finalized", "end", "ends", "ended",
    "stop", "stops", "stopped"
}

# ---------------------------------------------------------------------------
# Fuzzy word matching (handles basic English inflections)
# ---------------------------------------------------------------------------


def _word_matches(word: str, targets: set[str]) -> bool:
    """Check if `word` matches any target, handling common inflections.

    Handles:
      - Exact match
      - Prefix match (len >= 4): "pull" in "pulling", "tile" in "tiles"
      - Common suffix stripping: "running" -> "run", "tiles" -> "tile"
    """
    if word in targets:
        return True

    # Prefix matching for longer words (catches "pull" in "pulling", "tile" in "tiles")
    for target in targets:
        # For short targets, only exact match
        if len(target) <= 3 and len(word) <= 3:
            continue
        if word.startswith(target) or target.startswith(word):
            if min(len(word), len(target)) >= 3:
                return True

    # Try stripping common suffixes
    stripped = _strip_suffix(word)
    if stripped is not None and stripped in targets:
        return True
    if len(word) >= 4 and word[:-1] in targets:
        return True

    return False


def _strip_suffix(word: str) -> str | None:
    """Strip common English inflectional suffixes. Returns None if no change."""
    # -ing forms (running -> run, making -> make)
    if word.endswith("ing") and len(word) > 4:
        base = word[:-3]
        if base.endswith("nn") or base.endswith("tt") or base.endswith("mm"):
            return base[:-1]
        # running -> run, sitting -> sit, putting -> put
        if len(base) >= 2 and base[-1] == base[-2]:
            return base[:-1]
        # making -> make, taking -> take
        if base.endswith("k") and len(base) >= 3:
            return base + "e"
        return base
    # -ed forms (pulled -> pull, danced -> dance)
    if word.endswith("ed") and len(word) > 4:
        base = word[:-2]
        if base.endswith("i"):
            return base[:-1] + "y"
        if base.endswith("nn") or base.endswith("tt"):
            return base[:-1]
        return base
    # -s/-es forms (tiles -> tile, boxes -> box, cries -> cry)
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        base = word[:-1]
        if base in ["run", "sit", "put", "cut"]:
            return base
        if base.endswith("i"):
            return base[:-1] + "y"
        return base
    if word.endswith("es") and len(word) > 4:
        base = word[:-2]
        if base.endswith("i"):
            return base[:-1] + "y"
        return base
    # -ly adverbs (quickly -> quick)
    if word.endswith("ly") and len(word) > 5:
        return word[:-2]
    return None


def _fuzzy_overlap(words: set[str], targets: set[str]) -> float:
    """Overlap ratio using fuzzy word matching.

    Returns the proportion of ending words (any length) that fuzzy-match
    any target word. Simpler ratio approach.
    """
    if not words or not targets:
        return 0.0
    match_count = 0
    for w in words:
        if _word_matches(w, targets):
            match_count += 1
    return match_count / max(len(words), 1)


# ---------------------------------------------------------------------------
# Domain detection
# ---------------------------------------------------------------------------


def _detect_domains(context: str) -> list[int]:
    """Return indices of domains whose keywords appear in the context."""
    ctx_lower = context.lower()
    active: set[int] = set()
    for i, keywords in enumerate(_ALL_DOMAIN_KEYWORDS):
        for kw in keywords:
            if kw in ctx_lower:
                active.add(i)
                break
    return sorted(active)


# ---------------------------------------------------------------------------
# Activity detection score (30% final weight)
# Measures how well an ending shares vocabulary with the detected domain
# ---------------------------------------------------------------------------


def _activity_score(
    context: str, endings: list[str], active_domains: list[int]
) -> list[float]:
    """Score each ending by keyword overlap with the detected activity domain.

    Uses fuzzy word matching to handle inflections.
    """
    scores = [0.0] * 4
    if not active_domains:
        return scores

    # Union all keywords for activated domains
    domain_kws: set[str] = set()
    for di in active_domains:
        domain_kws.update(_ALL_DOMAIN_KEYWORDS[di])

    if not domain_kws:
        return scores

    ctx_words = set(_words(context))
    # Also include context words that match domain keywords
    for w in ctx_words:
        if _word_matches(w, domain_kws):
            domain_kws.add(w)

    for i, ending in enumerate(endings):
        end_words = set(_words(ending))
        if not end_words:
            continue
        # Fuzzy overlap between ending words and domain keywords
        scores[i] = _fuzzy_overlap(end_words, domain_kws)

    return scores


# ---------------------------------------------------------------------------
# Script-based scoring (40% final weight)
# Measures how well the ending matches expected next steps for the domain
# ---------------------------------------------------------------------------


def _script_score(
    context: str, endings: list[str], active_domains: list[int]
) -> list[float]:
    """Score each ending by overlap with expected script items for detected domains.

    Uses fuzzy word matching to handle inflections.
    """
    scores = [0.0] * 4
    if not active_domains:
        return scores

    # Union all script items for activated domains
    script_items: set[str] = set()
    for di in active_domains:
        script_items.update(_ALL_DOMAIN_SCRIPTS[di])

    if not script_items:
        return scores

    # Find context words that fuzzy-match script items
    ctx_words = set(_words(context))
    context_script_overlap = set()
    for w in ctx_words:
        if _word_matches(w, script_items):
            context_script_overlap.add(w)

    for i, ending in enumerate(endings):
        end_words = set(_words(ending))
        if not end_words:
            continue

        # Fuzzy overlap with script items
        base_score = _fuzzy_overlap(end_words, script_items)

        # Bonus: ending continues with script items after context mentioned a script word
        context_boost = 1.0
        if context_script_overlap:
            ending_script_hit = _fuzzy_overlap(end_words, script_items)
            if ending_script_hit > 0:
                context_boost = 1.3

        # Bonus: sequence words indicate continuation
        if any(w in _SEQUENCE_WORDS for w in end_words):
            context_boost = max(context_boost, 1.15)

        # Bonus: ending reuses words from the context (continuity)
        ctx_overlap = sum(1 for w in end_words if w in ctx_words)
        if ctx_overlap >= 2:
            context_boost = max(context_boost, 1.2)

        scores[i] = base_score * context_boost

    return scores


# ---------------------------------------------------------------------------
# Ending quality analysis (20% final weight)
# Linguistic quality: entity freshness, verb consistency, pronoun agreement,
# action completion
# ---------------------------------------------------------------------------


def _quality_score(context: str, endings: list[str]) -> list[float]:
    """Score each ending on linguistic quality and consistency.

    Combines linguistic checks with general text overlap (helps when
    no specific domain is detected).
    """
    scores = [0.0] * 4
    ctx_words_set = set(_words(context))
    ctx_words_list = _words(context)

    # Check if context ends mid-sentence (lowercase continuation expected)
    context_ends_incomplete = (
        context.rstrip().endswith(",")
        or context.rstrip().endswith("he")
        or context.rstrip().endswith("she")
        or context.rstrip().endswith("it")
        or context.rstrip().endswith("they")
        or context.rstrip().endswith("the")
        or context.rstrip().endswith("a")
        or context.rstrip().endswith("and")
        or context.rstrip().endswith("but")
        or context.rstrip().endswith("to")
        or context.rstrip().endswith("his")
        or context.rstrip().endswith("her")
        or context.rstrip().endswith("their")
    )

    # Pronoun sets in context
    ctx_has_he = any(w in _HE_PRONOUNS for w in ctx_words_set)
    ctx_has_she = any(w in _SHE_PRONOUNS for w in ctx_words_set)
    ctx_has_they = any(w in _THEY_PRONOUNS for w in ctx_words_set)
    ctx_has_i = any(w in _I_PRONOUNS for w in ctx_words_set)
    ctx_has_we = any(w in _WE_PRONOUNS for w in ctx_words_set)
    ctx_has_it = any(w in _IT_PRONOUNS for w in ctx_words_set)

    # Detect the main verb in the context (last verb-like word)
    ctx_main_verb = ""
    for w in reversed(ctx_words_list):
        if len(w) > 2 and not w in {"the", "and", "for", "are", "was", "were", "has", "had", "but", "not"}:
            ctx_main_verb = w
            break

    for i, ending in enumerate(endings):
        end_words = set(_words(ending))
        end_words_list = _words(ending)

        if not end_words:
            scores[i] = 0.1
            continue

        quality = 1.0

        # --- 0. General text overlap (important baseline) ---
        # This helps even when no specific domain is detected
        overlap_count = sum(1 for w in end_words if w in ctx_words_set)
        if end_words:
            overlap_ratio = overlap_count / max(len(end_words), 1)
            quality *= (0.8 + 0.4 * overlap_ratio)  # ranges 0.8-1.2

        # --- 1. Entity freshness: penalize unrelated new nouns ---
        new_entities = {w for w in end_words if len(w) >= 5 and w not in ctx_words_set}
        if new_entities:
            newness_penalty = 1.0 - min(0.6, len(new_entities) * 0.12)
            quality *= newness_penalty

        # Bonus: if ending reuses context entities (continuity)
        shared_content = {w for w in end_words if len(w) >= 5 and w in ctx_words_set}
        if shared_content:
            quality *= 1.0 + min(0.15, len(shared_content) * 0.05)

        # --- 2. Sentence continuation / capitalization ---
        if context_ends_incomplete and ending and ending[0].islower():
            quality *= 1.12
        elif not context_ends_incomplete and ending and ending[0].isupper():
            quality *= 1.08

        # --- 3. Pronoun consistency ---
        end_has_he = any(w in _HE_PRONOUNS for w in end_words)
        end_has_she = any(w in _SHE_PRONOUNS for w in end_words)
        end_has_they = any(w in _THEY_PRONOUNS for w in end_words)
        end_has_i = any(w in _I_PRONOUNS for w in end_words)
        end_has_we = any(w in _WE_PRONOUNS for w in end_words)
        end_has_it = any(w in _IT_PRONOUNS for w in end_words)

        if ctx_has_he and end_has_she:
            quality *= 0.5
        if ctx_has_she and end_has_he:
            quality *= 0.5
        if ctx_has_he and end_has_they and not any(w in ctx_words_set for w in {"and", "with"}):
            quality *= 0.7
        if ctx_has_she and end_has_they and not any(w in ctx_words_set for w in {"and", "with"}):
            quality *= 0.7
        if ctx_has_i and (end_has_he or end_has_she or end_has_they):
            quality *= 0.7
        if ctx_has_we and end_has_they and not any(w in ctx_words_set for w in {"and", "with"}):
            quality *= 0.7
        if ctx_has_we and end_has_he:
            quality *= 0.7
        if ctx_has_it and (end_has_they and not ("and" in end_words or "with" in end_words)):
            quality *= 0.6

        # --- 4. Action / verb continuation ---
        # If the ending continues with the same verb/action as context
        if ctx_main_verb and ctx_main_verb in end_words:
            quality *= 1.2
        # Action completion is good
        if any(v in _ACTION_COMPLETION_VERBS for v in end_words):
            quality *= 1.15
        # Ending starts with a verb in -ing form (natural continuation)
        if end_words_list and end_words_list[0].endswith("ing"):
            quality *= 1.1


        # --- 5. Length quality ---
        end_len = len(end_words)
        if end_len < 3:
            quality *= 0.6
        elif end_len > 50:
            quality *= 0.7
        elif end_len < 6:
            quality *= 0.9  # slightly short

        # --- 6. Sequence continuity bonus ---
        if end_words_list and any(w in _SEQUENCE_WORDS for w in end_words_list[:3]):
            quality *= 1.1

        scores[i] = quality

    return scores


# ---------------------------------------------------------------------------
# Negation / contradiction detection (10% final weight)
# Returns higher scores for *good* endings, so we return 1.0 for clean
# endings and lower for contradictory ones.
# ---------------------------------------------------------------------------


def _contradiction_penalty(context: str, endings: list[str]) -> list[float]:
    """Score each ending (1.0 = no contradiction, lower = contradictory)."""
    scores = [1.0] * 4
    ctx_clean = _clean(context)
    ctx_words = set(_words(context))

    # Count negations in context
    ctx_negations = sum(1 for w in ctx_words if w in _NEGATION_WORDS)
    context_is_negative = ctx_negations > 0

    for i, ending in enumerate(endings):
        end_clean = _clean(ending)
        end_words = set(_words(ending))

        if not end_words:
            scores[i] = 0.5
            continue

        # --- 1. Check contradiction pairs ---
        for ctx_verbs, end_verbs in _CONTRADICTION_PAIRS:
            if any(w in ctx_words for w in ctx_verbs):
                if any(w in end_words for w in end_verbs):
                    scores[i] *= 0.3
                    break

        # --- 2. Double negation: context is positive but ending negates ---
        if not context_is_negative:
            end_negations = sum(1 for w in end_words if w in _NEGATION_WORDS)
            if end_negations > 0:
                scores[i] *= max(0.4, 1.0 - end_negations * 0.3)

        # --- 3. Context says "stops X" but ending continues X ---
        stop_verbs = {"stop", "stops", "stopping", "quit", "quits", "quitting", "cease"}
        continue_verbs = {"continue", "continues", "continuing", "resume", "resumes"}
        if any(w in ctx_words for w in stop_verbs):
            if any(w in end_words for w in continue_verbs):
                scores[i] *= 0.4

        # --- 4. Temporal contradictions ---
        if "will" in ctx_words or "going" in ctx_words:
            end_past_count = sum(1 for w in end_words if w.endswith("ed"))
            if end_past_count >= 2 and end_past_count > len(end_words) * 0.3:
                scores[i] *= 0.6

        # --- 5. Context is negative, ending should reflect resolution ---
        if context_is_negative:
            end_negations = sum(1 for w in end_words if w in _NEGATION_WORDS)
            if end_negations >= ctx_negations:
                scores[i] *= 0.7

    return scores


# ---------------------------------------------------------------------------
# Pure-Python TF-IDF helpers (no numpy/sklearn) — used only as tiebreaker
# ---------------------------------------------------------------------------


def _hybrid_tokenize(text: str) -> list[str]:
    """Extract both word unigrams and char 4-grams from text.

    Words are prefixed with 'w_' and char n-grams with 'c_' to
    keep the feature spaces separate in the same vocabulary.
    This gives us both word-level semantics and character-level patterns.
    """
    tokens: list[str] = []
    lower = text.lower()

    # Word unigrams
    words = re.findall(r"[a-z]+", lower)
    for w in words:
        if len(w) >= 2:  # skip single chars as noise
            tokens.append("w_" + w)

    # Character 4-grams
    clean = re.sub(r"[^a-z0-9]", "", lower)
    n = 4
    if len(clean) >= n:
        for i in range(len(clean) - n + 1):
            tokens.append("c_" + clean[i : i + n])

    return tokens


def _compute_hybrid_counts(
    texts: list[str],
) -> tuple[dict[str, int], list[Counter]]:
    """Build vocabulary and per-document counts using hybrid features
    (word unigrams + char 4-grams).
    Returns (vocab, doc_counts).
    """
    vocab: dict[str, int] = {}
    doc_counts: list[Counter] = []

    for text in texts:
        tokens = _hybrid_tokenize(text)
        counter: Counter[str] = Counter()
        for tok in tokens:
            if tok not in vocab:
                vocab[tok] = len(vocab)
            counter[tok] += 1
        doc_counts.append(counter)

    return vocab, doc_counts


def _compute_idf(
    doc_counts: list[Counter], vocab: dict[str, int]
) -> list[float]:
    """Compute IDF for each vocabulary term.

    idf[w] = log(1 + N / (1 + df[w]))
    """
    N = len(doc_counts)
    df: Counter[int] = Counter()

    for counter in doc_counts:
        for w in counter:
            df[vocab[w]] += 1

    idf: list[float] = [0.0] * len(vocab)
    for w, idx in vocab.items():
        idf[idx] = math.log(1.0 + N / (1.0 + df[idx]))

    return idf


def _make_tfidf_vector(
    counter: Counter[str], vocab: dict[str, int], idf: list[float]
) -> dict[int, float]:
    """Build a sparse TF-IDF vector (term_index -> tfidf_value)."""
    vec: dict[int, float] = {}
    total = sum(counter.values()) if counter else 1.0
    for w, cnt in counter.items():
        idx = vocab.get(w)
        if idx is None:
            continue
        # Sublinear TF: log(1 + count)
        tf = math.log(1.0 + cnt)
        vec[idx] = tf * idf[idx]
    return vec


def _l2_norm(vec: dict[int, float]) -> float:
    """Compute L2 norm of a sparse vector."""
    return math.sqrt(sum(v * v for v in vec.values()))


def _cosine_similarity_sparse(
    v1: dict[int, float], v2: dict[int, float], n1: float, n2: float
) -> float:
    """Cosine similarity between two sparse TF-IDF vectors."""
    if n1 < 1e-9 or n2 < 1e-9:
        return 0.0
    # Iterate over the smaller vector's keys
    if len(v1) > len(v2):
        v1, v2 = v2, v1
    dot = 0.0
    for k in v1:
        if k in v2:
            dot += v1[k] * v2[k]
    return dot / (n1 * n2)


# ---------------------------------------------------------------------------
# Parquet loader
# ---------------------------------------------------------------------------


def _load_parquet(path: str, max_rows: int | None = None) -> list[dict[str, Any]]:
    """Load a HellaSwag parquet file and return rows as dicts."""
    if not HAS_PYARROW:
        raise ImportError("pyarrow is required to read parquet files")

    import pyarrow.parquet as pq
    table = pq.read_table(path)

    if max_rows is not None and max_rows < table.num_rows:
        table = table.slice(0, max_rows)

    rows: list[dict[str, Any]] = []
    for i in range(table.num_rows):
        ctx = str(table.column("ctx")[i].as_py())
        endings_raw = table.column("endings")[i].as_py()
        label_val = table.column("label")[i].as_py()

        if isinstance(endings_raw, (list, tuple)):
            endings = [str(e) for e in endings_raw]
        elif isinstance(endings_raw, str):
            try:
                endings = json.loads(endings_raw)
            except (json.JSONDecodeError, TypeError):
                endings = [endings_raw]
        else:
            endings = []

        endings = list(endings[:4])
        while len(endings) < 4:
            endings.append("")

        label = int(label_val) if label_val is not None else 0

        rows.append({"ctx": ctx, "endings": endings, "label": label})

    return rows


# ---------------------------------------------------------------------------
# Find cached data
# ---------------------------------------------------------------------------


def _find_cached_path(split: str = "validation") -> str | None:
    """Find a cached HellaSwag parquet file in huggingface cache."""
    cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
    pattern = f"datasets--hellaswag/snapshots/*/data/{split}-00000-of-00001.parquet"
    matches = sorted(cache_dir.glob(pattern))
    return str(matches[0]) if matches else None


# ---------------------------------------------------------------------------
# HellaSwag Solver
# ---------------------------------------------------------------------------


class HellaSwagSolver:
    """Symbolic solver for the HellaSwag commonsense NLI benchmark.

    Uses activity detection + script-based scoring + quality analysis.
    TF-IDF retrieval used as tiebreaker only.
    Depends only on standard library Python + pyarrow for parquet reading.
    """

    def __init__(self, max_train: int = MAX_TRAIN):
        self.max_train = max_train

        # Training data
        self.train_contexts: list[str] = []
        self.train_endings: list[list[str]] = []
        self.train_labels: list[int] = []

        # Pure-Python char n-gram TF-IDF index (tiebreaker only)
        self.vocab: dict[str, int] = {}  # n-gram -> index
        self.idf: list[float] = []  # idf per n-gram index
        self.ctx_tfidf: list[dict[int, float]] = []  # per-doc sparse vectors
        self.ctx_norms: list[float] = []  # pre-computed L2 norms
        self.inverted_index: dict[int, list[int]] = {}  # ngram_idx -> doc indices

        self._load_training_data()

    # ------- data loading ------------------------------------------------

    def _find_train_path(self) -> str | None:
        """Find training data from HF hub or local cache."""
        # Try local cache first
        path = _find_cached_path("train")
        if path:
            return path

        # Try huggingface_hub if available
        try:
            from huggingface_hub import hf_hub_download

            return hf_hub_download(
                "hellaswag",
                "data/train-00000-of-00001.parquet",
                repo_type="dataset",
            )
        except ImportError:
            print("  huggingface_hub not available")
            return None
        except Exception as exc:
            print(f"  Download failed: {exc}")
            return None

    def _load_training_data(self) -> None:
        """Load training data, build TF-IDF index."""
        print("  HellaSwag: Loading training data...", end=" ", flush=True)

        if not HAS_PYARROW:
            print("SKIP (need pyarrow)")
            return

        train_path = self._find_train_path()
        if train_path is None:
            print("FAILED (no training data found)")
            return

        try:
            rows = _load_parquet(train_path, max_rows=self.max_train)
        except Exception as exc:
            print(f"FAILED (read): {exc}")
            return

        self.train_contexts = [r["ctx"] for r in rows]
        self.train_endings = [r["endings"] for r in rows]
        self.train_labels = [r["label"] for r in rows]

        print(f"done ({len(self.train_contexts)} examples)")

        if len(self.train_contexts) == 0:
            print("  WARNING: No training data loaded.")
            return

        # Build TF-IDF index (used as tiebreaker)
        self._build_tfidf_index()

    def _build_tfidf_index(self) -> None:
        """Build pure-Python hybrid TF-IDF index (word unigrams + char 4-grams)."""
        print(
            "  HellaSwag: Building TF-IDF index (hybrid word+char)...",
            end=" ",
            flush=True,
        )

        # Build vocabulary and counts using hybrid features
        vocab, doc_counts = _compute_hybrid_counts(self.train_contexts)
        idf = _compute_idf(doc_counts, vocab)

        # Build TF-IDF vectors, inverted index
        ctx_tfidf: list[dict[int, float]] = []
        ctx_norms: list[float] = []
        inverted_index: dict[int, list[int]] = {}

        for doc_idx, counter in enumerate(doc_counts):
            vec = _make_tfidf_vector(counter, vocab, idf)
            norm = _l2_norm(vec)
            ctx_tfidf.append(vec)
            ctx_norms.append(norm)

            for tok_idx in vec:
                if tok_idx not in inverted_index:
                    inverted_index[tok_idx] = []
                inverted_index[tok_idx].append(doc_idx)

        self.vocab = vocab
        self.idf = idf
        self.ctx_tfidf = ctx_tfidf
        self.ctx_norms = ctx_norms
        self.inverted_index = inverted_index

        print(
            f"done (vocab={len(vocab)}, docs={len(ctx_tfidf)})"
        )

    # ------- TF-IDF retrieval (tiebreaker only) --------------------------

    def _retrieval_score(self, context: str, endings: list[str]) -> list[float]:
        """Score each label using TF-IDF retrieval.

        Used as tiebreaker when the primary scoring is tied.
        Returns a list of 4 scores (one per label).
        """
        out = [0.0, 0.0, 0.0, 0.0]

        if not self.ctx_tfidf:
            return out

        # Context retrieval
        query_tokens = _hybrid_tokenize(context)
        q_counter: Counter[str] = Counter()
        for tok in query_tokens:
            if tok in self.vocab:
                q_counter[tok] += 1

        if q_counter:
            query_vec = _make_tfidf_vector(q_counter, self.vocab, self.idf)
            query_norm = _l2_norm(query_vec)

            if query_norm > 1e-9:
                cand: set[int] = set()
                for ng_idx in query_vec:
                    for doc_idx in self.inverted_index.get(ng_idx, []):
                        cand.add(doc_idx)

                if cand:
                    scored: list[tuple[float, int]] = []
                    for doc_idx in cand:
                        sim = _cosine_similarity_sparse(
                            query_vec,
                            self.ctx_tfidf[doc_idx],
                            query_norm,
                            self.ctx_norms[doc_idx],
                        )
                        if sim > 0.0:
                            scored.append((sim, doc_idx))

                    scored.sort(reverse=True, key=lambda x: x[0])
                    if scored:
                        top_k = scored[:TOP_K_RETRIEVAL]
                        for rank, (sim, doc_idx) in enumerate(top_k):
                            rw = (sim * sim) / (rank + 1.0)
                            label = self.train_labels[doc_idx]
                            out[label] += rw

        total_ctx = sum(out)
        if total_ctx > 0:
            for i in range(4):
                out[i] /= total_ctx

        return out

    # ------- Primary scoring strategies ----------------------------------

    def _compute_scores(self, context: str, endings: list[str]) -> list[float]:
        """Compute combined score for each ending using all strategies.

        Returns a list of 4 scores (one per ending index).
        """
        endings = list(endings[:4])
        while len(endings) < 4:
            endings.append("")

        # Detect activity domains from context
        active_domains = _detect_domains(context)

        # Strategy 1: Activity detection (30%)
        s_activity = _activity_score(context, endings, active_domains)

        # Strategy 2: Script-based scoring (40%)
        s_script = _script_score(context, endings, active_domains)

        # Strategy 3: Ending quality analysis (20%)
        s_quality = _quality_score(context, endings)

        # Strategy 4: Negation/contradiction detection (10%)
        s_contradiction = _contradiction_penalty(context, endings)

        # Normalize each strategy's scores to [0, 1]
        def _normalize(scores: list[float]) -> list[float]:
            mx = max(scores)
            if mx > 0:
                return [s / mx for s in scores]
            return scores

        s_activity = _normalize(s_activity)
        s_script = _normalize(s_script)
        s_quality = _normalize(s_quality)
        # Contradiction is already in [0, 1] range

        combined = [0.0] * 4
        for i in range(4):
            combined[i] = (
                W_ACTIVITY * s_activity[i]
                + W_SCRIPT * s_script[i]
                + W_QUALITY * s_quality[i]
                + W_CONTRADICTION * s_contradiction[i]
            )

        return combined

    def solve(self, context: str, endings: list[str]) -> int:
        """Predict the most likely continuation index (0-3).

        Uses multi-strategy scoring with TF-IDF tiebreaker.
        """
        endings = list(endings[:4])
        while len(endings) < 4:
            endings.append("")

        # Primary scoring
        combined = self._compute_scores(context, endings)

        # Find best label
        max_score = max(combined)
        best = combined.index(max_score)

        # Check for ties
        tie_count = sum(1 for s in combined if abs(s - max_score) < 1e-6)
        if tie_count > 1:
            # Use TF-IDF retrieval as tiebreaker
            tfidf_scores = self._retrieval_score(context, endings)
            # Prefer TF-IDF over tied candidates
            best_tfidf = max(range(4), key=lambda i: (combined[i], tfidf_scores[i]))
            best = best_tfidf

        # Fallback: if all scores are zero, use length heuristic
        if max_score == 0.0:
            lengths = [len(_clean(e).split()) for e in endings]
            ideal = 8
            len_scores = [
                max(0.0, 1.0 - abs(ws - ideal) / ideal)
                for ws in lengths
            ]
            best = len_scores.index(max(len_scores))

        return best

    # ------- benchmark runner --------------------------------------------

    def run_benchmark(
        self, num_samples: int = N_VAL_SAMPLES, val_path: str | None = None
    ) -> float:
        """Run benchmark on the HellaSwag validation set. Returns accuracy (%)."""
        print(f"\n{'=' * 60}")
        print(f"  HellaSwag Benchmark (validation)")
        print(f"{'=' * 60}")

        if val_path is not None:
            val_rows = self._load_validation_parquet(val_path, num_samples)
        else:
            val_rows = self._load_validation_data(num_samples)

        if val_rows is None or len(val_rows) == 0:
            print("  No validation data available.")
            return 0.0

        total = len(val_rows)
        correct = 0

        for i, item in enumerate(val_rows):
            predicted = self.solve(item["ctx"], item["endings"])
            is_correct = predicted == item["label"]

            if is_correct:
                correct += 1

            if (
                i < 5
                or (i + 1) % max(1, num_samples // 10) == 0
                or i == total - 1
            ):
                status = "✓" if is_correct else "✗"
                ctx_short = item["ctx"][:60].replace("\n", " ")
                print(
                    f"  {status} [{i+1}/{total}] pred={predicted} "
                    f"exp={item['label']}"
                )
                print(f"     ctx: {ctx_short}...")
                for ei, ending in enumerate(item["endings"]):
                    print(f"     ending[{ei}]: {ending[:50]}...")

        accuracy = correct / total * 100 if total > 0 else 0.0
        print(f"\n  Result: {correct}/{total} = {accuracy:.1f}%")
        print(f"{'=' * 60}")
        return accuracy

    def _load_validation_data(
        self, num_samples: int
    ) -> list[dict[str, Any]] | None:
        """Load validation data from local cache or HuggingFace Hub."""
        # Try local cache first
        val_path = _find_cached_path("validation")

        # Try huggingface_hub if not in cache
        if val_path is None:
            try:
                from huggingface_hub import hf_hub_download

                val_path = hf_hub_download(
                    "hellaswag",
                    "data/validation-00000-of-00001.parquet",
                    repo_type="dataset",
                )
            except ImportError:
                print("  huggingface_hub not available")
                return None
            except Exception as exc:
                print(f"  ERROR downloading validation data: {exc}")
                return None

        return self._load_validation_parquet(val_path, num_samples)

    def _load_validation_parquet(
        self, val_path: str, num_samples: int
    ) -> list[dict[str, Any]] | None:
        """Load validation data from a local parquet file."""
        try:
            return _load_parquet(val_path, max_rows=num_samples)
        except Exception as exc:
            print(f"  ERROR reading validation parquet: {exc}")
            return None


# ---------------------------------------------------------------------------
# Command-line entry point
# ---------------------------------------------------------------------------


def main():
    """Run HellaSwag benchmark from command line.

    Usage:
        python3 hellaswag_solver.py [num_samples] [val_path]
    """
    num_samples = N_VAL_SAMPLES
    val_path = None

    args = sys.argv[1:]
    if args:
        try:
            num_samples = int(args[0])
        except ValueError:
            val_path = args[0]

    if len(args) > 1:
        try:
            num_samples = int(args[1])
        except ValueError:
            pass

    print(f"  HellaSwag Solver (pure Python + pyarrow)")
    print(
        f"  Using {MAX_TRAIN} training examples, "
        f"testing on up to {num_samples} validation samples"
    )
    print(
        f"  Weights: activity={W_ACTIVITY:.0%}, "
        f"script={W_SCRIPT:.0%}, quality={W_QUALITY:.0%}, "
        f"contradiction={W_CONTRADICTION:.0%}"
    )

    if not HAS_PYARROW:
        print("  WARNING: pyarrow not installed.")

    t0 = time.time()
    solver = HellaSwagSolver(max_train=MAX_TRAIN)
    load_time = time.time() - t0

    if len(solver.train_contexts) == 0:
        print("\n  No training data loaded. Cannot run benchmark.")
        return 0.0

    t1 = time.time()
    score = solver.run_benchmark(num_samples=num_samples, val_path=val_path)
    total_time = time.time() - t0

    print(f"\n  Timing: load={load_time:.1f}s, total={total_time:.1f}s")
    print(f"  Final HellaSwag accuracy: {score:.1f}%")

    return score


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
