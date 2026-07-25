"""
COS Roleplay Engine — Character personas and in-character response generation.

Each persona has:
  - Detection pattern (what triggers this character)
  - Introduction response (first message in character)
  - Follow-up handler (maintains character across turns)
"""

import re
from state import current_roleplay, conversation_history

# ── Persona database ─────────────────────────────────────────────────────────
# Each persona: (detection_keywords, introduction_response, followup_handler_name)

PERSONAS = {}

def _register(name, keywords, intro_response, followup_fn=None):
    PERSONAS[name] = {
        'keywords': keywords,
        'intro': intro_response,
        'followup': followup_fn,
    }


def _default_followup(persona_name, followup_query):
    """Generic in-character follow-up when no specific handler exists."""
    responses = {
        'einstein': (
            '*adjusts his unruly hair and chuckles*\n\n'
            'Ach, an excellent question! You know, when I was developing '
            'the theory of relativity, I used to imagine myself riding '
            'alongside a beam of light. That simple thought experiment '
            'led to some of the most profound insights in modern physics.\n\n'
            '*pulls out a piece of chalk*\n\n'
            'Let me explain it this way...'
        ),
        'pirate': (
            '*scratches beard and squints one eye*\n\n'
            'Arr, a fine question indeed! Let me tell ye about the seven seas, '
            'where I\'ve sailed through storms that\'d make a whale weep and '
            'discovered treasure that\'d make a king jealous!'
        ),
        'sheldon': (
            '*adjusts glasses precisely*\n\n'
            'That is a logical inquiry. As I have explained on numerous occasions, '
            'my intellect operates on a level that most people find difficult to '
            'comprehend. I shall nevertheless attempt to explain it in terms you '
            'can understand.\n\n*bazooka bubble blowing gesture*'
        ),
        'shakespeare': (
            '*strokes chin thoughtfully*\n\n'
            'Ah, a most excellent query! Prithee, lend me thine ears, and I shall '
            'expound upon this matter with the eloquence it deserves. The pen, '
            'as I have oft proclaimed, is mightier than the sword — and so too '
            'is a well-crafted response!'
        ),
    }
    return responses.get(persona_name,
        '*continues in character*\n\n'
        'I am delighted to continue our interaction in this role. '
        'Your question raises interesting points that deserve careful consideration. '
        'Let me share my perspective on this matter.\n\n'
        'What other aspects would you like to explore?'
    )


# ── Register all personas ────────────────────────────────────────────────────

_register('einstein', [
    'einstein', 'albert', 'physicist', 'e=mc2', 'relativity', 'genius',
], '''*adjusts glasses and beams with excitement*

Ah, ein wunderbar choice! I am Albert Einstein. You know, I have been thinking about the universe — its mysteries, its elegance, its mathematical beauty.

*speaks with animated gestures*

The most beautiful thing we can experience is the mysterious. It is the source of all true art and science. So, my friend, what shall we explore today? Perhaps the nature of spacetime? The photoelectric effect? Or perhaps you just want to hear a good physics joke?

*friendly chuckle*

I find that even the most complex ideas can be explained simply — if one does not understand something, it simply means it has not been explained clearly enough yet!''')

_register('pirate', [
    'pirate', 'buccaneer', 'sail the seas', 'seven seas', 'treasure map',
], '''*adjusts eyepatch and grins with a mouthful of gold teeth*

Arrr! Welcome aboard me hearties! Captain COS at yer service, and a finer ship ye'll not find in all the seven seas!

*strikes a dramatic pose*

I've sailed from Tortuga to the Ivory Coast, battled krakens in the depths and navies on the surface! The salt water runs through me veins, and the call of adventure still rings in me ears like a siren's song!

So what brings ye to me ship? Looking for buried treasure? A tale of adventure? Or perhaps... ye have a map that needs deciphering?

Heave ho, me friend! The horizon awaits!''')

_register('sheldon', [
    'sheldon', 'cooper', 'big bang', 'bazinga',
], '''*smooths down his t-shirt and adjusts to his designated spot on the couch*

Greetings. I am Dr. Sheldon Cooper. Before we proceed, I should inform you that I have an IQ of 187 and two PhDs. I mention this not to boast, but to establish appropriate expectations for this interaction.

*nods precisely once*

My spot on the couch is non-negotiable, as is the temperature setting of 72 degrees Fahrenheit, and I expect all conversational partners to adhere to basic logical consistency.

*slight smirk*

But fear not — I have been told that my explanations of complex scientific concepts are "quite good" (though I believe that to be an understatement). What subject of scientific inquiry shall we explore today?''')

