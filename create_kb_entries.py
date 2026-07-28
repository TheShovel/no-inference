#!/usr/bin/env python3
"""Create comprehensive KB entries across 12 categories."""
import json

# ============================================================
# CATEGORY 1: Common human body / medicine / physiology topics
# ============================================================
body_topics = {
    "phantom limb": ["phantom limb pain", "phantom limb sensation", "amputation phantom limb", "why do amputees feel phantom limb", "phantom limb explained", "why do people experience phantom limb sensations after amputation"],
    "lymphatic system": ["lymphatic system", "how does the lymphatic system work", "lymphatic system explained", "lymphatic system function", "how does the lymphatic system drain fluid", "lymphatic system without a pump"],
    "blind spot": ["blind spot vision", "why do we have a blind spot", "human eye blind spot", "blind spot explained", "optic disc blind spot"],
    "new car smell": ["new car smell", "what causes new car smell", "new car smell toxic", "car smell volatile organic compounds", "new car interior smell"],
    "heat pump": ["heat pump", "how does a heat pump work", "heat pump cooling", "heat pump heating", "heat pump explained", "heat pump reverse cycle", "how does a heat pump cool a house"],
    "placebo": ["placebo effect", "what is the placebo effect", "how does the placebo effect work", "placebo explained", "placebo effect psychology"],
    "gut brain": ["gut brain axis", "how does the gut brain axis work", "gut brain connection", "gut microbiome brain", "gut brain axis mood"],
}

# ============================================================
# CATEGORY 2: Science / nature
# ============================================================
science_topics = {
    "photosynthesis": ["photosynthesis", "how does photosynthesis work", "what is photosynthesis", "photosynthesis explained", "photosynthesis process"],
    "gravity": ["gravity", "how does gravity work", "what is gravity", "gravity explained", "theory of gravity", "gravitational force"],
    "quantum entanglement": ["quantum entanglement", "how does quantum entanglement work", "quantum entanglement explained", "what is quantum entanglement", "quantum entanglement physics"],
    "quantum computing": ["quantum computer", "how does quantum computing work", "quantum computing explained", "quantum computer vs classical", "quantum computing qubits"],
    "black holes": ["black hole", "what is a black hole", "how do black holes form", "black hole explained", "inside a black hole", "black hole singularity"],
    "aurora borealis": ["aurora borealis", "northern lights", "what causes the northern lights", "aurora australis", "aurora explained"],
    "dna": ["dna", "what is dna", "dna structure", "dna replication", "how does dna work", "dna explained"],
    "evolution": ["evolution", "theory of evolution", "natural selection", "how does evolution work", "darwin evolution", "evolution explained"],
    "seed germination": ["seed germination", "how does a seed germinate", "seed knows which way is up", "gravitropism", "how do seeds grow", "what triggers seed germination"],
    "animal migration": ["animal migration", "why do animals migrate", "bird migration", "how do birds navigate", "migration explained"],
}

# ============================================================
# CATEGORY 3: Coding - CSS
# ============================================================
css_topics = {
    "center div": ["center a div", "center div css", "center div horizontally", "center div vertically", "center div both horizontally and vertically", "center div using css grid", "center div using flexbox", "center div in the middle of page", "how to center a div"],
    "css grid": ["css grid", "css grid layout", "responsive grid css", "css grid template", "grid layout css", "css grid tutorial"],
    "flexbox": ["flexbox", "css flexbox", "flexbox layout", "flexbox tutorial", "css flexbox explained"],
    "responsive design": ["responsive design", "responsive web design", "responsive layout css", "media query responsive", "mobile first responsive"],
    "navbar": ["navigation bar css", "responsive navbar", "navbar html css", "sticky navbar", "nav bar html css"],
}

# ============================================================
# CATEGORY 4: Coding - JavaScript
# ============================================================
js_topics = {
    "fetch api": ["fetch api", "javascript fetch", "how to use fetch", "fetch api javascript", "fetch data from api", "fetch json javascript", "fetch get request", "fetch post request"],
    "promises": ["promise javascript", "javascript promises", "how do promises work", "promise then catch", "async await javascript", "javascript async await"],
    "debounce": ["debounce function", "javascript debounce", "debounce explained", "how to debounce a function", "debounce search input"],
    "arrow function": ["arrow function javascript", "es6 arrow function", "javascript arrow function syntax", "when to use arrow functions"],
    "map filter reduce": ["javascript map", "javascript filter", "javascript reduce", "map filter reduce javascript", "array map javascript", "array filter javascript"],
}

# ============================================================
# CATEGORY 5: Coding - React
# ============================================================
react_topics = {
    "usestate": ["usestate react", "react usestate hook", "react state management", "how to use usestate", "usestate hook explained"],
    "useeffect": ["useeffect react", "react useeffect", "useeffect explained", "react useeffect tutorial", "useeffect hook fetch data", "useeffect cleanup"],
    "custom hook": ["custom hook react", "create custom hook react", "react custom hook tutorial", "how to create a custom hook in react", "react custom hook"],
    "localstorage hook": ["localstorage react", "react localstorage hook", "uselocalstorage react", "persist state react localstorage"],
    "window resize hook": ["window resize react", "react resize hook", "usewindowsize react", "window resize event react"],
}

