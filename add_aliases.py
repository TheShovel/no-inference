#!/usr/bin/env python3
"""Add new aliases to data/aliases.json."""
import json

aliases = json.load(open("data/aliases.json"))

new_aliases = {
    "phantom limb": "Phantom limb",
    "lymphatic system": "Lymphatic system",
    "blind spot": "Blind spot (vision)",
    "new car smell": "Volatile organic compound",
    "heat pump": "Heat pump",
    "dna": "DNA",
    "evolution": "Evolution",
    "renaissance": "Renaissance",
    "world war 1": "World War I",
    "world war 2": "World War II",
    "cold war": "Cold War",
    "machine learning": "Machine learning",
    "neural network": "Neural network",
    "climate change": "Climate change",
    "water cycle": "Water cycle",
    "food chain": "Food chain",
    "classical conditioning": "Classical conditioning",
    "operant conditioning": "Operant conditioning",
    "confirmation bias": "Confirmation bias",
    "dunning kruger": "Dunning-Kruger effect",
    "existentialism": "Existentialism",
    "utilitarianism": "Utilitarianism",
    "social contract": "Social contract",
    "categorical imperative": "Categorical imperative",
    "kantian ethics": "Immanuel Kant",
    "cloud computing": "Cloud computing",
    "encryption": "Encryption",
    "css grid": "CSS Grid",
    "flexbox": "CSS Flexible Box Layout",
    "arrow function": "Arrow function",
    "map filter reduce": "Array methods",
    "custom hook": "React (JavaScript library)",
    "useeffect": "React (JavaScript library)",
    "usestate": "React (JavaScript library)",
}

added = 0
for k, v in new_aliases.items():
    if k not in aliases:
        aliases[k] = v
        added += 1

json.dump(aliases, open("data/aliases.json", "w"), indent=2)
print(f"Added {added} new aliases. Total aliases: {len(aliases)}")