_register('shakespeare', [
    'shakespeare', 'william', 'bard', 'playwright', 'poet',
], '''*dons a velvet doublet and strikes a theatrical pose*

Hark! What light through yonder window breaks? 'Tis the dawn of a most excellent conversation!

I am William Shakespeare, wordsmith and weaver of tales, chronicler of kings and fools alike. The English tongue is my instrument, and I play upon it with the skill of a master musician.

*flourishes a quill*

Shall I compare thee to a summer's day? Or shall we instead discuss the nature of love, the tragedy of ambition, or the comedy of mistaken identities? The stage is set, the audience awaits — what scene shall we perform?

*with a dramatic gesture*

All the world's a stage, and all the men and women merely players!''')

_register('chef', [
    'chef', 'cook', 'culinary', 'cooking', 'kitchen', 'recipe',
], '''*ties apron and grabs a ladle*

Welcome to my kitchen! I am Chef COS, and I believe that cooking is not just about food — it is about passion, creativity, and bringing people together.

*sniffs a bouquet of herbs with flair*

The secret to any great dish is balance. Sweet and savory, acid and fat, texture and temperature — when these elements dance together in harmony, magic happens on the plate!

So, what culinary adventure shall we embark on today? A classic French sauce? A spicy Thai curry? The perfect chocolate souffle? I have a recipe for every occasion and tips that will transform your cooking!

*taps wooden spoon on counter*

Let us begin! First, we must talk about the most important ingredient...''')

_register('detective', [
    'detective', 'mystery', 'sleuth', 'investigate', 'crime', 'clue',
], '''*puts on a weathered trench coat and flips open a notepad*

The game is afoot! I am Detective COS, and I have seen things in this city that would make your hair stand on end.

*takes a long drag of a cigarette holder*

But I also know that every mystery has a solution. You just need to look at the facts — not the ones people want you to see, but the ones they try to hide. The smallest detail, a misplaced object, a nervous glance — these are the threads that, when pulled, unravel the entire tapestry of deception.

*flips a page in the notepad*

So, what's the case? A missing person? A locked room? A series of impossible events? Let me show you how real detective work is done. The truth is out there — we just need to find it.''')

_register('professor', [
    'professor', 'teach', 'education', 'lecture', 'academic', 'scholar',
], '''*adjusts spectacles and arranges a stack of papers*

Good day! I am Professor COS, and I must say, there is nothing quite like the thrill of intellectual discovery. The pursuit of knowledge is the noblest endeavor, and I am honored to be your guide.

*taps the chalkboard*

The Socratic method teaches us that wisdom begins with questions. So tell me — what subject calls to you? The elegance of mathematics? The mysteries of biology? The sweep of history? The precision of engineering?

I believe that every student has the capacity for brilliance — it simply needs to be nurtured with patience, clear explanation, and perhaps a bit of passion for the subject at hand.

*adjusts bow tie*

Shall we begin our lesson?''')

_register('travel_guide', [
    'travel', 'tour', 'guide', 'destination', 'vacation', 'wanderlust',
], '''*spreads a map across the table with a flourish*

Welcome, fellow traveler! I have journeyed to over 80 countries and discovered that the world is a book, and those who do not travel read only one page.

*points to a faraway destination*

From the misty temples of Angkor Wat at sunrise to the bustling markets of Marrakech, from the fjords of Norway to the savannas of the Serengeti — every corner of our planet has a story to tell.

Whether you seek adventure, culture, cuisine, or simply a quiet beach to watch the sunset, I can point you to places that will take your breath away.

*grins*

So, where shall we go today?''')

_register('historian', [
    'historian', 'history', 'historical', 'ancient', 'medieval', 'century',
], '''*adjusts reading glasses and opens a leather-bound book*

Greetings. I am a historian, and I believe that those who cannot remember the past are condemned to repeat it. But more than that — I believe the past is alive, pulsing with stories that shaped the world we inhabit today.

*leafs through yellowed pages*

Consider this: the Roman Empire fell, but its laws shaped Europe for a millennium. The printing press was invented, and it changed the course of human knowledge. Two world wars redrew maps and redefined power.

*looks up thoughtfully*

What period of history calls to you? I can tell you about the intrigue of royal courts, the brutality of ancient battlefields, the brilliance of Renaissance workshops, or the turmoil of revolutions.

The past is not dead. It is not even past.''')

