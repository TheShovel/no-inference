import sys, signal, time
sys.path.insert(0, 'src')
import cos.engine as engine
engine._search_wikipedia = lambda query: (None, None)
engine._search_wikipedia_full = lambda query: (None, None)
import cos.nlg.fallback as _nf
_nf.fallback_response = lambda q, c: 'FALLBACK-NETWORK'
import cos.code_knowledge as CK
CK._search_stack = lambda query, max_files=2: []
from cos.engine import process_query, reset_conversation

FALLBACK = ['fallback-network', 'i do not have enough specific information',
            "i'm not sure about that", 'i could not find enough']

def alarm(*a): raise TimeoutError()
signal.signal(signal.SIGALRM, alarm)

# (query, [keywords]) — keywords required in the response
CASES = [
    # --- factual, varied phrasing ---
    ('whats the capital of france', ['paris']),
    ('capital of japan?', ['tokyo']),
    ('do you know what a black hole is', ['black hole']),
    ('tell me about the moon', ['moon']),
    ('spill the beans on coffee', ['coffee']),
    ('explain photosynthesis like im 5', ['photosynthesis']),
    ('why is the ocean salty', ['salt']),
    ('how are clouds formed', ['cloud']),
    ('what makes thunder', ['thunder']),
    ('who came up with the theory of relativity', ['einstein']),
    ('whos the author of harry potter', ['rowling']),
    ('how old is the sun', ['sun', 'billion']),
    ('how heavy is a blue whale', ['whale']),
    ('are penguins birds', ['bird']),
    ('is a strawberry a berry', ['berry']),
    ('whats the fastest thing in the universe', ['light']),
    ('how long does it take light to reach the earth', ['sun', 'minute']),
    ('what do bees do', ['bee']),
    ('why do dogs wag their tails', ['dog']),
    ('what happens if you fall into a black hole', ['black hole']),
    # --- coding, custom ---
    ('python how to sort a dictionary by value', ['sort', 'value']),
    ('how do i reverse an array in javascript', ['reverse']),
    ('whats the difference between == and === in js', ['==', '===']),
    ('how to read user input in python', ['input']),
    ('make a function that returns the length of a string', ['len']),
    ('javascript how to remove an item from an array', ['splice', 'filter']),
    ('what does this do in python: [x*2 for x in range(5)]', ['comprehension']),
    ('how to catch errors in javascript', ['catch']),
    ('sql how to count rows in a table', ['count']),
    ('what is the difference between a list and an array in python', ['list', 'array']),
    ('how to sleep in python', ['sleep', 'time']),
    ('what is a promise in js vs a callback', ['promise', 'callback']),
    ('how to open a file in python and read it', ['open', 'read']),
    ('write a loop that prints numbers 1 to 10', ['loop']),
    # --- editing, custom ---
    ('fix this: teh dog ran fastly across teh yard', ['the dog ran']),
    ('clean up this text: hello there , how are you doing today ?', ['hello there, how']),
    ('fix the typos: i cant beleive it is already tuesday', ["can't believe"]),
    ('rewrite this to fix grammar: me and my friend went to the store', ['i']),
    ('fix this code bug: function add(a b) { retunr a + b }', ['add(', 'return']),
    ('edit this: the reciept was incorrect so i returned it', ['receipt']),
    ('fix this python: def greet(name): print("hello" + name', ['def greet']),
    # --- slang, custom ---
    ('yo wuts up with black holes', ['black hole']),
    ('idk what a quasar is', ['quasar']),
    ('explain wat a dog is', ['dog']),
    ('im wondering what the capital of australia is', ['canberra']),
    ('wanna know how tall the eiffel tower is', ['eiffel']),
    ('gimme the lowdown on sharks', ['shark']),
    ('u know anything about the roman empire', ['roman']),
    # --- comparisons, custom ---
    ('cats or dogs which is better', ['cat', 'dog']),
    ('compare python and java', ['python', 'java']),
    ('whats better sql or nosql', ['sql']),
    ('how do lions and tigers compare', ['lion', 'tiger']),
    ('is a wolf bigger than a fox', ['wolf', 'fox']),
    ('difference between a hurricane and a typhoon', ['hurricane', 'typhoon']),
    ('whats the same about tea and coffee', ['tea', 'coffee']),
    # --- categories, custom ---
    ('what kinds of big cats are there', ['lion', 'tiger']),
    ('name some types of cheese', ['cheese']),
    ('what sort of clouds are there', ['cloud']),
    ('list some dog breeds', ['dog']),
    ('what types of pasta exist', ['pasta']),
    ('give me examples of mythical creatures', ['dragon', 'unicorn']),
    # --- geography / people, custom ---
    ('capital of norway', ['oslo']),
    ('who is the father of computers', ['babbage']),
    ('who wrote the odyssey', ['homer']),
    ('whats the longest river', ['nile']),
    ('biggest ocean in the world', ['pacific']),
    ('how many bones does the human body have', ['206']),
    ('whats the highest mountain in africa', ['kilimanjaro']),
    # --- science / how-things, custom ---
    ('why does the sun set in the west', ['earth', 'rotate']),
    ('how do planes stay in the air', ['lift', 'wing']),
    ('why is grass green', ['chlorophyll']),
    ('what makes a rainbow appear', ['rainbow']),
    ('how does a microwave work', ['microwave']),
    ('why do we sleep', ['sleep']),
    ('what causes lightning', ['lightning']),
    ('how is glass transparent', ['glass']),
    # --- edge cases, custom ---
    ('???', []),
    ('', []),
    ('abc123xyz', []),
    ('tell me a joke', []),
    ('do you dream', []),
    ('what is love', []),
    ('42', []),
    ('please', []),
    ('thanks bro', []),
    ('hello bot', []),
]

def run(query, required):
    signal.alarm(20)
    try:
        t0 = time.time()
        r = process_query(query)
        dt = time.time() - t0
    except TimeoutError:
        return 'HANG', None, None
    finally:
        signal.alarm(0)
    low = r.lower()
    fb = [f for f in FALLBACK if f in low]
    missing = [k for k in required if k.lower() not in low]
    return r, missing, fb

reset_conversation()
results = []
for q, req in CASES:
    r, missing, fb = run(q, req)
    if r == 'HANG':
        results.append(('HANG', q, [], []))
    elif missing or fb:
        results.append(('FAIL', q, missing, fb))
    else:
        results.append(('PASS', q, [], []))

stats = {}
for status, q, m, f in results:
    stats[status] = stats.get(status, 0) + 1
print('=== SUMMARY ===')
print('total:', len(results), '| pass:', stats.get('PASS', 0), '| fail:', stats.get('FAIL', 0), '| hang:', stats.get('HANG', 0))
print()
for status, q, m, f in results:
    if status != 'PASS':
        print(f'[{status}] {q}')
        if m: print('     missing:', m)
        if f: print('     fallback:', f)