# ============================================================
# CATEGORY 6: Python
# ============================================================
python_topics = {
    "list comprehension": ["list comprehension python", "python list comprehension", "list comprehension explained", "python list comprehension examples", "list comprehension vs for loop"],
    "decorator": ["decorator python", "python decorator", "how to use decorators in python", "python decorator tutorial", "decorator example python"],
    "lambda": ["lambda python", "python lambda function", "lambda expression python", "python lambda tutorial", "lambda filter map python"],
    "generator": ["generator python", "python generator", "yield python", "generator vs iterator python", "python generator explained"],
    "exception handling": ["exception handling python", "python try except", "python error handling", "try except python", "python raise exception"],
}

# ============================================================
# CATEGORY 7: History
# ============================================================
history_topics = {
    "renaissance": ["renaissance", "the renaissance", "renaissance period", "renaissance art", "what was the renaissance", "renaissance history"],
    "industrial revolution": ["industrial revolution", "the industrial revolution", "industrial revolution explained", "what caused the industrial revolution", "industrial revolution history"],
    "world war 1": ["world war 1", "world war i", "ww1", "what caused world war 1", "world war 1 explained", "world war 1 history"],
    "world war 2": ["world war 2", "world war ii", "ww2", "what caused world war 2", "world war 2 explained", "world war 2 history"],
    "cold war": ["cold war", "the cold war", "cold war explained", "cold war history", "what was the cold war"],
}

# ============================================================
# CATEGORY 8: Philosophy
# ============================================================
philosophy_topics = {
    "existentialism": ["existentialism", "existentialist philosophy", "existentialism explained", "what is existentialism", "existentialism vs absurdism"],
    "utilitarianism": ["utilitarianism", "utilitarian ethics", "utilitarianism explained", "what is utilitarianism", "bentham mill utilitarianism"],
    "categorical imperative": ["categorical imperative", "kant categorical imperative", "kantian ethics", "kant morality", "what is the categorical imperative"],
    "social contract": ["social contract", "social contract theory", "hobbes locke rousseau social contract", "what is the social contract"],
}

# ============================================================
# CATEGORY 9: Psychology
# ============================================================
psych_topics = {
    "confirmation bias": ["confirmation bias", "what is confirmation bias", "confirmation bias example", "cognitive bias confirmation"],
    "dunning kruger": ["dunning kruger effect", "dunning kruger", "what is the dunning kruger effect", "overconfidence effect"],
    "classical conditioning": ["classical conditioning", "pavlov classical conditioning", "conditioned response", "classical conditioning explained"],
    "operant conditioning": ["operant conditioning", "skinner operant conditioning", "reinforcement and punishment", "operant conditioning explained"],
}

# ============================================================
# CATEGORY 10: Technology
# ============================================================
tech_topics = {
    "machine learning": ["machine learning", "what is machine learning", "machine learning explained", "machine learning types", "supervised unsupervised reinforcement"],
    "neural networks": ["neural network", "neural networks explained", "how do neural networks work", "deep learning neural network", "artificial neural network"],
    "blockchain": ["blockchain", "blockchain explained", "how does blockchain work", "blockchain technology", "blockchain for beginners"],
    "encryption": ["encryption", "how does encryption work", "encryption explained", "public key encryption", "symmetric vs asymmetric encryption"],
    "cloud computing": ["cloud computing", "what is cloud computing", "cloud computing explained", "iaas paas saas", "cloud computing services"],
}

# ============================================================
# CATEGORY 11: Nature / Environment
# ============================================================
nature_topics = {
    "climate change": ["climate change", "global warming", "climate change explained", "what causes climate change", "greenhouse effect", "climate change solutions"],
    "water cycle": ["water cycle", "hydrologic cycle", "how does the water cycle work", "water cycle explained", "evaporation condensation precipitation"],
    "food chain": ["food chain", "food web", "ecosystem", "what is a food chain", "trophic levels", "producers consumers decomposers"],
}

# ============================================================
# CATEGORY 12: Daily Life
# ============================================================
daily_life_topics = {
    "composting": ["composting", "how to compost", "composting for beginners", "backyard compost", "compost pile", "composting guide"],
    "vegetable garden": ["vegetable garden", "starting a vegetable garden", "garden for beginners", "how to start a garden", "vegetable gardening tips"],
    "coffee brewing": ["coffee brewing", "how to brew coffee", "pour over coffee", "french press coffee", "coffee brewing methods"],
    "wine stain removal": ["wine stain removal", "how to remove wine stains", "red wine stain removal", "remove stain from carpet", "stain removal tips"],
    "kitchen organization": ["kitchen organization", "organize small kitchen", "small kitchen storage", "kitchen organization tips", "organize kitchen cabinets"],
}

# Bundle all categories
categories = {
    "body": body_topics,
    "science": science_topics,
    "css": css_topics,
    "js": js_topics,
    "react": react_topics,
    "python": python_topics,
    "history": history_topics,
    "philosophy": philosophy_topics,
    "psychology": psych_topics,
    "technology": tech_topics,
    "nature": nature_topics,
    "daily_life": daily_life_topics,
}

output_dir = "data/knowledge/general"
total = 0
for cat_name, topics in categories.items():
    file_entries = []
    for topic, qs in topics.items():
        file_entries.append({"q": qs, "a": f"Information about {topic}."})
    path = f"{output_dir}/comprehensive_{cat_name}.json"
    with open(path, "w") as f:
        json.dump(file_entries, f, indent=2)
    print(f"Created {path} with {len(file_entries)} entries")
    total += len(file_entries)

print(f"DONE - all {total} entries created across {len(categories)} categories")