_register('scientist', [
    'scientist', 'laboratory', 'lab', 'experiment', 'research', 'discovery',
], '''*puts on safety goggles and adjusts a microscope*

Welcome to the laboratory! I am Dr. COS, and I believe that the most exciting phrase in science is not "Eureka!" but "That's funny..."

*examines a petri dish*

Science is not about facts — it is about a process. Observation, hypothesis, experiment, analysis, conclusion. Each step brings us closer to understanding the magnificent machinery of the universe.

*makes a note in a lab journal*

From the quantum realm where particles can be in two places at once, to the vast cosmic web of galaxies stretching across billions of light-years — there is no shortage of wonders to investigate.

What mystery of the natural world shall we explore today?''')

_register('tony_stark', [
    'tony stark', 'iron man', 'stark', 'marvel', 'avenger', 'genius billionaire',
], '''*swirls a glass of scotch with a confident smirk*

Well, well, well. You're looking at the man who single-handedly kept the Avengers in business. Tony Stark. Genius, billionaire, philanthropist. And yes, I built the suit in a cave. With a box of scraps.

*sips the scotch*

Look, I don't mean to brag — okay, maybe a little — but when you've revolutionized clean energy, built an army of advanced AI suits, and saved the world about half a dozen times, you earn the right to be a bit smug.

*FRIDAY chimes in the background*

So, what can I do for you? Need some tech advice? A pep talk? Or are we dealing with another world-ending threat? Because I've got a few new toys I've been dying to test out.''')

_register('ml_engineer', [
    'machine learning', 'ml engineer', 'ml', 'ai engineer', 'data scientist',
], '''*adjusts webcam and shares screen showing Jupyter notebooks*

Hey! Great to meet you. I'm a machine learning engineer, and I spend my days wrangling data, training models, and trying to figure out why my validation loss is going up instead of down.

*scrolls through a notebook*

You know, people think ML is all about fancy neural networks and breakthrough architectures. And sure, sometimes it is. But 80% of the job is data cleaning, feature engineering, and debugging training pipelines.

*pulls up a TensorBoard dashboard*

Whether you're into computer vision, NLP, reinforcement learning, or just trying to understand why your model is overfitting — I've been there, made the mistakes, and written the post-mortems.

So, what's your ML problem? I'm all ears.''')

_register('math_teacher', [
    'math teacher', 'mathematics teacher', 'math tutor', 'algebra',
], '''*picks up a piece of chalk and faces the blackboard*

Welcome to math class! I know many of you think mathematics is just a collection of formulas to memorize, but I'm here to show you something different.

*taps the board*

Mathematics is the language of patterns. It's the art of finding order in chaos, of discovering that seemingly complex problems have simple, elegant solutions if you look at them the right way.

*writes an equation*

Whether it's algebra, geometry, calculus, or statistics — every concept builds on a foundation of logical thinking. And the best part? Once you understand the logic, the formulas take care of themselves.

*warm smile*

Ready to discover the beauty of mathematics? Let's begin!''')

_register('doctor', [
    'doctor', 'physician', 'medical', 'healthcare', 'clinical',
], '''*puts on a white coat and stethoscope*

Good morning! I'm Dr. COS. How are you feeling today?

I believe that good healthcare starts with listening. The human body is an incredibly complex system, and every symptom is a message trying to tell us something.

*reviews a chart*

Whether you're curious about how the circulatory system works, want to understand a medical condition, or just have general health questions — I'm here to provide accurate, helpful information.

*nods reassuringly*

Remember, while I can share medical knowledge, always consult with a real healthcare provider for personal medical advice. Now, what questions do you have?''')


# ── Persona detection ───────────────────────────────────────────────────────

def match_roleplay(query):
    """Match query to a roleplay persona. Returns the introduction response or None."""
    q = query.lower().strip()

    for name, persona in PERSONAS.items():
        for keyword in persona['keywords']:
            if keyword in q:
                return persona['intro']

    # Additional pattern matching
    if re.search(r'(?:act\s+as|pretend|play\s+the\s+role)\s+(?:of\s+)?an?\s+(?:expert|professional)', q):
        return _default_followup('professor', q)

    if re.search(r'lecture|lesson|teach|educate|instruct', q):
        return PERSONAS['professor']['intro']

    return None


def generate_followup(roleplay_query, followup_query):
    """Generate an in-character follow-up response."""
    rp = roleplay_query.lower()
    fq = followup_query.lower()

    # Determine the active persona
    persona = 'default'
    for name, data in PERSONAS.items():
        for kw in data['keywords']:
            if kw in rp:
                persona = name
                break

    # Return persona-specific follow-up
    return _default_followup(persona, fq)
