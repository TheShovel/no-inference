#!/usr/bin/env python3
"""Regression battery for the no-inference engine.

Each case is (query, [required_substrings], [forbidden_substrings]).
A case passes when the response contains every required substring
(case-insensitive) and none of the forbidden substrings.

This battery is the gold-standard check for question-format coverage.
Whenever a new wrapper, slang term, comparison pattern, or edge case is
added, add cases here and keep the whole battery green.

Run with:  python3 tests/test_regression.py
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
import cos.engine as engine
from cos.engine import process_query, reset_conversation

# By default the battery runs fully offline: Wikipedia is unreachable in CI
# sandboxes, and the battery tests the symbolic matching/composition logic, not
# the live network. Pass --live to enable real Wikipedia fallbacks.
parser = argparse.ArgumentParser()
parser.add_argument('--live', action='store_true', help='enable live Wikipedia fallback')
ARGS = parser.parse_args()
if not ARGS.live:
    engine._search_wikipedia = lambda query: (None, None)
    engine._search_wikipedia_full = lambda query: (None, None)
    # cos.nlg.fallback makes its OWN direct urllib calls to Wikipedia (5-8s
    # timeouts, three attempts per query) — patch it or the battery hangs.
    import cos.nlg.fallback as _nlg_fallback
    _nlg_fallback.fallback_response = (
        lambda query, config: "I do not have enough specific information about that topic to give you a thorough answer. Could you ask a more specific question or try a different topic?")

# Generic fallback/refusal phrases that indicate the engine failed to answer
FALLBACK_PHRASES = [
    "i'm not sure about that. could you rephrase",
    "i could not find enough information",
    "i'm not sure i have any information",
    "i have no information about that",
    "i don't know.",
    "i do not know.",
    "i do not have enough specific information",
    "information about placeholder",
]

# ── Core factual forms ────────────────────────────────────────────────────────
CORE = [
    ("what is a cat", ["cat"]),
    ("what is the capital of france", ["paris"]),
    ("what is the capital of japan", ["tokyo"]),
    ("define photosynthesis", ["photosynthesis"]),
    ("define the term photosynthesis", ["photosynthesis"]),
    ("who is albert einstein", ["einstein"]),
    ("who was marie curie", ["curie"]),
    ("how does a car engine work", ["engine"]),
    ("how do airplanes fly", ["wing", "lift"]),
    ("what is a dog", ["dog"]),
    ("what is tea", ["tea"]),
    ("what is coffee", ["coffee"]),
    ("what is jazz", ["jazz"]),
    ("what is stoicism", ["stoicism"]),
    ("what is the internet", ["internet"]),
    ("what is the great wall of china", ["great wall"]),
    ("who wrote romeo and juliet", ["shakespeare"]),
]

# ── Wrapper / phrasing forms ──────────────────────────────────────────────────
WRAPPERS = [
    ("do you know what a cat is", ["cat"]),
    ("do you know what the capital of france is", ["paris"]),
    ("i'm curious about black holes", ["black hole"]),
    ("i am curious about the great pyramid", ["pyramid"]),
    ("whats the deal with the moon", ["moon"]),
    ("what's the deal with quantum computing", ["quantum"]),
    ("explain gravity like i'm five", ["gravity"]),
    ("explain the water cycle like i'm five", ["water"]),
    ("explain how rainbows form", ["rainbow"]),
    ("what should i know about bees", ["bee"]),
    ("what information do you have on elephants", ["elephant"]),
    ("what do you have on penguins", ["penguin"]),
    ("what can you say about volcanoes", ["volcano"]),
    ("spill the beans about the titanic", ["titanic"]),
    ("the history of the roman empire", ["roman"]),
    ("the origins of jazz", ["jazz"]),
    ("the importance of sleep", ["sleep"]),
    ("the future of artificial intelligence", ["artificial intelligence"]),
    ("the theme of 1984", ["1984"]),
    ("the plot of hamlet", ["hamlet"]),
    ("the message of the great gatsby", ["gatsby"]),
    ("the setting of the great gatsby", ["gatsby"]),
    ("who invented the telephone", ["telephone"]),
    ("who discovered penicillin", ["penicillin"]),
    ("who discovered gravity", ["gravity"]),
    ("when was the roman empire founded", ["roman"]),
    ("when did world war 2 start", ["world war"]),
    ("in what year did world war 2 end", ["world war"]),
    ("what year was the internet invented", ["internet"]),
    ("how old is the earth", ["earth", "billion"]),
    ("how big is the sun", ["sun"]),
    ("how tall is mount everest", ["everest"]),
    ("how fast is a cheetah", ["cheetah"]),
    ("how far is the moon from earth", ["moon"]),
    ("how many legs does a spider have", ["eight"]),
    ("how much does an elephant weigh", ["elephant"]),
    ("is a tomato a fruit", ["fruit"]),
    ("is the earth flat", ["flat", "sphere"]),
    ("is fire a thing", ["fire"]),
    ("what does chocolate taste like", ["chocolate"]),
    ("what does a banana taste like", ["banana"]),
    ("what family does the lion belong to", ["felidae"]),
    ("what does the rose symbolize", ["rose"]),
    ("what does the peace sign stand for", ["peace"]),
    ("what is the biggest animal in the world", ["whale"]),
    ("what is the fastest land animal", ["cheetah"]),
    ("what is the tallest mountain", ["everest"]),
    ("why is it called the pacific ocean", ["pacific"]),
    ("what is the population of china", ["china", "billion"]),
    ("what is the currency of japan", ["yen"]),
    ("what is the climate of the sahara", ["sahara"]),
    ("what is the language of brazil", ["portuguese"]),
    ("what is the religion of india", ["hindu"]),
    ("can you eat mushrooms", ["mushroom"]),
    ("what are the parts of a flower", ["flower"]),
    ("what are the risks of smoking", ["smok"]),
    ("what are the side effects of caffeine", ["caffeine"]),
    ("what are the advantages of solar power", ["solar"]),
    ("what are the disadvantages of nuclear energy", ["nuclear"]),
    ("how is olive oil extracted", ["olive"]),
    ("how is chocolate made", ["chocolate"]),
    ("how is beer brewed", ["beer"]),
    ("how is cheese fermented", ["cheese"]),
    ("what is the average lifespan of a dog", ["dog"]),
    ("what is the average height of a giraffe", ["giraffe"]),
    ("what is the average weight of an elephant", ["elephant"]),
    ("how many tigers are left in the world", ["tiger"]),
    ("who is the main character of hamlet", ["hamlet"]),
    ("who is the villain of star wars", ["star wars"]),
    ("what happens at the end of romeo and juliet", ["romeo"]),
    ("where is the great gatsby set", ["gatsby"]),
    ("when is the great gatsby set", ["gatsby"]),
    ("why did the roman empire fall", ["roman"]),
    ("why did the soviet union collapse", ["soviet"]),
    ("what came after the roman empire", ["rome"]),
    ("how many people live in china", ["china"]),
    ("how many people speak english", ["english"]),
    ("how many people use the internet", ["internet"]),
    ("who is the president of the united states", ["president"]),
    ("who is the ceo of tesla", ["musk"]),
    ("what is the difference between a frog and a toad", ["frog", "toad"]),
]

# ── Slang / informal normalization ────────────────────────────────────────────
SLANG = [
    ("wat is a cat", ["cat"]),
    ("wat r u", []),
    ("idk what a cat is", ["cat"]),
    ("im gonna ask about dogs", ["dog"]),
    ("i dont know what jazz is", ["jazz"]),
    ("whaddya know about coffee", ["coffee"]),
    ("whatchu know about tea", ["tea"]),
    ("fr what is a cat", ["cat"]),
    ("ngl what is a dog", ["dog"]),
    ("100% what is coffee", ["coffee"]),
    ("wuts the capital of france", ["paris"]),
    ("wats the capital of japan", ["tokyo"]),
    ("gimme info on cats", ["cat"]),
    ("tell me bout the moon", ["moon"]),
    ("yo what is jazz", ["jazz"]),
    ("hey what is the internet", ["internet"]),
]

# ── Multi-entity / category composition ───────────────────────────────────────
CATEGORIES = [
    ("what types of cats are there", ["lion", "tiger"]),
    ("what kinds of cats are there", ["lion", "tiger"]),
    ("what breeds of dogs exist", ["dog"]),
    ("what species of birds are there", ["bird"]),
    ("what types of bears are there", ["bear"]),
    ("what kinds of snakes exist", ["snake"]),
    ("what types of sharks are there", ["shark"]),
    ("what kinds of whales exist", ["whale"]),
    ("list all the planets", ["mercury", "mars"]),
    ("list all the continents", ["asia", "europe"]),
    ("name some birds", ["bird"]),
    ("name some flowers", ["flower"]),
    ("what types of trees are there", ["tree"]),
    ("what types of cheese are there", ["cheese"]),
    ("what types of tea exist", ["tea"]),
    ("what kinds of coffee exist", ["coffee"]),
    ("what types of dogs are there", ["dog"]),
    ("what types of fish are there", ["fish"]),
    ("what types of insects are there", ["insect"]),
    ("what types of pasta are there", ["pasta"]),
    ("what types of music exist", ["music"]),
    ("what types of dance are there", ["dance"]),
    ("what types of sports exist", ["sport"]),
    ("what types of fruit are there", ["fruit"]),
    ("what types of vegetables exist", ["vegetable"]),
    ("what types of mushrooms are there", ["mushroom"]),
    ("what types of clouds exist", ["cloud"]),
    ("what types of rocks are there", ["rock"]),
    ("what types of storms are there", ["storm"]),
    ("what types of weapons exist", ["weapon"]),
    ("what types of swords are there", ["sword"]),
    ("what types of dinosaurs exist", ["dinosaur"]),
    ("what types of dragons are there", ["dragon"]),
    ("what types of mythical creatures exist", ["creature"]),
]

# ── Multi-point / comparison composition ──────────────────────────────────────
COMPARISONS = [
    ("compare cats and dogs", ["cat", "dog"]),
    ("compare coffee and tea", ["coffee", "tea"]),
    ("compare jazz and blues", ["jazz", "blues"]),
    ("compare rome and greece", ["rome", "greece"]),
    ("contrast cats and dogs", ["cat", "dog"]),
    ("how does coffee compare to tea", ["coffee", "tea"]),
    ("how do cats compare with dogs", ["cat", "dog"]),
    ("cats vs dogs", ["cat", "dog"]),
    ("coffee vs tea", ["coffee", "tea"]),
    ("jazz versus blues", ["jazz", "blues"]),
    ("what is the difference between cats and dogs", ["cat", "dog"]),
    ("what's the difference between coffee and tea", ["coffee", "tea"]),
    ("difference between jazz and blues", ["jazz", "blues"]),
    ("differences between cats and dogs", ["cat", "dog"]),
    ("similarities between jazz and blues", ["jazz", "blues"]),
    ("tell me the difference between cats and dogs", ["cat", "dog"]),
    ("tell me the similarities between jazz and blues", ["jazz", "blues"]),
    ("is a cat the same as a dog", ["cat", "dog"]),
    ("are cats and dogs the same", ["cat", "dog"]),
    ("what is the relationship between cats and dogs", ["cat", "dog"]),
    ("how are cats and dogs related", ["cat", "dog"]),
    ("what's the relationship between coffee and tea", ["coffee", "tea"]),
    ("is a cheetah faster than a lion", ["cheetah", "lion"]),
    ("are elephants bigger than rhinos", ["elephant", "rhino"]),
    ("how do cats and dogs differ", ["cat", "dog"]),
    ("how are cats and dogs different", ["cat", "dog"]),
    ("how are green tea and black tea similar", ["green tea", "black tea"]),
    ("what do cats and dogs have in common", ["cat", "dog"]),
    ("how is coffee different from tea", ["coffee", "tea"]),
    ("how does coffee differ from tea", ["coffee", "tea"]),
    ("how does jazz differ from blues", ["jazz", "blues"]),
    ("how is tea different from coffee", ["tea", "coffee"]),
    ("what is the difference between a frog and a toad", ["frog", "toad"]),
    ("how are apples and oranges similar", ["apple", "orange"]),
    ("what do lions and tigers have in common", ["lion", "tiger"]),
    ("how does a phone compare with a computer", ["phone", "computer"]),
    # compound factual questions (two questions joined by "and")
    ("what is the capital of france and the capital of spain", ["Paris", "Madrid"]),
    ("who wrote hamlet and who painted the mona lisa", ["Shakespeare", "Leonardo"]),
    ("what is the largest ocean and the smallest ocean", ["Pacific", "Arctic"]),
    ("what is the tallest mountain in africa and in europe", ["Kilimanjaro", "Elbrus"]),
    ("name a famous river in egypt and a famous river in india", ["Nile", "Ganges"]),
    ("what is the national animal of australia and of scotland", ["kangaroo", "unicorn"]),
    ("how many legs does a spider have and how many legs does an insect have", ["eight", "six"]),
    ("what currency is used in japan and in the united kingdom", ["yen", "pound"]),
    ("what are the main languages spoken in canada and in belgium", ["English", "French", "Dutch"]),
    # single-fact additions backing the compound halves
    ("what is the tallest mountain in africa", ["Kilimanjaro"]),
    ("what is the smallest ocean", ["Arctic"]),
    ("what is the national animal of australia", ["kangaroo"]),
    ("what is the national animal of scotland", ["unicorn"]),
    ("what currency is used in the united kingdom", ["pound"]),
    ("name a famous river in india", ["Ganges"]),
    ("how many legs does an insect have", ["six"]),
    # more compound forms
    ("what is the capital of france and spain", ["Paris", "Madrid"]),
    ("what is the capital of france or spain", ["Paris", "Madrid"]),
    ("what is a cat and a dog", ["cat", "dog"]),
    ("what are the capitals of france and italy", ["Paris", "Rome"]),
    ("what is the capital of france, what is the capital of spain, and what is the capital of italy", ["Paris", "Madrid", "Rome"]),
    # "or" comparisons
    ("which is bigger, an elephant or a rhino", ["elephant", "rhino"]),
    ("is an elephant or a rhino bigger", ["elephant", "rhino"]),
    ("which is taller, the eiffel tower or the statue of liberty", ["eiffel tower", "statue of liberty"]),
    ("is a cheetah or a lion faster", ["cheetah", "lion"]),
    ("which is larger, the pacific or the atlantic", ["pacific", "atlantic"]),
    # ocean data
    ("what is the largest country and the smallest country", ["Russia", "Vatican"]),
    ("what is the smallest country", ["Vatican"]),
    ("tell me about the pacific ocean", ["Pacific"]),
    ("which country has the most time zones", ["France"]),
    # superlatives
    ("what is the tallest building", ["Burj Khalifa"]),
    ("what is the longest river", ["Nile"]),
    ("what is the highest waterfall", ["Angel Falls"]),
    ("how many countries are in europe", ["Europe"]),
    ("what is the most spoken language", ["English", "Mandarin"]),
    ("what is the largest desert", ["Antarctic", "Sahara"]),
    ("what is the largest island", ["Greenland"]),
    ("what is the largest lake", ["Caspian"]),
    ("what is the largest city", ["Tokyo"]),
    # counts and body facts
    ("how many bones does an adult human have", ["206"]),
    ("how many teeth does an adult human have", ["32"]),
    ("how many chromosomes do humans have", ["46"]),
    ("how many senses do humans have", ["five"]),
    ("how many moons does mars have", ["two"]),
    ("how many moons does jupiter have", ["95"]),
    ("how many moons does mercury have", ["no moons"]),
    ("how many moons does jupiter have and how many moons does saturn have", ["95", "146"]),
    ("what is the tallest animal", ["giraffe"]),
    ("what is the largest continent", ["Asia"]),
    ("what is the smallest continent", ["Australia"]),
    ("how many countries are in the world", ["195"]),
    # records
    ("what is the fastest bird", ["peregrine"]),
    ("what is the largest mammal", ["blue whale"]),
    ("what is the most expensive painting", ["Salvator Mundi"]),
    ("what is the longest bridge", ["Danyang"]),
    ("what is the largest empire in history", ["British"]),
    ("who is the fastest man", ["Usain Bolt"]),
    ("what is the oldest living thing", ["bristlecone"]),
    ("what is the strongest animal", ["dung beetle", "elephant"]),
    ("what is the largest bird", ["ostrich"]),
    ("what is the largest land animal", ["African bush elephant"]),
    ("what is the largest fish", ["whale shark"]),
]

# ── Process / mechanism / science ─────────────────────────────────────────────
SCIENCE = [
    ("why is the sky blue", ["scatter", "blue"]),
    ("how are fossils formed", ["fossil"]),
    ("how is a rainbow formed", ["rainbow"]),
    ("how does photosynthesis work", ["photosynthesis"]),
    ("how does gravity work", ["gravity"]),
    ("why do cats purr", ["cat"]),
    ("why do we dream", ["dream"]),
    ("why do we hiccup", ["hiccup"]),
    ("why do leaves change color", ["leaves"]),
    ("why is the ocean salty", ["salt"]),
    ("how do birds fly", ["bird"]),
    ("how do bees make honey", ["bee"]),
    ("how are mountains formed", ["mountain"]),
    ("how do hurricanes form", ["hurricane"]),
    ("how do volcanoes erupt", ["volcano"]),
    ("why does the sun shine", ["sun"]),
    ("what causes earthquakes", ["earthquake"]),
    ("what causes the seasons", ["season"]),
    ("how does the heart work", ["heart"]),
    ("how do vaccines work", ["vaccine"]),
    ("what is a black hole", ["black hole"]),
    ("what is dna", ["dna"]),
    ("what is the periodic table", ["periodic"]),
    ("why is water wet", ["water"]),
    ("why does ice float", ["ice"]),
    ("how do submarines dive", ["submarine"]),
    ("how do glow sticks work", ["glow"]),
    ("why do onions make you cry", ["onion"]),
    ("why do we yawn", ["yawn"]),
    ("how do magnets work", ["magnet"]),
    ("what is electricity", ["electric"]),
    ("how does wifi work", ["wireless", "radio"]),
    ("how does bluetooth work", ["bluetooth"]),
    ("how do solar panels work", ["solar"]),
    ("how do batteries work", ["battery"]),
    ("why is the sky blue and not green", ["sky"]),
]

# ── Geography / people / culture ──────────────────────────────────────────────
GEO_CULTURE = [
    ("what is the longest river in the world", ["river"]),
    ("what is the largest desert", ["desert"]),
    ("what is the smallest country in the world", ["country"]),
    ("what is the most populous country", ["country"]),
    ("how many countries are in the world", ["country"]),
    ("what is the capital of australia", ["canberra"]),
    ("what is the capital of canada", ["ottawa"]),
    ("what is the capital of egypt", ["cairo"]),
    ("what is the capital of germany", ["berlin"]),
    ("what is the capital of italy", ["rome"]),
    ("what is the capital of spain", ["madrid"]),
    ("what is the capital of russia", ["moscow"]),
    ("what is the capital of brazil", ["brazil"]),
    ("what is the capital of india", ["new delhi"]),
    ("what is the capital of mexico", ["mexico city"]),
    ("what is the capital of nigeria", ["abuja"]),
    ("what is the capital of turkey", ["ankara"]),
    ("what is the capital of south korea", ["seoul"]),
    ("what is the capital of argentina", ["buenos aires"]),
    ("what is the capital of portugal", ["lisbon"]),
    ("what is the capital of sweden", ["stockholm"]),
    ("what is the capital of poland", ["warsaw"]),
    ("who is napoleon", ["napoleon"]),
    ("who was cleopatra", ["cleopatra"]),
    ("who is gandhi", ["gandhi"]),
    ("who was martin luther king", ["martin luther king"]),
    ("who is nelson mandela", ["mandela"]),
    ("who was leonardo da vinci", ["da vinci"]),
    ("who was galileo", ["galileo"]),
    ("who was newton", ["newton"]),
    ("who is einstein", ["einstein"]),
    ("who was tesla", ["tesla"]),
    ("who is da vinci", ["da vinci"]),
    ("who painted the mona lisa", ["mona lisa", "da vinci"]),
    ("who painted the scream", ["scream", "munch"]),
    ("who sculpted david", ["david", "michelangelo"]),
    ("who wrote the divine comedy", ["divine comedy", "dante"]),
    ("who wrote moby dick", ["moby dick"]),
    ("who wrote the catcher in the rye", ["catcher in the rye"]),
    ("who directed the godfather", ["godfather"]),
    ("who directed star wars", ["star wars", "lucas"]),
    ("who invented the light bulb", ["light bulb"]),
    ("who invented the printing press", ["printing press"]),
    ("who discovered america", ["america", "columbus"]),
    ("who discovered the electron", ["electron"]),
    ("who discovered radioactivity", ["radioactiv"]),
    ("who discovered the structure of dna", ["dna"]),
]

# ── Food / drink / daily life ─────────────────────────────────────────────────
FOOD_DAILY = [
    ("what is sushi", ["sushi"]),
    ("what is pizza", ["pizza"]),
    ("what is pasta", ["pasta"]),
    ("what is chocolate made of", ["chocolate"]),
    ("how is cheese made", ["cheese"]),
    ("how is wine made", ["wine"]),
    ("how is bread made", ["bread"]),
    ("how is butter made", ["butter"]),
    ("how is yogurt made", ["yogurt"]),
    ("how is whiskey distilled", ["whiskey"]),
    ("how is vodka made", ["vodka"]),
    ("how is sugar made", ["sugar"]),
    ("how is salt harvested", ["salt"]),
    ("how is honey made", ["honey"]),
    ("how is paper made", ["paper"]),
    ("how is glass made", ["glass"]),
    ("how is steel made", ["steel"]),
    ("how is plastic made", ["plastic"]),
    ("how is rubber made", ["rubber"]),
    ("how is cotton made into fabric", ["cotton"]),
    ("what is the difference between a fruit and a vegetable", ["fruit", "vegetable"]),
    ("what is the difference between jam and jelly", ["jam", "jelly"]),
    ("what is the difference between a mocha and a latte", ["mocha", "latte"]),
    ("what is the difference between a tornado and a hurricane", ["tornado", "hurricane"]),
    ("what is the difference between an alligator and a crocodile", ["alligator", "crocodile"]),
    ("what is the difference between a rabbit and a hare", ["rabbit", "hare"]),
    ("what is the difference between a turtle and a tortoise", ["turtle", "tortoise"]),
    ("what is the difference between a moth and a butterfly", ["moth", "butterfly"]),
    ("what is the difference between a seal and a sea lion", ["seal"]),
    ("what is the difference between an octopus and a squid", ["octopus", "squid"]),
    ("what is the difference between a llama and an alpaca", ["llama", "alpaca"]),
    ("what is the difference between a stalactite and a stalagmite", ["stalactite", "stalagmite"]),
    ("what is the difference between a meteor and a comet", ["meteor", "comet"]),
    ("what is the difference between a planet and a star", ["planet", "star"]),
    ("what is the difference between an asteroid and a meteor", ["asteroid", "meteor"]),
    ("what is the difference between weather and climate", ["weather", "climate"]),
    # legs & body counts
    ("how many legs does a cat have", ["four"]),
    ("how many legs does a bird have", ["two"]),
    ("how many legs does a crab have", ["ten"]),
    ("how many legs does a snake have", ["no legs"]),
    # country profiles (bare-name lookups)
    ("tell me about spain", ["Spain", "Madrid"]),
    ("tell me about italy", ["Italy", "Rome"]),
    ("what is the usa", ["United States"]),
    ("tell me about china", ["China", "Beijing"]),
    ("tell me about russia", ["Russia", "Moscow"]),
    # city profiles
    ("tell me about paris", ["Paris", "Eiffel Tower"]),
    ("tell me about london", ["London", "Big Ben"]),
    ("tell me about tokyo", ["Tokyo"]),
    ("tell me about new york", ["New York"]),
    # measurements
    ("how tall is the statue of liberty", ["93 meters"]),
    ("how long is the amazon river", ["6,400"]),
    ("how deep is the ocean", ["3,700"]),
    ("how hot is the sun", ["5,500"]),
    ("how heavy is an elephant", ["6 tonnes"]),
    ("how long is the great wall of china", ["21,196"]),
    # more cities
    ("tell me about barcelona", ["Barcelona", "Sagrada"]),
    ("tell me about dubai", ["Dubai", "Burj Khalifa"]),
    ("tell me about vienna", ["Vienna"]),
    ("tell me about amsterdam", ["Amsterdam", "canals"]),
    ("tell me about seoul", ["Seoul"]),
    ("tell me about singapore", ["Singapore"]),
    # tech comparisons
    ("what is the difference between a list and a tuple", ["mutable", "immutable"]),
    ("what is the difference between a stack and a queue", ["LIFO", "FIFO"]),
    ("what is the difference between a compiler and an interpreter", ["compiler", "interpreter"]),
    ("git merge vs git rebase", ["merge", "rebase"]),
    ("what is the difference between a function and a method", ["function", "method"]),
    ("what is the difference between http and https", ["encrypted", "TLS"]),
    # more tech comparisons
    ("what is the difference between get and post", ["GET", "POST"]),
    ("what is the difference between rest and soap", ["REST", "SOAP"]),
    ("what is the difference between sql and nosql", ["SQL", "NoSQL"]),
    ("what is the difference between tcp and udp", ["TCP", "UDP"]),
    ("what is the difference between a process and a thread", ["process", "thread"]),
    # coding concepts
    ("what is a database index", ["index", "speed"]),
    ("what is a closure", ["closure", "scope"]),
    ("what is caching", ["cache"]),
    ("what is an api", ["API"]),
    ("what is recursion", ["recursion"]),
    ("what is a unit test", ["unit test"]),
    # more cities
    ("tell me about madrid", ["Madrid", "Prado"]),
    ("tell me about hong kong", ["Hong Kong"]),
    ("tell me about toronto", ["Toronto", "CN Tower"]),
    ("tell me about los angeles", ["Los Angeles", "Hollywood"]),
    ("tell me about mumbai", ["Mumbai", "Bollywood"]),
    # more coding concepts
    ("what is an orm", ["Object-Relational Mapping"]),
    ("what is middleware", ["middleware"]),
    ("what is memoization", ["cache"]),
    ("what is an ip address", ["IPv4", "IPv6"]),
    ("what is a vpn", ["VPN"]),
    ("what is a programming language", ["programming language"]),
    ("what is the difference between frontend and backend", ["frontend", "backend"]),
    ("what is the difference between a class and an object", ["class", "object"]),
    ("what is the difference between an array and a linked list", ["array", "linked list"]),
    # hashing & data structures
    ("what is hashing", ["hash"]),
    ("what is a hashmap", ["hash table"]),
    ("what is a bug in programming", ["bug"]),
    ("what is object oriented programming", ["object-oriented"]),
    ("what is a data structure", ["data structure"]),
    ("what is the difference between rest and graphql", ["REST", "GraphQL"]),
    ("what is the difference between recursion and iteration", ["recursion", "iteration"]),
    ("what is the difference between mysql and postgresql", ["MySQL", "PostgreSQL"]),
]

# ── Emphatic / exclamation / informal question forms ──────────────────────────
EMPHATIC = [
    ("what even is a cat", ["cat"]),
    ("what exactly is a black hole", ["black hole"]),
    ("what the heck is a quasar", ["quasar"]),
    ("what on earth is dark matter", ["dark matter"]),
    ("how on earth do magnets work", ["magnet"]),
    ("how the hell does wifi work", ["wireless", "network"]),
    ("how come the sky is blue", ["sky"]),
    ("why is the sky so blue", ["sky"]),
    ("why are cats so cute", ["cat"]),
    ("why is coffee so popular", ["coffee"]),
    ("what in the world is a tesseract", ["tesseract"]),
    ("who even invented the wheel", ["wheel"]),
    ("what the heck does dna stand for", ["dna"]),
]

# ── Edge cases ────────────────────────────────────────────────────────────────
EDGE = [
    ("hello", []),
    ("hi there", []),
    ("hey", []),
    ("thanks", []),
    ("12345", []),
    ("!!!", []),
    ("what is 2+2", ["4"]),
    ("lorem ipsum dolor sit amet", []),
    ("https://example.com", []),
    ("test@example.com", []),
    ("asdfghjkl", []),
    ("what", []),
    ("why", []),
    ("huh?", []),
]

# ── Sequential / context-dependent behavior (ordered, run after everything) ───
SEQUENCES = [
    # (setup_queries, test_query, [required], [forbidden])
    # 1. True follow-up: "key pioneers" should resolve to the jazz topic
    (
        ["tell me about jazz"],
        "who were the key pioneers?",
        ["jazz"],
        [],
    ),
    # 2. Previous topic must NOT pollute a fresh self-contained comparison
    (
        ["what is a cat"],
        "how do cats and dogs differ",
        ["cat", "dog"],
        ["lion"],
    ),
    # 3. "what about X" introduces a NEW subject, not the previous topic
    (
        ["tell me about france"],
        "what about spain",
        ["Spain"],
        [],
    ),
    # 4. Pronoun "it" resolves to the previous topic
    (
        ["what is a cat"],
        "how many legs does it have",
        ["four"],
        [],
    ),
    (
        ["tell me about the eiffel tower"],
        "how tall is it",
        ["Eiffel"],
        [],
    ),
    # 5. Locative "there" resolves to the previous topic
    (
        ["tell me about paris"],
        "what is the population there",
        ["Paris"],
        [],
    ),
    # 3. Green tea / black tea comparison must not inherit "tea" as a whole
    (
        ["what is coffee"],
        "how are green tea and black tea similar",
        ["green tea", "black tea"],
        [],
    ),
    # 4. Follow-up "how does it work" resolves to the previous topic
    (
        ["how do solar panels work"],
        "how does it work exactly?",
        ["solar"],
        [],
    ),
    # 5. A follow-up with "it" should resolve, but a fresh comparison must not
    (
        ["what is jazz"],
        "how is it different from blues",
        ["jazz", "blues"],
        [],
    ),
]

CASES = (CORE + WRAPPERS + SLANG + CATEGORIES + COMPARISONS + SCIENCE
         + GEO_CULTURE + FOOD_DAILY + EMPHATIC + EDGE)


def _check(query, required, forbidden, timeout=20):
    import signal

    class _Timeout(Exception):
        pass

    def _alarm(*_):
        raise _Timeout()

    old = signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(timeout)
    try:
        response = process_query(query)
    except _Timeout:
        response = "__TIMEOUT__"
    except Exception as exc:  # noqa: BLE001 — battery must never die on one query
        response = f"__ERROR__: {exc}"
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)
    low = response.lower()
    missing = [k for k in required if k.lower() not in low]
    bad = [f for f in forbidden if f.lower() in low]
    return response, missing, bad


def main():
    reset_conversation()
    passed = failed = 0
    failures = []
    for query, required, *rest in CASES:
        forbidden = rest[0] if rest else FALLBACK_PHRASES
        response, missing, bad = _check(query, required, forbidden)
        if missing or bad:
            failed += 1
            failures.append((query, missing, bad, response[:300]))
        else:
            passed += 1

    # Sequence tests run in a controlled conversation
    for setup, query, required, forbidden in SEQUENCES:
        reset_conversation()
        for s in setup:
            process_query(s)
        response, missing, bad = _check(query, required, forbidden)
        if missing or bad:
            failed += 1
            failures.append((query, missing, bad, response[:300]))
        else:
            passed += 1

    print(f"Results: {passed}/{passed + failed} passed")
    if failures:
        print("\nFAILURES:")
        for query, missing, bad, snippet in failures:
            print(f"  Q: {query}")
            if missing:
                print(f"     missing: {missing}")
            if bad:
                print(f"     forbidden hit: {bad}")
            print(f"     response: {snippet}")
        sys.exit(1)


if __name__ == '__main__':
    main()
