"""COS Text & Code Editor — deterministic, rule-based editing.

The engine is purely symbolic (no LLM), so editing is done with safe,
word-boundary transformation rules:

  * Text: capitalization, common typos, spacing, contractions, clear
    homophone errors (your/you're, there/their/they're, its/it's), a/an.
  * Code: common identifier typos, tabs->spaces, trailing whitespace,
    missing commas in Python function signatures.

detect_edit_request() recognizes imperative edit commands ("fix this code: ...",
"edit this email to fix any problems: ...") and extracts the content to edit.
"""
import re
from typing import List, Optional, Tuple

# ── Edit-request detection ──────────────────────────────────────────────────

_EDIT_VERBS = (
    'edit', 'fix', 'rewrite', 'improve', 'correct', 'clean', 'clean up',
    'debug', 'review', 'refactor', 'proofread', 'polish', 'tidy', 'revise',
    'rephrase', 'reword', 'reformat', 'fix the problems', 'fix any problems',
    'fix the issues', 'fix the errors', 'fix the typos', 'fix the bugs',
    'fix the grammar', 'check the grammar', 'correct the typos',
    'fix the spelling', 'fix the punctuation', 'fix the mistakes',
    'check for errors', 'check for typos', 'check for mistakes',
    'make this sound better', 'make this sound more professional',
    'make this sound more natural', 'make this better',
    'make this more professional', 'review this', 'review the',
    'check this', 'check the', 'whats wrong with',
    "what's wrong with", 'check my', 'proofread the',
)
_TARGETS = (
    'email', 'e-mail', 'text', 'paragraph', 'essay', 'sentence', 'message',
    'letter', 'article', 'code', 'script', 'function', 'program', 'file',
    'document', 'writing', 'draft', 'note', 'copy', 'description', 'bio',
    'intro', 'introduction', 'poem', 'story', 'headline', 'title', 'caption',
    'review', 'summary', 'response', 'reply', 'post', 'comment', 'tweet',
    'subject line', 'template', 'json', 'data',
    'html', 'css', 'sql', 'bash', 'python', 'javascript', 'typescript', 'java',
    'cpp', 'c#', 'rust', 'go', 'ruby', 'php', 'swift', 'kotlin',
)
_LANG_ADJ = '|'.join((
    'python', 'javascript', 'typescript', 'java', 'c\\+\\+', 'c#', 'cpp',
    'rust', 'go', 'golang', 'ruby', 'php', 'swift', 'kotlin', 'scala',
    'html', 'css', 'sql', 'bash', 'shell', 'react', 'vue', 'node', 'flask',
    'django',
))

_PREFIX_RE = re.compile(
    r'^(?:(?:can|could|will|would)\s+you\s+(?:please\s+)?|please\s+(?:you\s+)?)?'
    r'(?:' + '|'.join(_EDIT_VERBS) + r')\s+'
    r'(?:(?:in|on|for|of|within)\s+)?'   # "fix the typos IN this text"
    r'(?:(?:this|the|my|our|that|a|an|it)|(?:the|this)\s+following|following|attached|enclosed)?\s*'
    r'(?:(?:' + _LANG_ADJ + r')\s+)?'         # "fix this PYTHON script"
    r'(?:' + '|'.join(_TARGETS) + r')\b'
    r'(?:\s+(?:to|and|so|for)\s+(?:fix|improve|correct|make|be|read|sound|look|flow|clean|polish|shorten|expand|reword|rephrase|bugs|issues|problems|errors|style|grammar|spelling|me|us|you)\b[^:]*)?'
    r'(?:\s+(?:below|above|attached|enclosed))?'
    r'[:]?\s*',
    re.IGNORECASE,
)


def detect_edit_request(query: str) -> Optional[Tuple[str, str]]:
    """Detect an edit command and extract the content to edit.

    Returns (kind, content) where kind is one of 'email', 'code', 'text',
    'json', 'json_check', or None if the query is not an edit request.
    """
    q = query.strip()
    if not q:
        return None
    # "is this json valid: {...}" — a validation request, not an edit
    m_check = re.match(
        r'^(?:is|is this|is that)\s+(?:the\s+)?json\s+(?:valid|correct|ok(?:ay)?)\s*[:]?\s*',
        q, re.IGNORECASE)
    if m_check:
        return ('json_check', q[m_check.end():].strip())
    m = _PREFIX_RE.match(q)
    if not m:
        # Fallback 1: no target word at all — "fix this: <content>",
        # "fix the typos: <content>", "rewrite this to fix grammar: <content>"
        m2 = re.match(
            r'^(?:(?:this|the|my|that|our|your)\s+[^:]{0,60}?,\s+)?'
            r'(?:(?:can|could|will|would)\s+you\s+(?:please\s+)?|please\s+(?:you\s+)?)?'
            r'(?:' + '|'.join(_EDIT_VERBS) + r')\s*(?:this|that|it)?'
            r'(?:\s+(?:to|and|so|for)\s+(?:fix|improve|correct|make|be|read|sound|look|flow|clean|polish|shorten|expand|reword|rephrase|bugs|issues|problems|errors|style|grammar|spelling|me|us|you)\b[^:]*)?'
            r'\s*[:]\s*',
            q, re.IGNORECASE)
        if m2:
            raw = q[m2.end():].strip()
            if raw:
                return (_kind_of_content(raw), _finalize_content(q, raw))
            return ('text', '')
        # Fallback 2: language adjective with no target word —
        # "fix this python: <code>", "clean up this javascript: <code>"
        m3 = re.match(
            r'^(?:(?:can|could|will|would|please)\s+you\s+)?'
            r'(?:' + '|'.join(_EDIT_VERBS) + r')\s+(?:this|that)\s+'
            r'(?:' + _LANG_ADJ + r')\s*[:]\s*',
            q, re.IGNORECASE)
        if m3:
            return ('code', _finalize_content(q, q[m3.end():].strip()))
        return None
    prefix = m.group(0)
    raw = q[m.end():].strip()

    # Determine the kind from the prefix (target word)
    prefix_lower = prefix.lower()
    if 'email' in prefix_lower or 'e-mail' in prefix_lower:
        kind = 'email'
    elif 'json' in prefix_lower:
        kind = 'json'
    elif any(t in prefix_lower for t in (
            'code', 'script', 'function', 'program', 'file',
            'html', 'css', 'sql', 'bash', 'shell', 'python', 'javascript',
            'typescript', 'java', 'cpp', 'c#', 'rust', 'go', 'ruby', 'php',
            'swift', 'kotlin', 'scala', 'react', 'vue', 'node', 'flask',
            'django')):
        kind = 'code'
    else:
        kind = 'text'

    return (kind, _finalize_content(q, raw))


def _finalize_content(query: str, raw: str) -> str:
    """Resolve the content to edit: quoted text wins only when the quotes span
    most of the content ("fix this: \"teh cat\""), otherwise keep the raw
    remainder so "fix this: teh \"cat\" sat" isn't reduced to just "cat".
    Only strips quote characters when they PAIR around the whole content — a
    content ending in a quote ("print \"bad number\"") must keep it."""
    content = raw
    _quoted = _extract_quoted(query)
    # Only trust the quoted extraction when the raw content starts with the
    # opening quote ("fix this: \"teh cat\"") — a mid-string quote pair in
    # "print \"bad number\"" must not reduce the content.
    if (_quoted and raw and raw[0] in '\"\'\u201c\u201d\u2018\u2019'
            and len(_quoted) >= max(4, int(len(raw) * 0.6))):
        content = _quoted
    content = content.strip()
    if len(content) >= 2 and content[0] == content[-1] and content[0] in '\"\'\u201c\u201d\u2018\u2019':
        content = content[1:-1].strip()
    return content


def _kind_of_content(content: str) -> str:
    """Guess whether pasted content is code, JSON, or prose.

    Deliberately conservative: plain prose often contains code-like words
    ("for", "if", "while", "let"), so weak signals only count when several
    appear together or alongside braces/semicolons.
    """
    stripped = content.lstrip()
    if stripped.startswith(('{', '[')) and ('"' in stripped or ':' in stripped):
        return 'json'
    # Strong, unambiguous code signals
    if re.search(
        r'\bdef\s+\w+\s*\(|\bfunction\s+\w+\s*\(|\bclass\s+\w+[:({]'
        r'|=>|::|\b(?:import|require|export|console\.log)\b'
        r'|\bprint\s*\(|\breturn\s+\w+\s*[;\)]',
        content):
        return 'code'
    # Weak keyword hits only count when code structure is present (braces,
    # semicolons, or a line ending in a colon) — "let me know if you can"
    # and "while we wait for the bus" must stay prose.
    _weak = re.findall(
        r'\b(?:if|for|while|let|const|var|function|elif|else|try|except|switch|case)\s',
        content)
    if _weak and (
            re.search(r'[{}\[\];]', content)
            or re.search(r':\s*$', content, re.MULTILINE)):
        return 'code'
    return 'text'


def _extract_quoted(query: str) -> Optional[str]:
    """Extract content inside quotes if present (\"...\" or '...')."""
    m = re.search(r'["\u201c\u201d](.+?)["\u201c\u201d]', query, re.DOTALL)
    if m:
        return m.group(1).strip()
    return None


# ── Text editing rules ──────────────────────────────────────────────────────

_TYPOS = {
    'teh': 'the', 'recieve': 'receive', 'recieved': 'received',
    'definately': 'definitely', 'definately': 'definitely',
    'seperate': 'separate', 'occured': 'occurred', 'wich': 'which',
    'thier': 'their', 'adress': 'address', 'lenght': 'length',
    'becuase': 'because', 'usefull': 'useful', 'succesful': 'successful',
    'successfull': 'successful', 'untill': 'until', 'writting': 'writing',
    'writen': 'written', 'recieve': 'receive', 'neccessary': 'necessary',
    'accross': 'across', 'alot': 'a lot', 'dont': "don't", 'cant': "can't",
    'wont': "won't", 'isnt': "isn't", 'didnt': "didn't", 'doesnt': "doesn't",
    'couldnt': "couldn't", 'wouldnt': "wouldn't", 'shouldnt': "shouldn't",
    'havent': "haven't", 'hasnt': "hasn't", 'wasnt': "wasn't", 'werent': "weren't",
    'arent': "aren't", 'im': "I'm", 'ive': "I've", 'id': "I'd",
    'dosent': "doesn't", 'dosnt': "doesn't",
    'youre': "you're", 'theyre': "they're", 'weve': "we've", 'whats': "what's",
    'thats': "that's", 'whos': "who's", 'wheres': "where's", 'whens': "when's",
    'whys': "why's", 'hows': "how's", 'its': None,  # handled specially (homophone)
    'grammer': 'grammar', 'calender': 'calendar', 'tommorow': 'tomorrow',
    'tomorow': 'tomorrow', 'freind': 'friend', 'beleive': 'believe',
    'acheive': 'achieve', 'probally': 'probably', 'probabaly': 'probably',
    'seperatly': 'separately', 'comming': 'coming', 'goign': 'going',
    'hte': 'the', 'emial': 'email', 'attatch': 'attach', 'attatched': 'attached',
    'begining': 'beginning', 'buisness': 'business', 'busines': 'business',
    'cheif': 'chief', 'collegue': 'colleague', 'completly': 'completely',
    'concious': 'conscious', 'enviroment': 'environment',
    'familar': 'familiar', 'febuary': 'february', 'foriegn': 'foreign',
    'goverment': 'government', 'immediatly': 'immediately', 'independant': 'independent',
    'intrest': 'interest', 'intrested': 'interested', 'knowlege': 'knowledge',
    'litterally': 'literally', 'maintainance': 'maintenance', 'managment': 'management',
    'mesage': 'message', 'ocassion': 'occasion', 'persistant': 'persistent',
    'publically': 'publicly', 'recomend': 'recommend', 'relevent': 'relevant',
    'remeber': 'remember', 'responsable': 'responsible', 'speach': 'speech',
    'supose': 'suppose', 'surprize': 'surprise', 'tendancy': 'tendency',
    'usally': 'usually', 'wendsday': 'wednesday', 'wierd': 'weird',
    'yeild': 'yield', 'vacum': 'vacuum', 'unforseen': 'unforeseen',
    'beleif': 'belief', 'bargin': 'bargain', 'caterpiller': 'caterpillar',
    'comemorate': 'commemorate', 'conceed': 'concede', 'conciousness': 'consciousness',
    'desparate': 'desperate', 'dilemna': 'dilemma', 'embarass': 'embarrass',
    'existance': 'existence', 'harrass': 'harass', 'humourous': 'humorous',
    'liason': 'liaison', 'millenium': 'millennium',
    'mischeivous': 'mischievous', 'noticable': 'noticeable',
    'occurence': 'occurrence', 'paralell': 'parallel', 'pharoah': 'pharaoh',
    'priviledge': 'privilege', 'quater': 'quarter', 'refered': 'referred',
    'rythm': 'rhythm', 'sophmore': 'sophomore', 'stomache': 'stomach',
    'superceed': 'supersede', 'tommorrow': 'tomorrow', 'wether': 'whether',
    'whitch': 'which', 'quik': 'quick', 'confidant': 'confident',
    'reciept': 'receipt', 'consistant': 'consistent', 'persistance': 'persistence',
    'occassion': 'occasion', 'occasionaly': 'occasionally', 'absolutly': 'absolutely',
    'reguard': 'regard', 'succes': 'success', 'anyways': 'anyway',
    'accomodate': 'accommodate', 'accomodation': 'accommodation',
    'accomodating': 'accommodating', 'arguement': 'argument', 'arguements': 'arguments',
    'caffiene': 'caffeine', 'caffine': 'caffeine', 'cemetary': 'cemetery',
    'cemetaries': 'cemeteries', 'colum': 'column', 'colums': 'columns',
    'commited': 'committed', 'commiting': 'committing', 'commitment': 'commitment',
    'delibrately': 'deliberately', 'disapear': 'disappear', 'disapeared': 'disappeared',
    'disapearing': 'disappearing', 'govenment': 'government', 'guage': 'gauge',
    'intresting': 'interesting', 'irresistable': 'irresistible',
    'ocured': 'occurred', 'particurly': 'particularly', 'particulary': 'particularly',
    'recomended': 'recommended', 'recomendation': 'recommendation',
    'sincerly': 'sincerely', 'sucess': 'success', 'sucessful': 'successful',
    'vaccum': 'vacuum', 'vaccume': 'vacuum', 'wich': 'which',
    # transposition typos (scrambled letters — not valid words, so safe)
    'wiht': 'with', 'nad': 'and', 'adn': 'and', 'hsa': 'has',
    'taht': 'that', 'htat': 'that', 'jsut': 'just', 'wnat': 'want',
    'woudl': 'would', 'coudl': 'could', 'shoudl': 'should', 'abotu': 'about',
    'becasue': 'because', 'hteir': 'their', 'hten': 'then', 'tehn': 'then',
    'whihc': 'which', 'wihch': 'which', 'porblem': 'problem', 'prbolem': 'problem',
    'quesiton': 'question', 'quesion': 'question', 'peopel': 'people', 'poeple': 'people',
    'frist': 'first', 'firts': 'first', 'wrold': 'world', 'worls': 'world',
    'bananna': 'banana', 'resturant': 'restaurant', 'restaraunt': 'restaurant',
    'hotell': 'hotel', 'hotal': 'hotel', 'meessage': 'message', 'messege': 'message',
    'diferent': 'different', 'diffrent': 'different', 'exmaple': 'example',
    'exmple': 'example', 'littel': 'little', 'smoe': 'some', 'somthing': 'something',
    'thier': 'their', 'recieve': 'receive',
    'anoter': 'another', 'anotehr': 'another', 'anothre': 'another',
    'tomorow': 'tomorrow', 'teh': 'the',
    'helpfull': 'helpful', 'carefull': 'careful', 'beautifull': 'beautiful',
    'wonderfull': 'wonderful', 'peacefull': 'peaceful', 'hopefull': 'hopeful',
    'painfull': 'painful', 'powerfull': 'powerful', 'successfull': 'successful',
    'thankfull': 'thankful', 'usefull': 'useful', 'colorfull': 'colorful',
    'fearfull': 'fearful', 'gratefull': 'grateful', 'faithfull': 'faithful',
    # month/day typos
    'janurary': 'January', 'feburary': 'February', 'decemeber': 'December',
    'septemeber': 'September', 'octoboer': 'October', 'novemeber': 'November',
    'tuseday': 'Tuesday', 'thrusday': 'Thursday', 'saterday': 'Saturday',
    'sunday': 'Sunday',
    # wave: more common misspellings (all non-words, so word-boundary safe)
    'happend': 'happened', 'happenned': 'happened',
    'amoung': 'among', 'amung': 'among',
    'agressive': 'aggressive', 'agression': 'aggression',
    'apparant': 'apparent', 'apparantly': 'apparently',
    'availible': 'available', 'avaliable': 'available',
    'bizzare': 'bizarre',
    'catagory': 'category', 'catagories': 'categories',
    'changable': 'changeable',
    'completley': 'completely', 'comletely': 'completely',
    'concensus': 'consensus',
    'congradulations': 'congratulations', 'congradulation': 'congratulation',
    'contagous': 'contagious',
    'curiousity': 'curiosity',
    'dissapear': 'disappear', 'dissapeared': 'disappeared',
    'exagerate': 'exaggerate', 'exaggerrate': 'exaggerate',
    'experiance': 'experience', 'experiances': 'experiences',
    'finaly': 'finally',
    'foward': 'forward',
    'frequecy': 'frequency',
    'garantee': 'guarantee', 'gaurantee': 'guarantee',
    'guarentee': 'guarantee', 'gurantee': 'guarantee',
    'greatful': 'grateful',
    'heirarchy': 'hierarchy',
    'humerous': 'humorous',
    'hygine': 'hygiene',
    'innoculate': 'inoculate',
    'jeapardy': 'jeopardy',
    'jewlery': 'jewelry',
    'lieing': 'lying',
    'listner': 'listener', 'listners': 'listeners',
    'mispell': 'misspell', 'mispelled': 'misspelled', 'mispelling': 'misspelling',
    'moniter': 'monitor',
    'neice': 'niece',
    'niether': 'neither',
    'nucular': 'nuclear',
    'offical': 'official', 'offically': 'officially',
    'oppurtunity': 'opportunity', 'oppertunity': 'opportunity',
    'parliment': 'parliament',
    'passanger': 'passenger', 'passangers': 'passengers',
    'pasttime': 'pastime',
    'payed': 'paid',
    'peice': 'piece',
    'playwrite': 'playwright',
    'posession': 'possession', 'possesion': 'possession',
    'potatos': 'potatoes', 'tomatos': 'tomatoes',
    'prefered': 'preferred',
    'pronounciation': 'pronunciation',
    'questionaire': 'questionnaire',
    'realy': 'really',
    'religous': 'religious',
    'resevoir': 'reservoir',
    'sacreligious': 'sacrilegious',
    'sceince': 'science',
    'silouette': 'silhouette',
    'similiar': 'similar',
    'sincerley': 'sincerely',
    'souvenier': 'souvenir',
    'strenght': 'strength',
    'striaght': 'straight',
    'succesfully': 'successfully',
    'suprise': 'surprise', 'suprised': 'surprised', 'suprising': 'surprising',
    'suround': 'surround', 'surounded': 'surrounded', 'surounding': 'surrounding',
    'techniqe': 'technique',
    'temperture': 'temperature',
    'threshhold': 'threshold',
    'tounge': 'tongue',
    'truely': 'truly',
    'vegtable': 'vegetable', 'vegtables': 'vegetables',
    'vehical': 'vehicle', 'vehicals': 'vehicles',
    'visable': 'visible',
    'withold': 'withhold',
    # month/day typos (more)
    'januray': 'January', 'septmeber': 'September', 'novmeber': 'November',
    'ocotber': 'October', 'thurdsay': 'Thursday', 'wenesday': 'Wednesday',
    'wensday': 'Wednesday',
    # wave 3: even more common misspellings (all non-words)
    'vaccuum': 'vacuum', 'vacume': 'vacuum',
    'assasination': 'assassination', 'assasin': 'assassin',
    'assasinate': 'assassinate',
    'commitee': 'committee', 'commitees': 'committees',
    'embarassment': 'embarrassment',
    'harrasment': 'harassment', 'harrassment': 'harassment',
    'appearence': 'appearance', 'appearences': 'appearances',
    'appitite': 'appetite',
    'beaurocracy': 'bureaucracy',
    'facinating': 'fascinating', 'facinated': 'fascinated',
    'unfortunatly': 'unfortunately', 'unfortunatley': 'unfortunately',
    'seige': 'siege',
    'kernal': 'kernel',
    'aquire': 'acquire', 'aquired': 'acquired',
    'allegience': 'allegiance',
    'aquaintance': 'acquaintance',
    'alchohol': 'alcohol',
    'amature': 'amateur',
    'artical': 'article', 'articals': 'articles',
    'attatchment': 'attachment',
    'autum': 'autumn',
    'benifit': 'benefit', 'benifits': 'benefits',
    'cancle': 'cancel',
    'charcter': 'character',
    'chocalate': 'chocolate',
    'civillian': 'civilian',
    'comission': 'commission',
    'conection': 'connection',
    'conspiricy': 'conspiracy',
    'corperate': 'corporate',
    'corupt': 'corrupt',
    'critisism': 'criticism', 'critisize': 'criticize',
    'curiculum': 'curriculum',
    'decieve': 'deceive',
    'definetly': 'definitely',
    'develope': 'develop',
    'dicipline': 'discipline',
    'dissapoint': 'disappoint',
    'distruction': 'destruction',
    'divison': 'division',
    'docter': 'doctor',
    'drunkeness': 'drunkenness',
    'effecient': 'efficient',
    'elemantary': 'elementary',
    'enchance': 'enhance',
    'enourmous': 'enormous',
    'especialy': 'especially',
    'exausted': 'exhausted',
    'excellant': 'excellent',
    'excitment': 'excitement',
    'exersise': 'exercise', 'excersise': 'exercise',
    'expence': 'expense',
    'extreem': 'extreme',
    'extrodinary': 'extraordinary',
    'florescent': 'fluorescent',
    'forseen': 'foreseen',
    'futher': 'further',
    'generaly': 'generally',
    'glamourous': 'glamorous',
    'heared': 'heard',
    'hindrence': 'hindrance',
    'holliday': 'holiday',
    'honset': 'honest',
    'hygeine': 'hygiene',
    'idealogy': 'ideology',
    'illigal': 'illegal',
    'imediately': 'immediately',
    'immitate': 'imitate',
    'impecable': 'impeccable',
    'imposible': 'impossible',
    'indispensible': 'indispensable',
    'inevitible': 'inevitable',
    'infinate': 'infinite',
    'infromation': 'information',
    'inocence': 'innocence',
    'interupt': 'interrupt',
    'irrelevent': 'irrelevant',
    'laboritory': 'laboratory',
    'lawer': 'lawyer',
    'legitamate': 'legitimate',
    'liberry': 'library',
    'lonly': 'lonely',
    'magnificient': 'magnificent',
    'maintenence': 'maintenance',
    'mamal': 'mammal',
    'marraige': 'marriage',
    'mathmatics': 'mathematics',
    'medeval': 'medieval',
    'messanger': 'messenger',
    'millitary': 'military',
    'minature': 'miniature',
    'miniscule': 'minuscule',
    'minumum': 'minimum',
    'missles': 'missiles',
    'morgage': 'mortgage',
    'nausious': 'nauseous',
    'necesary': 'necessary',
    'negociate': 'negotiate',
    'nieghbor': 'neighbor',
    'nineth': 'ninth',
    'ninty': 'ninety',
    'nuisanse': 'nuisance',
    'obediant': 'obedient',
    'oclock': "o'clock",
    'occurrance': 'occurrence',
    'omited': 'omitted',
    'oponent': 'opponent',
    'oppinion': 'opinion',
    'opression': 'oppression',
    'orgin': 'origin',
    'overwelm': 'overwhelm',
    'pamplet': 'pamphlet',
    'parellel': 'parallel',
    'percieve': 'perceive',
    'permenant': 'permanent',
    'perseverence': 'perseverance',
    'petetion': 'petition',
    'philosiphy': 'philosophy',
    'phsyical': 'physical',
    'poisen': 'poison',
    'politican': 'politician',
    'posibility': 'possibility',
    'preceeding': 'preceding',
    'prehaps': 'perhaps',
    'presidental': 'presidential',
    'prevelant': 'prevalent',
    'primative': 'primitive',
    'probaly': 'probably',
    'proceedure': 'procedure',
    'proffesional': 'professional',
    'promiss': 'promise',
    'protaganist': 'protagonist',
    'reconize': 'recognize',
    'recrod': 'record',
    'recurrance': 'recurrence',
    'reminescent': 'reminiscent',
    'representive': 'representative',
    'responcibility': 'responsibility',
    'sandwhich': 'sandwich',
    'satelite': 'satellite',
    'secretery': 'secretary',
    'sergent': 'sergeant',
    'severly': 'severely',
    'shedule': 'schedule',
    'shreik': 'shriek',
    'sieze': 'seize',
    'smoth': 'smooth',
    'sociaty': 'society',
    'specificaly': 'specifically',
    'sponcer': 'sponsor',
    'stubborness': 'stubbornness',
    'succesion': 'succession',
    'sufficent': 'sufficient',
    'supliment': 'supplement',
    'supposably': 'supposedly',
    'surgury': 'surgery',
    'symetry': 'symmetry',
    'tatoo': 'tattoo',
    'temperment': 'temperament',
    'theif': 'thief',
    'throught': 'through',
    'tution': 'tuition',
    'umbella': 'umbrella',
    'unbeleivable': 'unbelievable',
    'underneith': 'underneath',
    'uneccessary': 'unnecessary',
    'univeristy': 'university',
    'unusal': 'unusual',
    'usualy': 'usually',
    'vegatarian': 'vegetarian',
    'vengence': 'vengeance',
    'warrent': 'warrant',
    'windsheild': 'windshield',
    'wisard': 'wizard',
    'yesturday': 'yesterday',
    # wave 4: contractions and dropped-letter typos
    'hadnt': "hadn't", 'itll': "it'll", 'youd': "you'd", 'theyll': "they'll",
    'hed': "he'd", 'woud': 'would', 'coud': 'could', 'shoud': 'should',
    'haev': 'have', 'noone': 'no one', 'incase': 'in case',
    # wave 4b: transposition typos
    'eveyr': 'every', 'somethign': 'something', 'anythign': 'anything',
    'everythign': 'everything', 'notihng': 'nothing', 'enought': 'enough',
}

# Compiled single-pass alternation over the typo dictionary — one regex scan
# per edit instead of one per entry (fast on long documents). Replacement is
# case-insensitive; values with None (e.g. "its") are handled elsewhere.
_TYPOS_RE = re.compile(
    r'\b(' + '|'.join(re.escape(w) for w in sorted(_TYPOS) if _TYPOS[w]) + r')\b',
    re.IGNORECASE)

# Words where "a" is correct even though they start with a vowel letter
_VOWEL_TAKES_A = {
    'university', 'unique', 'useful', 'useless', 'user', 'users', 'use', 'used',
    'uses', 'using', 'unit', 'united', 'uniform', 'union', 'universal',
    'universe', 'usual', 'usually', 'euro', 'european', 'one', 'once',
    'unicorn', 'ukulele', 'url', 'utah', 'ufo', 'u-turn', 'us', 'usa',
    'eulogy', 'euphemism', 'ubiquitous', 'unanimous', 'uprising', 'uranium',
}

# Words that take "an" despite starting with a consonant letter (silent h)
_SILENT_H_TAKES_AN = {
    'hour', 'hours', 'honest', 'honesty', 'honor', 'honour', 'honors',
    'honours', 'honored', 'honoured', 'heir', 'heiress', 'herb', 'hourly',
}

# Common abbreviations that should not trigger sentence capitalization or
# space insertion after their period.
_ABBREVIATIONS = {
    'dr', 'mr', 'mrs', 'ms', 'st', 'sr', 'jr', 'vs', 'etc', 'e.g', 'i.e',
    'fig', 'prof', 'rev', 'gen', 'col', 'lt', 'capt', 'sgt', 'approx', 'min',
    'max', 'no', 'jan', 'feb', 'mar', 'apr', 'jun', 'jul', 'aug', 'sep',
    'sept', 'oct', 'nov', 'dec', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat',
    'sun', 'dept', 'ave', 'blvd', 'rd', 'est', 'gmt', 'mph', 'kg', 'km', 'cm',
    'mm', 'vol', 'ed', 'pp', 'cf', 'al', 'etc', 'vs', 'p.m', 'a.m', 'inc',
    'co', 'ltd', 'corp', 'gov', 'uni', 'tel', 'ph', 'ext', 'apt', 'box',
    'oz', 'lb', 'lbs', 'ft', 'yd', 'yds', 'mi', 'hr', 'hrs', 'sec', 'wpm',
}


def _fix_spacing_after_punct(text):
    """Insert a space after , . ! ? ; : when one is missing, but never inside
    abbreviations ("U.S."), decimals ("3.14"), thousands separators
    ("1,000"), or times ("3:30")."""
    def _repl(m):
        punct = m.group(0)[0]
        nxt = m.group(0)[1]
        if nxt.isdigit():
            return punct + nxt  # 3.14 / 1,000 / 3:30 — no space
        if punct != '.':
            return punct + ' ' + nxt
        # period: check the token it belongs to (single letter or abbreviation)
        before = text[:m.start(0)]
        tok = re.search(r'([A-Za-z0-9]+)$', before)
        if tok and (len(tok.group(1)) == 1 or tok.group(1).lower() in _ABBREVIATIONS):
            return punct + nxt
        return punct + ' ' + nxt
    return re.sub(r'[.,!?;:]([A-Za-z0-9])', _repl, text)


def _capitalize_sentence_starts(text):
    """Capitalize the first letter of each sentence (start of text, or after
    . ! ? followed by whitespace), but not after abbreviation periods."""
    out = text
    if out and out[0].islower():
        out = out[0].upper() + out[1:]
    def _repl(m):
        punct = m.group(1)
        # look back to the token before the punctuation
        before = out[:m.start(1)]
        tok = re.search(r'([A-Za-z0-9]+)\.?$', before)
        if punct == '.' and tok:
            word = tok.group(1).lower()
            if len(word) == 1 or word in _ABBREVIATIONS:
                return punct + ' ' + m.group(2)  # don't capitalize
        return punct + ' ' + m.group(2).upper()
    return re.sub(r'([.!?])(\s+[a-z])', _repl, out)


# Words that may legitimately appear doubled — everything else gets
# deduplicated. This is a deliberately small set: "had had", "that that",
# "so so", "no no", "very very", "now now", "there there", etc.
_DUP_ALLOW = {
    'had', 'that', 'so', 'no', 'yes', 'well', 'very', 'really',
    'ok', 'okay', 'now', 'there',
}


_HOMOPHONE_PATTERNS = [
    # your/you're
    (r'\byour\s+(going|welcome|right|wrong|sure|certain|probably|never|always|correct|incorrect|kidding|joking|saying|asking|telling|invited|wanted|needed|coming|leaving)\b', r"you're \1"),
    (r"\byou're\s+(book|name|email|phone|address|car|house|home|job|work|idea|plan|project|team|colleague|boss|friend|family|kids|children|dog|cat|keys|wallet|money|time|schedule|appointment|meeting|question|answer|problem|issue|fault|turn)\b", r"your \1"),
    # there/their/they're
    (r'\btheir\s+(going|coming|leaving|right|wrong|sure|probably|never|always|asking|telling|kidding|saying|joking)\b', r"they're \1"),
    (r"\bthey're\s+(book|name|email|phone|address|car|house|home|job|work|idea|plan|project|team|boss|friend|family|kids|children|dog|cat|keys|money|time|meeting|question|answer|problem|issue|fault|turn|apartment|office)\b", r"their \1"),
    (r'\bthere\s+(book|name|email|phone|address|car|house|home|job|work|idea|plan|project|team|boss|friend|family|kids|children|dog|cat|keys|money|time|meeting|question|answer|problem|issue|fault|turn)\b', r"their \1"),
    # its/it's
    (r"\bits\s+(a|an)\b", r"it's \1"),
    (r"\bit's\s+(tail|name|color|colour|size|shape|smell|taste|sound|price|cost|value|purpose|owner|parents|mother|father|sister|brother|base|root|core|center|centre|surface|edge|side|end|start|beginning|history|meaning|style|design|behavior|behaviour)\b", r"its \1"),
    # let's go ("lets go" -> "let's go")
    (r'\blets\s+(go|see|do|try|have|get|start|begin|make|take|put|say|talk|walk|run|eat|play|watch|listen|think|hope|ask|tell|show)\b', r"let's \1"),
    # no -> know before question words ("let me no" -> "let me know",
    # "no what to say" -> "know what to say")
    (r'\blet\s+me\s+no\b', 'let me know'),
    (r'\bno\s+(what|who|where|when|why|how)\b', r'know \1'),
    # their/there before be-verbs and common verbs
    (r'\btheir\s+(are|is|was|were|will|would|could|should|might|may)\b', r'there \1'),
    (r'\bthere\s+(going|coming|leaving|right|wrong|sure|asking|telling|kidding|joking)\b', r"they're \1"),
    # its before -ing verbs ("its looking" -> "it's looking") and common
    # adjectives/states ("its important" -> "it's important")
    (r"\bits\s+(looking|going|coming|working|becoming|starting|ending|taking|making|getting|doing|being)\b", r"it's \1"),
    (r"\bits\s+(important|true|great|good|bad|time|ok|okay|fine|not|never|always|possible|impossible|likely|unlikely|clear|obvious|certain|sure|hard|easy|wrong|right|worth|over|under|back|here|there|ready|done|finished|up|down|out|in|nice|fun|hard|tough|difficult|easy|different|same)\b", r"it's \1"),
    # "ill" before a verb is "I'll" ("ill be there") but "he is ill" is correct
    (r'\b(?:i|i\'?)ll\s+(be|go|see|do|have|get|come|take|make|tell|show|say|try|let|put|help|buy|find|know|want|need|call|send|bring|keep|hold|start|stop|give|ask|walk|run|look|wait|check|read|write)\b', r"I'll \1"),
    # could/would/should/might of + past participle -> have
    # ("could of course" is legitimate — "course" ends in -se)
    (r'\b(could|would|should|might|must|may)\s+of\s+([a-z]+?(?:ed|en|d|t|one|wn))\b', r'\1 have \2'),
    # to -> too before degree words; "me to" at sentence end
    (r'\bto\s+(much|late|soon|early|far|many|long|hard|fast|slow|little|big|small|hot|cold|often|rarely|expensive|tired|excited)\b', r'too \1'),
    (r'\b(me|you|him|her|us|them)\s+to\s*[.!?,;:]?$', r'\1 too'),
    # then/than
    (r'\b(better|worse|more|less|rather|other|bigger|smaller|faster|slower|taller|shorter|older|younger|higher|lower|earlier|later|longer|shorter|easier|harder)\s+then\b', r'\1 than'),
    (r'\b(back|since|by|until|from|before|after)\s+than\b', r'\1 then'),
    # lose/loose
    (r'\bloose\s+(weight|control|interest|focus|track|touch|your|my|the|a|an|his|her|their|its|our|ground|balance)\b', r'lose \1'),
    (r'\blose\s+(fit|clothing|clothes|jeans|shirt|dress|pants|trousers|shoes|change|coins)\b', r'loose \1'),
    (r'\blose\s+on\s+(me|you|him|her|us|them)\b', r'loose on \1'),
    # quiet/quite
    (r'\bbe\s+quite\s*$', 'be quiet'),
    (r'\bbe\s+quite\s+(please|now|everyone|class|kids|children)\b', r'be quiet \1'),
    (r'\bquiet\s+(good|bad|big|small|interesting|difficult|easy|different|similar|long|short|new|old|sure|certain|clear|large|high|low|nice|impressive|remarkable|unusual|common|rare)\b', r'quite \1'),
    # weather/whether
    (r'\bweather\s+or\s+not\b', 'whether or not'),
    # accept/except
    (r'\bexcept\s+(the|this|an|a|my|your|our|their|his|her|its)\s+(offer|invitation|job|challenge|responsibility|role|task|position|award|nomination|proposal)\b', r'accept \1 \2'),
    (r'\baccept\s+for\b', 'except for'),
    # passed/past
    (r'\b(walked|ran|drove|went|driven|ridden)\s+passed\b', r'\1 past'),
    # less/fewer with countable nouns
    (r'\bless\s+(people|things|items|cars|books|errors|mistakes|problems|issues|users|members|employees|students|hours|days|weeks|months|years|dollars|tables|chairs|buildings|cities|countries|questions|answers|ideas|suggestions|comments|reasons|options|choices)\b', r'fewer \1'),
    # desert/dessert
    (r'\b(had|have|eat|ate|eaten|served|ordered|shared)\s+desert\b', r'\1 dessert'),
    # breath/breathe
    (r'\b(?:can\'?t|cannot|can not)\s+breath\b', "can't breathe"),
    (r'\btake\s+a\s+breathe\b', 'take a breath'),
    # affect/effect (verb vs noun)
    (r'\beffect\s+(the|our|your|their|his|her|its|a|an)\s+(outcome|results?|behavior|behaviour|decision|performance|health|mood|perception|judgment|choices?|people|children|students|workers|employees|users|sales|profits|growth|development|learning|memory|attention|sleep|appetite)\b', r'affect \1 \2'),
    (r'\bthe\s+affect\b', 'the effect'),
    # peace/piece
    (r'\bpeace\s+of\s+(cake|bread|paper|furniture|advice|news|art|work|pie|cheese|land)\b', r'piece of \1'),
    # write/right
    (r'\bwrite\s+now\b', 'right now'),
    (r'\bright\s+(a|an|the)\s+(letter|book|email|note|report|essay|article|poem|message)\b', r'write \1 \2'),
    # role/roll
    (r'\b(main|key|leading|important|major|supporting|central|vital)\s+roll\b', r'\1 role'),
    (r'\brole\s+(the|a|an)\s+(dice|drum|tape|camera|credits|film)\b', r'roll \1 \2'),
    # sale/sail
    (r'\bsale\s+(the|a|an|his|her|their|my|your|our)\s+(boat|ship|yacht|vessel)\b', r'sail \1 \2'),
    (r'\bfor\s+sail\b', 'for sale'),
    # steal/steel
    (r'\bsteel\s+(the|a|an|my|your|his|her|their)\s+(show|heart|idea|thunder|spotlight|base|scene)\b', r'steal \1 \2'),
    (r'\bof\s+steal\b', 'of steel'),
    # two -> to/too
    (r'\btwo\s+(go|see|do|have|get|come|take|make|be|try|ask|tell|show|say|walk|run|talk|eat|play|watch|listen|learn|work|help|call|buy|find)\b', r'to \1'),
    (r'\b(me|you|him|her|us|them)\s+two\b', r'\1 too'),
    # whose -> who's (before verbs/states)
    (r'\bwhose\s+(coming|going|there|here|next|first|right|wrong|ready|tired|hungry|thirsty|happy|sad|late|early|home|outside|inside|responsible|in\s+charge)\b', r"who's \1"),
    # apart of -> a part of
    (r'\bapart\s+of\b', 'a part of'),
    # one upon -> once upon
    (r'\bone\s+upon\b', 'once upon'),
    # maybe / may be
    (r'\bit\s+maybe\b', 'it may be'),
    (r'\bmay\s+be\s+(we|i|you|they|he|she|it)\b', r'maybe \1'),
    # site seeing -> sightseeing
    (r'\bsite\s+seeing\b', 'sightseeing'),
    # threw -> through (before time spans)
    (r'\bthrew\s+(the|this|that|these|those)\s+(years?|months?|weeks?|days?|decades?|centuries?)\b', r'through \1 \2'),
    # tail/tale (wag its tale -> tail)
    (r'\b(wag|wagged)\s+(its|the|his|her)\s+tale\b', r'\1 \2 tail'),
    # your the -> you're the / its the -> it's the
    (r'\byour\s+the\b', "you're the"),
    (r'\bits\s+the\b', "it's the"),
    # merged two-word compounds ("some thing" -> "something")
    (r'\bsome\s+thing\b', 'something'),
    (r'\bany\s+thing\b', 'anything'),
    (r'\bevery\s+thing\b', 'everything'),
    (r'\bsome\s+one\b', 'someone'),
    # subject-verb agreement (narrow, safe patterns)
    (r'\bdiscus\s+the\b', 'discuss the'),
    (r'\bthere\s+is\s+(many|several|a\s+few|numerous|various|lots|hundreds|thousands|millions)\s+', r'there are \1 '),
    (r'\ba\s+lots\s+of\b', 'a lot of'),
    (r'\bmore\s+(better|worse|bigger|smaller|faster|slower|taller|shorter|older|younger|higher|lower|easier|harder|further|farther|quieter|louder|longer|shorter|warmer|colder|darker|lighter)\b', r'\1'),
    (r'\bi\s+seen\b', 'I saw'),
    (r'\bi\s+done\b', 'I did'),
    (r'\b(have|has)\s+saw\b', r'\1 seen'),
    (r'\b(he|she|it)\s+don\'t\b', r"\1 doesn't"),
    (r'\b(i|you|we|they)\s+doesn\'t\b', r"\1 don't"),
    (r'\b(they|we|you)\s+was\b', r'\1 were'),
    (r'\b(he|she|it|i)\s+were\b', r'\1 was'),
    # principle/principal (school/office head), stationary/stationery (shop)
    (r'\bprinciple\s+of\s+(the\s+)?(school|office|company|department|university|college)\b', r'principal of \1\2'),
    (r'\bstationary\s+(store|shop|supplies)\b', r'stationery \1'),
    # compliment/complement, council/counsel, ensure/insure, brake/break
    (r'\bcompliment\s+(the|my|your|his|her|their|our)\s+(colors?|colours?|flavors?|flavours?|design|team|skills?|effort|work|flavour|color)\b', r'complement \1 \2'),
    (r'\bcompliment\s+each\s+other\b', 'complement each other'),
    (r'\blegal\s+council\b', 'legal counsel'),
    (r'\binsure\s+that\b', 'ensure that'),
    (r'\bbrake\s+(the|a|an|my|your|his|her|their|our)\s+(glass|window|mirror|plate|vase|bottle|record|promise|rule|law|silence|ice|news|heart|fall|even|tie|fast|loose)\b', r'break \1 \2'),
    # pedal/peddle, shear/sheer, stake/steak, pore/pour
    (r'\bpeddle\s+(the|a|an|his|her|their|my|your)\s+(bike|bicycle|car|boat|kayak)\b', r'pedal \1 \2'),
    (r'\bsheer\s+(the|a|an|his|her|their|my|your)\s+(sheep|wool|fleece|lambs?)\b', r'shear \1 \2'),
    (r'\bsteak\s+(your|my|his|her|their|our)\s+claim\b', r'stake \1 claim'),
    (r'\bpour\s+over\s+(the|a|an|my|your|his|her|their|our|this|that)\s+(book|books|document|documents|report|reports|page|pages|text|letter|file|files|notes?|details?|manuscript|article)\b', r'pore over \1 \2'),
    (r'\bpoured\s+over\s+(the|a|an|my|your|his|her|their|our|this|that)\s+(book|books|document|documents|report|reports|page|pages|text|letter|file|files|notes?|details?|manuscript|article)\b', r'pored over \1 \2'),
    (r'\bpouring\s+over\s+(the|a|an|my|your|his|her|their|our|this|that)\s+(book|books|document|documents|report|reports|page|pages|text|letter|file|files|notes?|details?|manuscript|article)\b', r'poring over \1 \2'),
    # soar/sore, waist/waste, peak/peek, fair/fare
    (r'\b(muscles?|throat|back|neck|feet|shoulders?|knees?|arms?|legs?|eyes?|joints?)\s+are\s+soar\b', r'\1 are sore'),
    (r'\bwaist\s+((?:your|my|his|her|their|our|the|a|an)\s+)?(time|money|effort|resources?|energy|food|water|paper|space)\b', r'waste \1\2'),
    (r'\bpeak\s+(at|into|through|inside)\b', r'peek \1'),
    (r'\b(bus|taxi|train|air)\s+fair\b', r'\1 fare'),
    # homophone wave 5
    (r'\bbare\s+with\s+(me|us|you|him|her|them)\b', r'bear with \1'),
    (r'\bdual\s+to\b', 'duel to'),
    (r'\bdiscreet\s+(math|mathematics)\b', r'discrete \1'),
    (r'\billicit\s+(a|an|the|responses?|reactions?|information|support|comments?|feedback)\b', r'elicit \1'),
    (r'\bflaunt\s+(the|rules?|law|laws|regulations?|conventions?)\b', r'flout \1'),
    (r'\bgrisly\s+bear\b', 'grizzly bear'),
    (r'\bleach\s+off\b', 'leech off'),
    (r'\bmute\s+point\b', 'moot point'),
    (r'\bpalette\s+cleanser\b', 'palate cleanser'),
    (r'\bpeaked\s+(my|your|his|her|their|our)\s+interest\b', r'piqued \1 interest'),
    (r'\bpeaking\s+(my|your|his|her|their|our)\s+interest\b', r'piquing \1 interest'),
    (r'\bpeak\s+(my|your|his|her|their|our)\s+interest\b', r'pique \1 interest'),
    (r'\bproceed\s+(the|a|an)\s+(event|meeting|ceremony|speech|presentation|announcement|results?|discussion)\b', r'precede \1 \2'),
    (r'\bproscribe\s+(medication|drugs?|medicine|treatment|pills?)\b', r'prescribe \1'),
    (r'\breign\s+in\b', 'rein in'),
    (r'\btorturous\s+(path|route|journey|winding|curves?)\b', r'tortuous \1'),
    (r'\bweary\s+of\b', 'wary of'),
    # ── homophone wave 6 ───────────────────────────────────────────────────
    # hear/here ("here that/about" -> "hear"; "hear is" -> "here is")
    (r'\bhere\s+(that|about)\b', r'hear \1'),
    (r'\bhear\s+(is|are|was|were|comes?|goes?)\b', r'here \1'),
    # heard/herd ("i herd you had..." / "herd the news")
    (r'\bherd\s+(you|him|her|them|me|us|it)\s+(had|have|has|did|was|were|are|is|got|said|went|came|left|talked|spoke|been|will|would|could|moved|found|saw|heard)\b', r'heard \1 \2'),
    (r'\bherd\s+(the|that|this|about)\s+(news|rumor|rumour|story|report|announcement|word|update)\b', r'heard \1 \2'),
    # capital/capitol: "capitol of X" is always a misspelling (the building
    # is "the Capitol" / "Capitol Hill", never "capitol of")
    (r'\bcapitol\s+of\b', 'capital of'),
    # idle/idol
    (r'\bidol\s+(threat|threats|time|times|hands|minds?|engine|engines|machinery|workers?|rumors?|rumours?|gossip|chatter)\b', r'idle \1'),
    # coarse/course
    (r'\bcourse\s+(sand|salt|grit|texture|fabric|cloth|wool|hair|skin|fur|beard|canvas|linen|ground)\b', r'coarse \1'),
    (r'\bin\s+due\s+coarse\b', 'in due course'),
    # vain/vein (a weather vane stays)
    (r'\bvane\s+(attempt|attempts|effort|efforts|hope|hopes|search|struggle|glory|pursuit|trying)\b', r'vain \1'),
    (r'\bin\s+the\s+same\s+vane\b', 'in the same vein'),
    # soul/sole
    (r'\bsoul\s+(purpose|reason|aim|goal|intention|motivation|objective|survivor|owner|heir|focus|point|cause|function|motive)\b', r'sole \1'),
    # yoke/yolk
    (r'\byolk\s+(the|a|an|oxen|ox|cattle|team|horses?|mules?|donkeys?)\b', r'yoke \1'),
    # metal/mettle
    (r'\b(show|prove|test|demonstrate)\s+(your|my|his|her|their|our)\s+metal\b', r'\1 \2 mettle'),
    # profit/prophet
    (r'\bfalse\s+profit\b', 'false prophet'),
    # naval/navel
    (r'\bnavel\s+(battle|battles|fleet|fleets|forces?|base|bases|operations?|engagement|engagements|strategy|superiority|power|warfare)\b', r'naval \1'),
    # flair/flare
    (r'\bflare\s+for\s+(design|drama|fashion|style|language|words|theatrics|comedy|music|art|writing|storytelling|detail|showmanship)\b', r'flair for \1'),
    # hoard/horde
    (r'\bhorde\s+of\s+(treasure|treasures|gold|silver|coins|jewels|jewelry|supplies|goods|weapons|money|riches|food|grain)\b', r'hoard of \1'),
    (r'\bhoard\s+of\s+(zombies|people|barbarians|huns|riders?|fans|tourists|crowds?|insects|rats?|bees|ants|locusts)\b', r'horde of \1'),
    # cue/queue
    (r'\bqueue\s+(the|a|an|our|your|this|that)\s+(music|song|track|video|clip|sound|sounds|lights?|lighting|scene|scenes|entrance|intro)\b', r'cue \1 \2'),
    # eminent/imminent
    (r'\bimminent\s+(scholar|scholars|scientist|scientists|professor|professors|author|authors|writer|writers|lawyer|lawyers|judge|judges|figure|figures|historian|historians|artist|artists|musician|musicians|expert|experts|authority|authorities|physician|physicians|surgeon|surgeons|statesman|diplomat|diplomats)\b', r'eminent \1'),
    # incite/insight
    (r'\binsight\s+(a|an|the|this|that|riots?|rebellion|revolt|uprising|protests?|violence|anger|hatred|fear|chaos|panic|trouble|conflict|resistance)\b', r'incite \1'),
    # canvas/canvass
    (r'\bcanvass\s+(the|a|an|this|that|these|those|my|your|his|her|their|our)\s+(walls?|tent|painting|paintings|stretcher|stretchers|tarp|tarpaulin|sail|sails)\b', r'canvas \1 \2'),
    # strait/straight (Strait of Gibraltar stays)
    (r'\bstrait\s+(answer|answers|forward|up|ahead|talk|talking|shooter|shooters?|line|lines|path|road|a|to|from|at|into|out|off|on)\b', r'straight \1'),
    (r'\bstraight\s+of\s+(gibraltar|hormuz|ormuz|malacca|dover|messina|magellan|georgia|florida|bosporus|bosphorus|mackinac|canso|belle|hainan|taiwan)\b', r'strait of \1'),
    # hanger/hangar
    (r'\b(aircraft|airplane|airplanes|planes?|jets?|helicopters?|military|bombers?|fighters?)\s+hanger\b', r'\1 hangar'),
    # censor/sensor
    (r'\b(motion|light|heat|infrared|proximity|temperature|pressure|touch|smoke|speed|image|ultrasonic|acoustic|chemical|optical|magnetic|humidity)\s+censor\b', r'\1 sensor'),
    # band/banned
    (r'\bbanned\s+of\s+(musicians|brothers|thieves|gorillas|merry|pirates|outlaws|rebels|gypsies|robbers|vandals)\b', r'band of \1'),
    # board/bored ("on bored" and "bored game"; "get bored" stays)
    (r'\bbored\s+(game|games|directors|trustees|governors|meeting|meetings|members|room|rooms)\b', r'board \1'),
    (r'\bon\s+bored\b', 'on board'),
    # loathe/loath
    (r'\bloathe\s+to\s+(admit|do|say|go|accept|believe|agree|leave|make|tell|ask|wait|stay|return|move|share|change|miss|relive)\b', r'loath to \1'),
    # moral/morale (only after group nouns — "the moral of the story" and
    # "moral high ground" stay untouched)
    (r'\b(team|company|staff|employees?|students?|players?|workers?|office|workplace|army|troops?|crew|crews|squads?)\s+moral\s+(is|was|are|were|dropping|dropped|improving|improved|boosted|plummeted|plummeting|suffering|suffers|sagged|sagging|rising|sank|dipped|soared|collapsed|rose|fell)\b', r'\1 morale \2'),
    # principal/principle (roles, reasons, characters — not "of the school")
    (r'\bprinciple\s+(concern|concerns|reason|reasons|aim|aims|goal|goals|objective|objectives|purpose|source|cause|factor|factors|issue|issues|point|points|finding|findings|character|characters|actor|actors|dancer|dancers|investor|investors|engineer|engineers|architect|architects|designer|designers|spokesman|spokeswoman|spokesperson|contributor|contributors|role|roles|focus|means|theme|motif|ingredient|ingredients|trait|traits)\b', r'principal \1'),
    # taught/taut
    (r'\btaut\s+(me|us|you|him|her|them|the|a|an)\s+(class|classes|students|children|kids|group|lesson|lessons|course|courses|subject|subjects|everything|something|nothing|math|history|science|english|art|music|how|to|that|this)\b', r'taught \1 \2'),
    # troop/troupe
    (r'\btroop\s+of\s+(actors|actresses|performers|dancers|players|clowns|jugglers|acrobats|thespians|musicians|singers)\b', r'troupe of \1'),
    # phase/faze
    (r'\bunphased\b', 'unfazed'),
    (r'\bphased\s+by\s+((?:the|a|an|any)\s+)?(noise|criticism|pressure|setbacks?|failure|comments?|words|teasing|mockery|threats?|trouble|fear|scares?|rejection|delays?)\b', r'fazed by \1\2'),
    # one in the same / everytime
    (r'\bone\s+in\s+the\s+same\b', 'one and the same'),
    (r'\beverytime\b', 'every time'),
    # ── grammar & word-choice wave 8 ──────────────────────────────────────
    # "learn me" / "borrow me" (dialect errors)
    (r'\blearn\s+(me|us)\b', r'teach \1'),
    (r'\bborrow\s+(me|us)\b', r'lend \1'),
    # didn't knew / doesn't knows / don't knows
    (r"\b(didn't|doesn't|don't)\s+(knew|knows)\b", r'\1 know'),
    (r"\b(didn't|doesn't|don't)\s+saw\b", r'\1 see'),
    (r"\b(didn't|doesn't|don't)\s+(went|gone)\b", r'\1 go'),
    (r"\b(didn't|doesn't|don't)\s+(did|does|done)\b", r'\1 do'),
    # could care less -> couldn't care less
    (r'\bcould\s+care\s+less\b', "couldn't care less"),
    # lay down -> lie down (after desire/future verbs; "lay down the law"
    # and "laid down" stay)
    (r'\b((?:going|go|gonna|want|wants|wanted|need|needs|needed|should|would|could|can|will|let\'?s|try|tried|trying)\s+(?:to\s+|and\s+)?)lay\s+down\b', r'\1lie down'),
    # awhile -> a while
    (r'\bfor\s+awhile\b', 'for a while'),
    (r'\bawhile\s+ago\b', 'a while ago'),
    # "everyday" as an adverb ("I go there everyday." -> "every day";
    # "everyday life" stays)
    (r'\beveryday\s*([.!?;:]|$)', r'every day\1'),
    # none the less -> nonetheless
    (r'\bnone\s+the\s+less\b', 'nonetheless'),
    # ── homophone wave 9 ──────────────────────────────────────────────────
    # wait/weight
    (r'\bwait\s+(loss|lifting|training|room|machine|gain|gains|losses|watchers)\b', r'weight \1'),
    (r'\bweight\s+(for|a\s+minute|a\s+second|a\s+moment|a\s+bit|here|there|up|outside|until|till)\b', r'wait \1'),
    (r'\blose\s+wait\b', 'lose weight'),
    # pray/prey
    (r'\bpray\s+on\s+(the|a|an|their|smaller|weaker|vulnerable|innocent|unsuspecting)\b', r'prey on \1'),
    (r'\bprey\s+for\s+(the|a|an|your|my|our|their|his|her|guidance|forgiveness|mercy|peace|strength)\b', r'pray for \1'),
    # leak/leek
    (r'\bleek\s+(the|a|an|my|your|his|her|their|our|this|that)\s+(info|information|data|secrets?|details?|news|story|plans?|documents?|report)\b', r'leak \1 \2'),
    # flour/flower
    (r'\bflour\s+(arrangement|arrangements|garden|bed|beds|pot|pots|vase|shop|show|crown|child|girl|boy)\b', r'flower \1'),
    # pair/pare/pear
    (r'\bpare\s+of\s+(shoes?|socks?|gloves?|pants|jeans|trousers|shorts|scissors|earrings|sneakers|boots|eyes|hands|feet|dice|wings)\b', r'pair of \1'),
    (r'\bpear\s+of\s+(shoes?|socks?|gloves?|pants|jeans|trousers|shorts|scissors|earrings|sneakers|boots|eyes|hands|feet|dice|wings)\b', r'pair of \1'),
    (r'\bpair\s+(the|a|an|your|my|his|her|their|our|this|that)\s+(apple|apples|nails?|claws?|potatoes?|carrots?|fruit|fruits?|pears?)\b', r'pare \1 \2'),
    # rode/road
    (r'\broad\s+(the|a|an|my|your|his|her|their|our)\s+(horse|bike|bicycle|motorcycle|mule|donkey|camel|wave|waves)\b', r'rode \1 \2'),
    (r'\brode\s+(to|down|up|along|across|through|home|back|ahead|off|over|past|toward|towards|into)\b', r'road \1'),
    # week/weak
    (r'\bweak(s?)\s+(from\s+now|ago|after\s+next|of\s+mondays?|of\s+fridays?|before\s+last|before\s+next|ahead|after)\b', r'week\1 \2'),
    # feat/feet
    (r'\bfeet\s+of\s+(strength|agility|endurance|skill|daring|bravery|courage|engineering|will)\b', r'feat of \1'),
    # hole/whole
    (r'\bwhole\s+(in|through|in\s+the|in\s+my|in\s+your|in\s+his|in\s+her|in\s+their|in\s+our|in\s+this|in\s+that)\b', r'hole \1'),
    (r'\bhole\s+(new|lot|world|time|bunch|thing|things|story|family|team|class|day|week|year|truth|point)\b', r'whole \1'),
    # pole/poll
    (r'\bpoll\s+(vault|vaulting|position|vaulter|jumping|jump|tent|fishing|fisherman|dancing|dancer)\b', r'pole \1'),
    (r'\b(take|takes|took|conduct|conducted|run|ran|hold|held)\s+a\s+pole\b', r'\1 a poll'),
    # knight/night
    (r'\bnight\s+in\s+shining\s+armor\b', 'knight in shining armor'),
    # ── homophone wave 10 ─────────────────────────────────────────────────
    # advice/advise
    (r'\badvice\s+(me|us|him|her|them|you)\b', r'advise \1'),
    (r'\b(a|an|the|good|great|best|bad|some|any|my|your|his|her|their|our|expert|professional|legal|medical)\s+advise\b', r'\1 advice'),
    # device/devise
    (r'\b(a|an|the|this|that|my|your|his|her|their|our|new|old|small|large|electronic|digital|mobile|portable|handheld)\s+devise\b', r'\1 device'),
    (r'\bdevice\s+(a|an|the|our|your|my|his|her|their|this|that)\s+((?:[a-z]+\s+)?)(plan|plans|strategy|strategies|scheme|schemes|method|methods|way|ways|approach|system)\b', r'devise \1 \2\3'),
    # lay down -> lie down, extended to "lay on/in/here/there/back"
    (r'\b((?:going|go|gonna|want|wants|wanted|need|needs|needed|should|would|could|can|will|let\'?s|try|tried|trying)\s+(?:to\s+|and\s+)?)lay\s+(down|on\s+(?:the|a|an|my|your|his|her|their|our)|in\s+(?:the|a|an|my|your|his|her|their|our)|here|there|back)\b', r'\1lie \2'),
    # sit down ("please set down." -> "please sit down."; "set down the book" stays)
    (r'\b((?:please|go|going|gonna|want|wants|wanted|need|needs|needed|should|would|could|can|will|let\'?s|try|tried|trying|come)\s+(?:to\s+|and\s+)?)set\s+down\b(?=[.!?,;:]|$)', r'\1sit down'),
    # sight/site ("the sight of the accident" -> "the site of the accident")
    (r'\bsight\s+of\s+(?:the|a|an|this|that|my|your|his|her|their|our|new|old|former|current)\s+(building|construction|accident|crash|attack|battle|fire|explosion|murder|crime|landing|launch)\b', r'site of the \1'),
    # rain/reign
    (r'\brain\s+supreme\b', 'reign supreme'),
    (r'\breign\s+(drops?|fall|falls|falling|storm|storms|forest|forests|water|waters|cloud|clouds)\b', r'rain \1'),
    # seem/seam
    (r'\b(a|an|the|this|that|my|your|his|her|their|our)\s+seem\s+(in|of|along|down|torn|ripped|split)\b', r'\1 seam \2'),
    # sweet/suite
    (r'\bsweet\s+of\s+(rooms?|offices?|apartments?|furniture)\b', r'suite of \1'),
    (r'\bsuite\s+(tea|potato|potatoes|corn|treat|treats|tooth|toothpaste|smell|smells|taste|tastes|voice|music|melody)\b', r'sweet \1'),
    # ── homophone wave 11 ─────────────────────────────────────────────────
    # affect -> effect as a noun ("have an affect on")
    (r'\b(an|the|no|some|any|a|positive|negative|direct|significant|major|minor|long-term|short-term|lasting|big|small|huge|real|strong|weak)\s+affect\s+on\b', r'\1 effect on'),
    # ensure -> insure for possessions
    (r'\bensure\s+(the|a|an|my|your|his|her|their|our|this|that)\s+(car|cars|house|home|property|properties|vehicle|vehicles|boat|boats|jewelry|life)\b', r'insure \1 \2'),
    # gorilla -> guerrilla (warfare)
    (r'\bgorilla\s+(warfare|tactics|fighters?|warriors?|forces?|war|attacks?|groups?|movement|insurgency|leader|leaders|fighters?)\b', r'guerrilla \1'),
    # miner/minor (both directions)
    (r'\bminor\s+(in\s+the\s+mines?|working|works|digging|digs|shaft|tunnel|tunnels?|shafts?)\b', r'miner \1'),
    (r'\bminer\s+(issue|issues|problem|problems|role|roles|part|detail|details|point|points|player|players|character|characters|offense|offenses|crime|crimes|child|children|key|keys|scale|scales|ity)\b', r'minor \1'),
    # team/teem
    (r'\bteem\s+(player|players|member|members|leader|leaders|spirit|work|effort|sport|sports|meeting|meetings|tryouts?|captain|captains)\b', r'team \1'),
    # breath -> breathe (verb contexts)
    (r'\bbreath\s+(deeply|in|out|slowly|heavily|easily|normally|again|through\s+the)\b', r'breathe \1'),
    # ── homophone wave 12 ─────────────────────────────────────────────────
    # its been -> it's been
    (r"\bits\s+been\b", "it's been"),
    # whether -> weather before forecast nouns
    (r'\bwhether\s+(report|reports|forecast|forecasts|station|stations|man|woman|channel|map|maps|conditions|pattern|patterns|system|systems|service|services)\b', r'weather \1'),
    # two -> too before degree words ("two small dogs" stays)
    (r'\btwo\s+(many|much|late|soon|early|far|often)\b', r'too \1'),
    # ── homophone wave 13 ─────────────────────────────────────────────────
    # cereal/serial
    (r'\bcereal\s+(number|numbers|killer|killers|murderer|murderers|port|ports|code|codes|connection|connections)\b', r'serial \1'),
    (r'\bserial\s+(for\s+breakfast|bowl|box|boxes|brand|commercial|for\s+lunch|aisle|isles?)\b', r'cereal \1'),
    # complementary/complimentary
    (r'\bcomplimentary\s+(angles?|colors?|colours?|pairs?|genes?|proteins?|colors?|palette|schemes?|goods?|services?|products?|items?|wines?|drinks?|tickets?|breakfast|samples?|passes?)\b', r'complementary \1'),
    (r'\bcomplementary\s+(tickets?|drinks?|wine|coffee|breakfast|snacks?|lunch|dinner|passes?|admission|gifts?|samples?|subscriptions?|copies?)\b', r'complimentary \1'),
    # wave/waive
    (r'\bwaive\s+(at|to|hello|goodbye|good-bye|the\s+crowd|the\s+fans?|the\s+flag|goodbye)\b', r'wave \1'),
    (r'\bwave\s+(the|a|an|my|your|his|her|their|our)\s+(fee|fees|requirement|requirements|rights?|immunity|penalty|penalties|rule|rules|claim|claims)\b', r'waive \1 \2'),
    # alter/altar
    (r'\balter\s+(boy|boys|girl|girls|server|servers|bread|wine|of\s+the\s+church)\b', r'altar \1'),
    (r'\baltar\s+(the|a|an|my|your|his|her|their|our|this|that)\s+(course|plan|plans|route|schedule|design|program|programs|approach|behavior|behaviour)\b', r'alter \1 \2'),
    # currant/current
    (r'\bcurrant\s+(events?|affairs|situation|status|price|prices|date|time|year|month|week|trend|trends|news|edition|issue|flow|of\s+electricity|temperature|weather)\b', r'current \1'),
    (r'\bcurrent\s+(bun|buns|cake|cakes|pie|tart|tarts|jam|preserves|bush|bushes|bread)\b', r'currant \1'),
    # ascent/assent
    (r'\bassent\s+((?:to\s+the|of\s+the))\s+(top|summit|peak|mountain|hill|throne|mount)\b', r'ascent \1 \2'),
    (r'\bascent\s+to\s+(the|a|an|this|that|my|your|his|her|their|our)\s+(plan|plans|proposal|proposals|suggestion|suggestions|request|requests|agreement|treaty|bill|law|resolution)\b', r'assent to \1 \2'),
    # tide/tied
    (r'\btide\s+(up|down|to\s+the|into\s+knots?|together|off|in\s+knots?)\b', r'tied \1'),
    (r'\btied\s+of\s+(the\s+)?(ocean|sea|river|waters?|current|currents)\b', r'tide of \1\2'),
    # ── homophone wave 14 ─────────────────────────────────────────────────
    # plain/plane
    (r'\bplain\s+(ticket|tickets|flight|flights|crash|crashes|landing|landings|mode|journey)\b', r'plane \1'),
    (r'\bplane\s+and\s+simple\b', 'plain and simple'),
    (r'\bplane\s+(english|text|clothes?|water|sight|truth|vanilla|old|white|black)\b', r'plain \1'),
    # allowed/aloud
    (r'\baloud\s+to\s+(go|stay|come|leave|enter|play|use|have|take|watch|see|join|speak|drive|vote|return|bring|buy)\b', r'allowed to \1'),
    (r'\b(said|read|speak|spoke|laughed|laugh|sang|sing|shout|shouted|cried|cry|muttered|wondered|counted|recited|whispered)\s+(it\s+)?allowed\b', r'\1 \2aloud'),
    # bear/bare
    (r'\bbear\s+(minimum|necessities|bones|hands|feet|chest|knuckle|cupboards?|shelves?|floor|walls?|truth|essentials)\b', r'bare \1'),
    # later/latter
    (r'\bthe\s+later\s+(one|half|part|option|choice|chapter|version|example|two|three)\b', r'the latter \1'),
    (r'\bsee\s+you\s+latter\b', 'see you later'),
    (r'\bsooner\s+or\s+latter\b', 'sooner or later'),
    (r'\blatter\s+(today|tonight|this\s+week|this\s+month|this\s+year)\b', r'later \1'),
    # seas/seize
    (r'\bseas\s+(the|a|an|every|any)\s+(day|moment|opportunity|chance|initiative|power|control|attention)\b', r'seize \1 \2'),
    # paws/pause
    (r'\b(hit|hits|hitting|press|presses|pressing|push|pushes|pushing)\s+paws\b', r'\1 pause'),
    # tacks/tax
    (r'\bsales\s+tacks\b', 'sales tax'),
    (r'\bincome\s+tacks\b', 'income tax'),
    (r'\btacks\s+(rate|rates|return|returns|payer|payers|forms?|laws?|breaks?|deduction|deductions|credit|credits|bill|code|system|season)\b', r'tax \1'),
    # sell/cell
    (r'\bsell\s+(phone|phones|tower|towers|membrane|membranes|walls?|division|biology|block|blocks|signals?)\b', r'cell \1'),
    (r'\bcell\s+(the|a|an|my|your|his|her|their|our|this|that)\s+(products?|goods?|house|car|cars|stocks?|shares?|tickets?|books?|business)\b', r'sell \1 \2'),
    # forth/fourth
    (r'\bback\s+and\s+fourth\b', 'back and forth'),
    (r'\bforth\s+(floor|grade|quarter|birthday|anniversary|inning|symphony|estate|dimension|chapter|generation)\b', r'fourth \1'),
    # son/sun
    (r'\bthe\s+son\s+is\s+shining\b', 'the sun is shining'),
    (r'\bson\s+(screen|flower|flowers|glasses|light|rays?)\b', r'sun \1'),
    (r'\b(my|your|his|her|their)\s+sun\s+(is|was|are|were|has|had|goes|go|plays?|attends?|lives?|works?)\b', r'\1 son \2'),
    # ate/eight
    (r"\bate\s+(o'?clock|hours?|days?|weeks?|months?|years?|minutes?|am|pm|dollars?|percent|students?|items?|miles?|pounds?)\b", r'eight \1'),
    (r'\beight\s+(dinner|lunch|breakfast)\b', r'ate \1'),
    (r'\beight\s+(the|a|an|my|your|his|her|their|our|some|all)\s+(dinner|lunch|breakfast|snacks?|food|cake|pizza|sushi|sandwich|sandwiches|apples?|bananas?|berries?|chocolate)\b', r'ate \1 \2'),
    # holy/wholly
    (r'\bholy\s+(responsible|different|new|unaware|devoted|owned|dependent|separate|unexpected|unnecessary|unsatisfied|unacceptable)\b', r'wholly \1'),
    (r'\bwholly\s+(spirit|grail|land|lands?|water|week|war|city|cities?|man|woman|father|mother|scripture|scriptures|communion|roman|ghost)\b', r'holy \1'),
    # our/hour
    (r'\bour\s+of\b', 'hour of'),
    (r'\bhour\s+(team|company|family|home|house|goal|mission|customers?|clients?|products?|services?|friends?|kids|children|parents?|neighbors?|way|door|plan|plans|project)\b', r'our \1'),
    # chews/choose
    (r'\bchews\s+your\s+battles?\b', 'choose your battles'),
    (r'\bchews\s+(the|a|an|this|that|my|your|his|her|their|our)\s+((?:right|wrong|best|new|same|different)\s+)?(path|option|options|route|color|colours?|career|major|candidate|winner|side|seat)\b', r'choose \1 \2\3'),
    # berry/bury
    (r'\bberry\s+the\s+hatchet\b', 'bury the hatchet'),
    (r'\bberry\s+(the|a|an|my|your|his|her|their|our)\s+(treasure|bones?|body|bodies|secrets?|remains|head|face)\b', r'bury \1 \2'),
    # dye/die
    (r'\bdye\s+(in|from|of)\s+(a\s+)?(car\s+crash|accident|the\s+war|war|battle|combat|childbirth|old\s+age|a\s+fire|the\s+flu|cancer|a\s+disease|the\s+pandemic)\b', r'die \1 \2\3'),
    (r'\bdye\s+(young|alone|fighting|laughing|trying)\b', r'die \1'),
    (r'\bdie\s+(my|your|his|her|their|our|the|a|an)\s+(hair|fabric|cloth|shirt|shirts?|dress|dresses|eggs?|wool|silk)\b', r'dye \1 \2'),
    # knead/need
    (r'\bknead\s+to\b', 'need to'),
    # pane/pain
    (r'\bwindow\s+pain\b', 'window pane'),
    (r'\bglass\s+pain\b', 'glass pane'),
    (r'\bpane\s+in\s+(the|my|your|his|her|their|our)\s+(neck|back|chest|side|shoulder|knee|leg|arm|head|stomach|joints?)\b', r'pain in \1 \2'),
    (r'\bpain\s+of\s+(glass|window|windows?|door|doors?|stained)\b', r'pane of \1'),
    # wring/ring
    (r'\bwring\s+(the|a|an)\s+(bell|doorbell|phone|alarm)\b', r'ring \1 \2'),
    (r'\bring\s+(his|her|their|my|your|our)\s+hands\b', r'wring \1 hands'),
    # root/route
    (r'\broute\s+cause\b', 'root cause'),
    (r'\broot\s+(to|from)\s+(work|school|home|town|the\s+airport|the\s+store|the\s+beach|the\s+office)\b', r'route \1 \2'),
    (r'\broot\s+(map|maps)\b', r'route \1'),
    # scent/cent/sent
    (r'\bscent\s+(me|us|him|her|them|you)\s+(an\s+)?(email|message|letter|text|package|invitation|card|cards?|note)\b', r'sent \1 \2\3'),
    (r'\bsent\s+of\s+(flowers?|perfume|perfumes|cologne|smells?)\b', r'scent of \1'),
    # wood/would
    (r"(?<!\bthe\s)(?<!\ban\s)(?<!\ba\s)(?<!\bthis\s)(?<!\bthat\s)(?<!\bmy\s)(?<!\byour\s)(?<!\bhis\s)(?<!\bher\s)(?<!\bour\s)(?<!\btheir\s)(?<!\bmuch\s)\bwood\s+you\s+(like|love|prefer|rather|mind|care|please)\b", r'would you \1'),
    (r'\b(the|a|an|my|your|his|her|their|our|this|that)\s+would\s+(desk|table|chair|chairs|floor|plank|planks|furniture|carving|carvings|shed|sheds|panel|panels)\b', r'\1 wood \2'),
    # knot/not
    (r'\bknot\s+(sure|ready|only|just|really|very|too|that|this|what|why|how|where|when|who|enough|yet|now|here|there|again|anymore|the\s+case|a\s+problem|an\s+issue|bad|good|true|fair|funny|worth)\b', r'not \1'),
    # sow/sew/so
    (r'\bsow\s+(the|a|an|my|your|his|her|their|our)\s+(dress|shirt|shirts?|pants|button|buttons|hem|patch|costume|clothes|fabric|sleeve)\b', r'sew \1 \2'),
    (r'\bsew\s+(the|a|an|my|your|his|her|their|our)\s+(seeds?|oats|wheat|crops?|fields?|wild)\b', r'sow \1 \2'),
    (r'\bsew\s+(much|many|far|long|good|bad|big|small|fast|slow|late|early|often|hot|cold|well|badly|happy|sad|tired|hungry|excited|nervous|angry|proud|sorry|glad|sure|close|deep|high|low|heavy|light|quickly|slowly)\b', r'so \1'),
    # throne/thrown
    (r'\bto\s+the\s+thrown\b', 'to the throne'),
    (r'\bthrone\s+(away|out|off|down|up|aside)\b', r'thrown \1'),
    # toad/towed
    (r'\b(got|get|gets|getting|was|were|being)\s+toad\b', r'\1 towed'),
    # vial/vile
    (r'\bvile\s+of\s+(blood|poison|serum|medicine|drugs?|perfume|venom)\b', r'vial of \1'),
    (r'\bvial\s+(language|smell|temper|mood|insults?|attacks?|behavior|behaviour|remarks?)\b', r'vile \1'),
    # wade/weighed
    (r'\bwade\s+(the|a|an|my|your|his|her|their|our)\s+(options?|choices?|risks?|pros|cons|evidence|costs?|benefits?|consequences?|alternatives?)\b', r'weighed \1 \2'),
    # wear/where
    (r"(?<!\w\s)\bwear\s+(are|is|was|were)\s+(you|we|they|he|she|it|i|the|a|an|my|your|his|her|their|our|this|that|there|here|everyone|everybody|anyone|anybody|someone|somebody|nobody)\b", r'where \1 \2'),
    (r'\bwear\s+(have|has|had|do|does|did|can|could|will|would|should|might)\s+(you|we|they|he|she|it|i)\b', r'where \1 \2'),
    (r"\bwhere\s+(my|your|his|her|their|our|the|a|an)\s+(coat|jacket|hat|glasses|shoes?|dress|shirt|uniform|suit|mask|helmet|seatbelt|belt|scarf|gloves?)\b(?!\s*(?:is|are|was|were|has|have|had|hangs?|hanging|belongs?|kept|lies?|sits?|goes?|and|or|,))", r'wear \1 \2'),
    # wore/war
    (r'\bwore\s+(cries?|zones?|effort|efforts|chest|room|paint|horse|memorial|heroes?|veterans?|machines?|planes?|crimes?)\b', r'war \1'),
    (r'\bwar\s+(the|a|an|my|your|his|her|their|our)\s+(jacket|coat|hat|uniform|ring|dress|shirt|glasses|suit)\b', r'wore \1 \2'),
    # ── grammar & word-choice wave 7 ──────────────────────────────────────
    # supposed to ("suppose to" / "suppost to")
    (r'\bsuppose\s+to\b', 'supposed to'),
    (r'\bsuppost\s+to\b', 'supposed to'),
    # had/have/has went
    (r'\b(had|have|has)\s+went\b', r'\1 gone'),
    # wouldn't/couldn't/shouldn't of + participle
    (r"\b(wouldn't|couldn't|shouldn't)\s+of\s+([a-z]+?(?:ed|en|d|t|one|wn))\b", r'\1 have \2'),
    # eggcorns and non-words
    (r'\bfor\s+all\s+intensive\s+purposes\b', 'for all intents and purposes'),
    (r'\birregardless\b', 'regardless'),
    (r'\bin\s+regards\s+to\b', 'regarding'),
    (r'\ball\s+the\s+sudden\b', 'all of a sudden'),
    (r'\bin\s+the\s+mean\s+time\b', 'in the meantime'),
    (r'\boff\s+of\b', 'off'),
    (r'\ba\s+women\b', 'a woman'),
    (r'\bthese\s+kind\s+of\b', 'this kind of'),
    (r'\bthose\s+kind\s+of\b', 'that kind of'),
    # "between you and I" -> "between you and me"
    (r'\bbetween\s+(you|him|her|them|us)\s+and\s+i\b', r'between \1 and me'),
    # sentence-initial "me and X went" -> "X and I went"
    (r'^me\s+and\s+(\S.*?)\s+(went|are|were|have|had|will|would|could|should|can|do|did|want|need|like|love|enjoy|know|think|feel|agree|believe)\b', r'\1 and I \2'),
    # "defiantly" (a real word!) is almost always "definitely" before a verb
    (r'\bdefiantly\s+(be|come|go|take|see|help|send|do|have|get|make|try|call|write|read|finish|start|stop|join|meet|tell|ask|buy|eat|drink|watch|listen)\b', r'definitely \1'),
    # who's -> whose before a possessed noun
    (r"\bwho's\s+(book|name|email|phone|address|car|house|home|job|work|idea|plan|project|team|friend|family|dog|cat|keys|money|time|turn|responsibility|fault|problem|issue|answer|birthday)\b", r'whose \1'),
    # different than -> different from
    (r'\bdifferent\s+than\b', 'different from'),
    # assure that -> ensure that ("assure" needs an object: "assure you that")
    (r'\bassure\s+that\b', 'ensure that'),
    # bought -> brought ("bought it to the party")
    (r'\bbought\s+(it|this|that|the|a|an|my|your|his|her|their|our|me|us|him|her|them)\s+(to|here|along|back|home|over|up|out|in)\b', r'brought \1 \2'),
    # site -> cite before sources/references
    (r'\bsite\s+(a|an|the|your|my|his|her|their|our)\s+(source|sources|reference|references|example|examples|quote|quotes|statistic|statistics|study|studies|report|reports|article|articles|data|evidence|author|authors)\b', r'cite \1 \2'),
]


def edit_text(text: str) -> Tuple[str, List[str]]:
    """Apply deterministic text fixes. Returns (edited_text, changes)."""
    original = text
    changes: List[str] = []

    # 0. Mask URLs and emails so punctuation rules never mangle them
    # ("example.com" -> "example. Com", "user@a.com" spacing, etc.).
    _masked_parts = []
    def _mask(m):
        _masked_parts.append(m.group(0))
        return f'\u0001MASK{len(_masked_parts) - 1}\u0001'
    fixed = re.sub(r'https?://\S+|www\.\S+|\S+@\S+\.\S+', _mask, text.strip())
    def _unmask(s):
        return re.sub(r'\u0001MASK(\d+)\u0001',
                      lambda m: _masked_parts[int(m.group(1))], s)

    # 1. Collapse runs of whitespace, fix spacing around punctuation
    fixed = re.sub(r'[ \t]+', ' ', fixed)
    before = fixed
    fixed = re.sub(r'\s+([,.;:!?])', r'\1', fixed)          # no space before punct
    fixed = _fix_spacing_after_punct(fixed)                    # space after (abbrev-aware)
    if fixed != before:
        changes.append("removed stray spaces around punctuation")

    # 2. Common typo dictionary (single-pass, word-boundary, case-insensitive)
    _typo_hits = []
    def _typo_repl(m):
        w = m.group(1).lower()
        _typo_hits.append(w)
        return _TYPOS[w]
    fixed = _TYPOS_RE.sub(_typo_repl, fixed)
    for _w in dict.fromkeys(_typo_hits):
        changes.append(f'fixed "{_w}" -> "{_TYPOS[_w]}"')

    # 2b. Accidental repeated words ("the the", "and and", "he he said")
    # — but keep legitimate doubled words ("had had", "that that",
    # "very very", "no no"). Runs before homophones so "lets lets go"
    # becomes "let's go" in one pass.
    before = fixed
    def _dedup(m):
        w = m.group(1)
        return m.group(0) if w.lower() in _DUP_ALLOW else w
    fixed = re.sub(r'\b([\w\']+)\s+\1\b', _dedup, fixed, flags=re.IGNORECASE)
    if fixed != before:
        changes.append("removed accidentally repeated words")

    # 3. Clear homophone / agreement errors
    for pat, repl in _HOMOPHONE_PATTERNS:
        new = re.sub(pat, repl, fixed, flags=re.IGNORECASE)
        if new != fixed:
            changes.append("corrected a common grammar or word-choice error")
            fixed = new

    # 4. Capitalize "i" when standalone
    fixed = re.sub(r"(^|[\s.!?;:])i([\s.,!?;:'\"]|$)", r'\1I\2', fixed)

    # 4b. Days and months are always capitalized in English ("monday" ->
    # "Monday", "in january" -> "in January"). "May" is excluded because
    # it is also a modal verb.
    fixed = re.sub(
        r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|january|february|march|april|june|july|august|september|october|november|december)\b',
        lambda m: m.group(1)[0].upper() + m.group(1)[1:],
        fixed, flags=re.IGNORECASE)

    # 5. Sentence-start capitalization (after . ! ? or at the start), but NOT
    # after abbreviation periods ("U.S. and the U.K. are..." -> "and" stays
    # lowercase).
    def _cap_sentence(m):
        return m.group(1) + m.group(2).upper()
    before = fixed
    fixed = _capitalize_sentence_starts(fixed)
    if fixed != before:
        changes.append("capitalized sentence starts")

    # 6. a/an
    before = fixed
    # "a" -> "an" before vowel-start words (except words like "university") and
    # silent-h words ("hour", "honest"), preserving the case of the article.
    def _fix_a(am):
        article = am.group(1)
        word = am.group(2)
        wl = word.lower()
        if wl in _VOWEL_TAKES_A:
            return article + ' ' + word
        return ('An' if article == 'A' else 'an') + ' ' + word
    fixed = re.sub(r'\b([Aa])\s+([aeiouAEIOU][a-zA-Z]*|' + '|'.join(sorted(_SILENT_H_TAKES_AN, key=len, reverse=True)) + r')', _fix_a, fixed)
    # "an" -> "a" before consonant-start words or exception words (but NOT
    # before silent-h words like "honest")
    _vowel_a_words = '|'.join(sorted(_VOWEL_TAKES_A, key=len, reverse=True))
    _silent_h_words = '|'.join(sorted(_SILENT_H_TAKES_AN, key=len, reverse=True))
    def _fix_an(am):
        article = am.group(1)
        return ('A' if article == 'An' else 'a') + ' ' + am.group(2)
    fixed = re.sub(
        r'\b([Aa]n)\s+([bcdfghjklmnpqrstvwxyz][a-zA-Z]*|' + _vowel_a_words + r')\b',
        _fix_an, fixed)
    # restore an -> an for silent-h words that the rule above just broke
    fixed = re.sub(
        r'\b([Aa])\s+(' + _silent_h_words + r')\b',
        lambda m: ('An' if m.group(1) == 'A' else 'an') + ' ' + m.group(2),
        fixed, flags=re.IGNORECASE)
    if fixed != before:
        changes.append("fixed a/an articles")

    # 7. Collapse leftover double spaces from substitutions
    fixed = re.sub(r' +', ' ', fixed)
    fixed = re.sub(r'\s+([.!?,;:])', r'\1', fixed)

    # restore masked URLs/emails
    fixed = _unmask(fixed)

    if fixed == original:
        changes.append("no typos or issues found")
    return fixed, changes


def _replace_word(text, word, repl, changes, original):
    """Case-aware word-boundary replacement, tracking whether it fired."""
    pattern = re.compile(r'\b' + re.escape(word) + r'\b', re.IGNORECASE)
    new = pattern.sub(repl, text)
    if new != text:
        changes.append(f'fixed "{word}" -> "{repl}"')
    return new


# ── Code editing rules ──────────────────────────────────────────────────────

# CSS property/value typos (word-boundary, safe — not valid CSS properties)
_CSS_TYPOS = {
    'hieght': 'height', 'heigth': 'height', 'with': 'width', 'widht': 'width',
    'colour': 'color', 'bordr': 'border', 'boder': 'border', 'pading': 'padding',
    'padidng': 'padding', 'margn': 'margin', 'marign': 'margin',
    'backgound': 'background', 'backgorund': 'background', 'displa': 'display',
    'flor': 'float', 'foat': 'float', 'positiong': 'positioning',
    'text-alignn': 'text-align', 'font-sise': 'font-size', 'font-siez': 'font-size',
    'font-sze': 'font-size', 'line-hight': 'line-height', 'line-heigth': 'line-height',
    'border-radus': 'border-radius', 'border-radi': 'border-radius',
    'opactiy': 'opacity', 'opcity': 'opacity', 'transparenty': 'transparency',
    'box-shadoe': 'box-shadow', 'box-shadown': 'box-shadow',
    'overflwo': 'overflow', 'overflw': 'overflow', 'z-indexx': 'z-index',
    'cursorr': 'cursor', 'curdor': 'cursor', 'visiblity': 'visibility',
    'visibilityy': 'visibility', 'flex-diraction': 'flex-direction',
    'justify-conent': 'justify-content', 'justify-contnet': 'justify-content',
    'align-iteams': 'align-items', 'align-itesm': 'align-items',
    'box-sizng': 'box-sizing', 'z-idex': 'z-index', 'aniamtion': 'animation',
    'animaton': 'animation', 'tranform': 'transform', 'transiton': 'transition',
}


# SQL keyword typos (safe — not valid SQL)
_SQL_TYPOS = {
    'FORM': 'FROM', 'SELCET': 'SELECT', 'SELEECT': 'SELECT', 'WERE': 'WHERE',
    'WHRER': 'WHERE', 'WERHE': 'WHERE', 'INERT': 'INSERT', 'INSERTT': 'INSERT',
    'UPDAT': 'UPDATE', 'DELEET': 'DELETE', 'DELET': 'DELETE', 'CREAT': 'CREATE',
    'GROUB': 'GROUP', 'GROUOP': 'GROUP', 'ODER': 'ORDER', 'ORDRE': 'ORDER',
    'BYE': 'BY', 'INTO': 'INTO', 'JOINN': 'JOIN', 'LEF': 'LEFT', 'RIGTH': 'RIGHT',
    'RIGT': 'RIGHT', 'OUTERR': 'OUTER', 'INNER': 'INNER', 'CROSSS': 'CROSS',
    'WHER': 'WHERE', 'HAVIN': 'HAVING', 'DISTICNT': 'DISTINCT', 'DISTINT': 'DISTINCT',
    'COUNNT': 'COUNT', 'SUM': 'SUM', 'AVERAGE': 'AVG', 'MINN': 'MIN', 'MAXX': 'MAX',
    'BETWEENN': 'BETWEEN', 'LIKEE': 'LIKE', 'INN': 'IN', 'NOTT': 'NOT', 'ANND': 'AND',
    'ORR': 'OR', 'ISSS': 'IS', 'NULLL': 'NULL', 'TRUEE': 'TRUE', 'FALSEE': 'FALSE',
    'DESCENDING': 'DESC', 'ASCENDING': 'ASC', 'TABEL': 'TABLE', 'TABLLE': 'TABLE',
    'DATBASE': 'DATABASE', 'DATABSE': 'DATABASE', 'COLUMM': 'COLUMN', 'COLUMNSS': 'COLUMNS',
    'SELEC': 'SELECT', 'UPDTE': 'UPDATE', 'HAVNG': 'HAVING', 'DISTINCTT': 'DISTINCT',
    'WHRER': 'WHERE', 'INTOO': 'INTO', 'SETT': 'SET', 'WHERR': 'WHERE',
}

# Bash command typos (safe — not valid commands)
_BASH_TYPOS = {
    'ecoh': 'echo', 'echi': 'echo', 'cdd': 'cd', 'mkidr': 'mkdir', 'mkdirr': 'mkdir',
    'rmdirr': 'rmdir', 'cmod': 'chmod', 'chmodd': 'chmod', 'sudu': 'sudo',
    'suod': 'sudo', 'grep': 'grep', 'grepp': 'grep', 'sedd': 'sed', 'awkk': 'awk',
    'wget': 'wget', 'wgett': 'wget', 'curll': 'curl', 'curlr': 'curl',
    'unzip': 'unzip', 'unzipp': 'unzip', 'tarr': 'tar', 'chwon': 'chown',
    'chonw': 'chown', 'lnn': 'ln', 'rmm': 'rm', 'rmm -rf': 'rm -rf',
    'cp -r': 'cp -r', 'mvv': 'mv', 'lss': 'ls', 'pwd': 'pwd',
    'mkdri': 'mkdir', 'chomd': 'chmod', 'touh': 'touch', 'catt': 'cat',
    'grepp': 'grep', 'finnd': 'find', 'exitt': 'exit',
}

# HTML attribute/tag typos (safe — not valid attributes)
_HTML_TYPOS = {
    'herf': 'href', 'clas': 'class', 'stlye': 'style', 'widht': 'width',
    'hieght': 'height', 'scr': 'src', 'srcc': 'src', 'id': 'id',
    'colspan': 'colspan', 'alt': 'alt', 'tytle': 'title', 'titel': 'title',
    'placehoder': 'placeholder', 'placeholder': 'placeholder', 'disabledd': 'disabled',
    'readonlyy': 'readonly', 'onselect': 'onselect', 'onclickk': 'onclick',
    'ondblclick': 'ondblclick', 'onchangee': 'onchange', 'onfocuss': 'onfocus',
    'onblurr': 'onblur', 'onsubmitt': 'onsubmit', 'onloadd': 'onload',
}


_CODE_TYPOS = {
    'cunsle': 'console', 'consle': 'console', 'consoloe': 'console',
    'fucntion': 'function', 'functoin': 'function', 'fuction': 'function',
    'funtion': 'function', 'funtions': 'functions',
    'retunr': 'return', 'retun': 'return', 'reutrn': 'return',
    'prnit': 'print', 'prtin': 'print',
    'varible': 'variable', 'varibles': 'variables', 'sting': 'string',
    'integar': 'integer', 'interger': 'integer', 'lenght': 'length',
    'defintion': 'definition', 'recieve': 'receive', 'wether': 'whether',
    'elif': 'elif', 'nubmer': 'number', 'nubmers': 'numbers',
    'lits': 'list', 'dic': 'dict', 'dicionary': 'dictionary',
    'arra': 'array', 'arraies': 'arrays', 'elment': 'element',
    'elments': 'elements', 'indx': 'index', 'param': 'param',
    'arguement': 'argument', 'arguements': 'arguments',
    'excpet': 'except', 'exceptio': 'exception', 'throwed': 'thrown',
    'getter': 'getter', 'setter': 'setter', 'boolen': 'boolean',
    'flaot': 'float', 'stirng': 'string', 'strng': 'string',
    'javescript': 'javascript', 'javasript': 'javascript',
    'pythn': 'python', 'pthon': 'python', 'reqiure': 'require',
    'requier': 'require', 'reqire': 'require', 'improt': 'import',
    'impot': 'import', 'exprot': 'export', 'exort': 'export',
    'constt': 'const', 'lett': 'let', 'varr': 'var',
    'undefiend': 'undefined', 'nullish': 'nullish',
    'functio': 'function', 'functionn': 'function',
    # wave: more code misspellings
    'retrun': 'return', 'retern': 'return',
    'funciton': 'function', 'funcitons': 'functions',
    'defualt': 'default', 'defautl': 'default',
    'paramter': 'parameter', 'paramters': 'parameters',
    'delimeter': 'delimiter',
    'atrribute': 'attribute', 'atributes': 'attributes',
    'interator': 'iterator',
    'generater': 'generator',
    'conatiner': 'container',
    'destory': 'destroy',
    'requst': 'request', 'requsts': 'requests',
    'responce': 'response', 'responces': 'responses',
    'seach': 'search',
    'booleen': 'boolean', 'boolearn': 'boolean',
    'initalize': 'initialize', 'initalized': 'initialized',
    'initalization': 'initialization',
    'recieve': 'receive',
    'objcet': 'object', 'objct': 'object',
    'heigth': 'height',
    'sring': 'string',
    'widnow': 'window',
    # wave: JS identifiers and other code misspellings
    'doucment': 'document', 'functin': 'function', 'retuns': 'returns',
    'addeventlistner': 'addEventListener', 'queryselctor': 'querySelector',
    'innerhtml': 'innerHTML', 'textcontnet': 'textContent',
    'dafault': 'default', 'defaul': 'default',
}


def detect_code_lang(content: str, query: str = '') -> str:
    q = (query + ' ' + content).lower()
    # "python3"/"javascript" must not trigger "python"/"java" via substring
    if re.search(r'\bpython\b', q) or re.search(r'\bdef\s+\w+\(', content):
        return 'python'
    if any(w in q for w in ('javascript', 'typescript', 'node')):
        return 'javascript'
    # JS-style functions and console/var/let/const syntax
    if re.search(r'\bfunction\s+\w+\s*\(|console\.|=>|\blet\s+\w+|\bconst\s+\w+|document\.|getElementById|querySelector|addEventListener|\.innerHTML|\.textContent', content):
        return 'javascript'
    # Python-style blocks (indentation + print/import/if/for/while/class)
    if (re.search(r'\b(?:print|import|from|def|class|for|while|try|except|elif|else|raw_input|xrange|if|unicode|basestring|has_key)\b', content)
            and (re.search(r'\n\s+', content) or re.search(r'\bprint\(', content)
                 or re.search(r'\bprint\s+["\']', content)
                 or re.search(r'\b(?:raw_input|xrange|unicode)\s*\(', content)
                 or re.search(r'^\s*(?:def|class|if|for|while|try|except|elif|else)\s', content, re.MULTILINE))):
        return 'python'
    if 'java' in q and 'javascript' not in q:
        return 'java'
    if 'c++' in q or 'cpp' in q:
        return 'cpp'
    if 'go' in q:
        return 'go'
    if 'rust' in q:
        return 'rust'
    if 'sql' in q or re.search(r'\b(?:SELECT|INSERT|UPDATE|DELETE|FROM|WHERE|JOIN|CREATE\s+TABLE|FORM|WERE|SELCET|INERT)\b', content):
        return 'sql'
    if 'html' in q or re.search(r'<\/?[a-z][a-z0-9-]*|\b(?:href|src|class|div|span|img|a\s+href)\b', content):
        return 'html'
    # CSS requires an actual rule block or unit/property signals — a bare
    # "color" inside style="..." must not win over HTML.
    if 'css' in q or re.search(r'[a-z-]+\s*\{[^}]*\}|\b\d+(?:px|em|rem|vh|vw|%)\b|\b(?:margin|padding|background|font-size|line-height)\s*:', content):
        return 'css'
    if 'bash' in q or 'shell' in q or re.search(r'\b(?:echo|sudo|mkdir|chmod|grep|curl|wget|cd|rm|mv|cp|ecoh|sudu|mkidr|touh|chomd|mkdri|chwon)\b', content):
        return 'bash'
    if 'html' in q or re.search(r'<\/?[a-z][a-z0-9-]*|\b(?:href|src|class|div|span|img|a\s+href)\b', content):
        return 'html'
    return 'text'


def edit_code(content: str, query: str = '') -> Tuple[str, List[str]]:
    """Apply deterministic code fixes. Returns (edited_code, changes)."""
    lang = detect_code_lang(content, query)
    original = content
    changes: List[str] = []

    fixed = content

    # 1. Common identifier typos (word-boundary, also inside snake_case names:
    # "my_sting" -> "my_string", "retrun_value" -> "return_value")
    _code_hits = []
    def _code_typo_repl(m):
        w = m.group(1).lower()
        _code_hits.append(w)
        return _CODE_TYPOS[w]
    _CODE_TYPOS_RE = re.compile(
        r'(?<![A-Za-z0-9])(' + '|'.join(re.escape(w) for w in sorted(_CODE_TYPOS)) + r')(?![A-Za-z0-9])',
        re.IGNORECASE)
    fixed = _CODE_TYPOS_RE.sub(_code_typo_repl, fixed)
    for _w in dict.fromkeys(_code_hits):
        changes.append(f'fixed "{_w}" -> "{_CODE_TYPOS[_w]}"')

    # 2. Tabs -> 4 spaces, strip trailing whitespace per line
    before = fixed
    fixed = '\n'.join(line.replace('\t', '    ').rstrip() for line in fixed.split('\n'))
    if fixed != before:
        changes.append("converted tabs to spaces and removed trailing whitespace")

    # 3. Missing commas in function signatures: "def add(a b):" -> "def add(a, b):"
    if lang == 'python':
        before = fixed
        def _fix_sig(m):
            name = m.group('name')
            args = m.group('args')
            # insert commas between whitespace-separated bare identifiers
            args = re.sub(r'\b([a-zA-Z_][\w]*)\s+([a-zA-Z_][\w]*)\b', r'\1, \2', args)
            return f'def {name}({args})'
        fixed = re.sub(r'\bdef\s+(?P<name>\w+)\s*\((?P<args>[^()]*)\)', _fix_sig, fixed)
        if fixed != before:
            changes.append("added missing commas in function signature")

    # 4. Missing colons after Python block openers: "def foo()" -> "def foo():",
    # "if x > 5" -> "if x > 5:", bare "else" -> "else:". Only fixes a line
    # that currently ends without a colon, brace, or semicolon.
    if lang == 'python':
        before = fixed
        def _fix_colon(line):
            s = line.rstrip()
            if not s:
                return line
            stripped = s.lstrip()
            if not re.match(
                r'(?:def|class|if|elif|else|for|while|try|except|finally|with)\b',
                stripped):
                return line
            if s.endswith((':', '{', ';', '\\')):
                return line
            # "else" / "try" / "finally" need nothing but the colon
            if stripped in ('else', 'try', 'finally'):
                return s + ':'
            # the header already carries its colon (one-line blocks like
            # "def add(a, b): print(a+b)" must NOT get a second one at the end)
            if ':' in s:
                return line
            # compound forms already end in ':' if correct; if not, add it
            return s + ':'
        fixed = '\n'.join(_fix_colon(line) for line in fixed.split('\n'))
        if fixed != before:
            changes.append("added missing colons after block statements")

    # 5. Python body re-indentation: a line ending in ':' whose next non-empty
    # line is NOT indented is broken ("def foo():\nreturn 1"). Indent the body
    # by 4 spaces. Skips when the next line starts another block at column 0
    # ("if x:\nelse:" would be a different error) or is a comment.
    if lang == 'python':
        before = fixed
        # 5a. "for i range(10):" -> "for i in range(10):" (missing 'in')
        def _fix_for_in(m):
            lead, vars_, ws, tok, rest = (m.group(1), m.group(2), m.group(3),
                                          m.group(4), m.group(5))
            if tok == 'in':
                return m.group(0)
            return f'{lead}{vars_} in {tok}' + (f' {rest}' if rest else '') + ':'
        fixed = re.sub(
            r'^(\s*for\s+)(\w+(?:\s*,\s*\w+)*)(\s+)'
            r'([a-z_]\w*(?:\([^)]*\))?)(?:\s+([^:]+))?:\s*$',
            _fix_for_in, fixed, flags=re.MULTILINE)
        # 5b. "if x = 5:" -> "if x == 5:" (assignment in a condition);
        # also covers elif/while. Never touches ==, <=, >=, !=.
        def _fix_cond_eq(m):
            return f'{m.group(1)}{m.group(2)} == {m.group(3)}:'
        fixed = re.sub(
            r'^(\s*(?:if|elif|while)\s+)([a-zA-Z_]\w*)\s*=(?!=)\s*([^:]+):\s*$',
            _fix_cond_eq, fixed, flags=re.MULTILINE)
        if fixed != before:
            changes.append("fixed for-loop 'in' / condition '==' syntax")

        lines = fixed.split('\n')
        out = []
        i = 0
        while i < len(lines):
            line = lines[i]
            out.append(line)
            if line.rstrip().endswith(':'):
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    out.append(lines[j])
                    j += 1
                if j < len(lines):
                    nxt = lines[j]
                    if nxt and not nxt.startswith((' ', '\t')) and nxt.strip() and not nxt.startswith('#'):
                        out.append('    ' + nxt)
                        i = j
            i += 1
        fixed = '\n'.join(out)
        if fixed != before:
            changes.append("re-indented code block bodies")

    # 6. CSS repairs: property typos, missing colons in declarations, missing
    # semicolons, and spaces inside unit values ("16 px" -> "16px").
    if lang == 'css':
        before = fixed
        for word, repl in _CSS_TYPOS.items():
            fixed = _replace_word(fixed, word, repl, changes, original)
        # "16 px" -> "16px" (also %, em, rem, etc.)
        fixed = re.sub(r'(\d)\s+(px|em|rem|%|vh|vw|vmin|vmax|pt|cm|mm|in)\b', r'\1\2', fixed)
        # declaration repair inside blocks: track brace depth so selectors and
        # @-rules are never touched.
        out_lines = []
        depth = 0
        for line in fixed.split('\n'):
            s = line.rstrip()
            if not s.strip():
                out_lines.append(line)
                continue
            depth += s.count('{') - s.count('}')
            stripped = s.strip()
            if depth > 0 and not stripped.startswith(('/*', '*', '//', '@')):
                # "color red" -> "color: red;" / "color: red" -> "color: red;"
                if ':' in stripped and not stripped.endswith(';'):
                    if not re.search(r':\s*$', stripped):
                        s = s + ';'
                elif ':' not in stripped and not stripped.endswith(('{', '}')):
                    m = re.match(r'^(\s*)([a-z-]+)\s+([^;{}]+)$', s)
                    if m:
                        s = m.group(1) + m.group(2) + ': ' + m.group(3) + ';'
            out_lines.append(s)
        fixed = '\n'.join(out_lines)
        if fixed != before:
            changes.append("fixed CSS declarations")

    # 6b. Python 2 -> 3 migration fixes (safe, unambiguous)
    if lang == 'python':
        before = fixed
        # print "x" -> print("x"); print i -> print(i) (bare identifiers
        # only — print(x) / print (x) must not be touched)
        fixed = re.sub(r'\bprint\s+(["\'][^"\']*["\'])(?=\s*(?:#|$))', r'print(\1)', fixed)
        fixed = re.sub(r'\bprint\s+([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)\s*(?=\s*(?:#|$))', r'print(\1)', fixed)
        # xrange/raw_input/unichr -> range/input/chr
        fixed = re.sub(r'\bxrange\s*\(', 'range(', fixed)
        fixed = re.sub(r'\braw_input\s*\(', 'input(', fixed)
        fixed = re.sub(r'\bunichr\s*\(', 'chr(', fixed)
        # .iteritems()/.iterkeys()/.itervalues() -> .items()/.keys()/.values()
        fixed = re.sub(r'\.iteritems\(\)', '.items()', fixed)
        fixed = re.sub(r'\.iterkeys\(\)', '.keys()', fixed)
        fixed = re.sub(r'\.itervalues\(\)', '.values()', fixed)
        # except Exception, e: -> except Exception as e:
        fixed = re.sub(r'\bexcept\s+([A-Za-z_]\w*)\s*,\s*(\w+)\s*:', r'except \1 as \2:', fixed)
        # x <> y -> x != y  (py2 inequality operator)
        fixed = re.sub(r'\s*<>\s*', ' != ', fixed)
        # unicode(x) -> str(x), basestring -> str
        fixed = re.sub(r'\bunicode\s*\(', 'str(', fixed)
        fixed = re.sub(r'\bbasestring\b', 'str', fixed)
        # d.has_key(k) -> k in d  (also with quoted keys: d.has_key('k'))
        fixed = re.sub(r'\b(\w+)\.has_key\((["\']?)(\w+)\2\)', r'\3 in \1', fixed)
        if fixed != before:
            changes.append("applied Python 2 to 3 fixes")

    # 7. SQL keyword typos ("SELECT * FORM" -> "SELECT * FROM")
    if lang == 'sql':
        before = fixed
        for word, repl in _SQL_TYPOS.items():
            fixed = _replace_word(fixed, word, repl, changes, original)
        # "SELECT * form x" (lowercase form) -> FROM
        fixed = re.sub(r'\bform\s+(?!\w*\bwhere\b)', 'FROM', fixed, flags=re.IGNORECASE)
        if fixed != before:
            changes.append("fixed SQL keyword typos")

    # 8. Bash command typos
    if lang == 'bash':
        before = fixed
        for word, repl in _BASH_TYPOS.items():
            fixed = _replace_word(fixed, word, repl, changes, original)
        if fixed != before:
            changes.append("fixed bash command typos")

    # 9. HTML attribute typos
    if lang == 'html':
        before = fixed
        for word, repl in _HTML_TYPOS.items():
            fixed = _replace_word(fixed, word, repl, changes, original)
        # unclosed common tags: <div>...</div> (fix </dvi> -> </div> etc.)
        fixed = re.sub(r'<\/(dvi|spna|pam|sapn|dv)>(?=\s|$)', lambda m: '</' + {'dvi': 'div', 'spna': 'span', 'pam': 'p', 'sapn': 'span', 'dv': 'div'}[m.group(1)] + '>', fixed)
        if fixed != before:
            changes.append("fixed HTML attribute/tag typos")

        # 9b. Tag balance: auto-close unclosed container tags and report
        # mismatches. Void elements (br, img, ...) and self-closing tags are
        # skipped; "soft" tags (li, p, td, ...) may be implicitly closed by
        # HTML so they are only reported when left dangling at the end.
        _VOID_TAGS = {'br', 'img', 'hr', 'input', 'meta', 'link', 'source',
                      'area', 'base', 'col', 'embed', 'param', 'track', 'wbr'}
        _SOFT_TAGS = {'li', 'p', 'td', 'th', 'tr', 'option', 'dd', 'dt',
                      'tbody', 'thead', 'tfoot', 'html', 'head', 'body'}
        _stack = []
        _mismatch = []
        for tm in re.finditer(r'<(/?)([a-zA-Z0-9-]+)([^>]*)>', fixed):
            closing, tag, attrs = tm.group(1), tm.group(2).lower(), tm.group(3)
            if tag in _VOID_TAGS or attrs.rstrip().endswith('/'):
                continue
            if closing:
                while _stack and _stack[-1] != tag and _stack[-1] in _SOFT_TAGS:
                    _stack.pop()
                if _stack and _stack[-1] == tag:
                    _stack.pop()
                else:
                    _mismatch.append(tag)
            else:
                _stack.append(tag)
        _hard_open = [t for t in _stack if t not in _SOFT_TAGS]
        if _mismatch:
            changes.append('html: mismatched closing tag(s): '
                           + ', '.join(f'</{t}>' for t in _mismatch))
        if _hard_open:
            fixed += '\n' + ''.join(f'</{t}>' for t in reversed(_hard_open))
            changes.append('html: closed unclosed tag(s): '
                           + ', '.join(f'</{t}>' for t in reversed(_hard_open)))

    if fixed == original:
        changes.append("no obvious issues found in the code")
    return fixed, changes


# ── Top-level entry ─────────────────────────────────────────────────────────

# ── Change/refinement requests ──────────────────────────────────────────────
# The user can ask for changes to the last edited content: "make it shorter",
# "make it more formal", "change hello to hi", "add a greeting", etc.
_LAST_EDIT = {'kind': None, 'content': ''}

# Word-level formalization (safe swaps)
_FORMAL_WORDS = {
    'gonna': 'going to', 'wanna': 'want to', 'gotta': 'have to',
    'kinda': 'kind of', 'sorta': 'sort of', 'u': 'you', 'ur': 'your',
    'ya': 'you', 'pls': 'please', 'plz': 'please', 'thx': 'thanks',
    'ty': 'thank you', 'tysm': 'thank you so much', 'thnx': 'thanks',
    'yeah': 'yes', 'yep': 'yes', 'nope': 'no', 'nah': 'no',
    'lemme': 'let me', 'gimme': 'give me', 'dunno': 'do not know',
    'cuz': 'because', 'hey': 'hello', 'hiya': 'hello', 'howdy': 'hello',
    'sup': 'hello', 'stuff': 'things', 'guys': 'everyone', 'kids': 'children',
    "i'm": 'I am', 'im': 'I am', "i'll": 'I will', "i've": 'I have',
    "i'd": 'I would', "don't": 'do not', 'dont': 'do not',
    "can't": 'cannot', 'cant': 'cannot', "won't": 'will not', 'wont': 'will not',
    "it's": 'it is', "that's": 'that is', "there's": 'there is',
    "we're": 'we are', "we've": 'we have', "you're": 'you are',
    "they're": 'they are', "isn't": 'is not', "aren't": 'are not',
    "wasn't": 'was not', "weren't": 'were not', "didn't": 'did not',
    "doesn't": 'does not', "couldn't": 'could not', "wouldn't": 'would not',
    "shouldn't": 'should not', "hasn't": 'has not', "haven't": 'have not',
    "hadn't": 'had not', "let's": 'let us',
    'thanks for': 'thank you for', 'thanks': 'thank you',
    'btw': 'by the way', 'asap': 'as soon as possible',
    'tmrw': 'tomorrow', 'tomoz': 'tomorrow', 'msg': 'message',
    'idk': 'I do not know', 'imo': 'in my opinion', 'tbh': 'to be honest',
    'rn': 'right now', 'yall': 'you all', "ya'll": 'you all',
    'want to': 'would like to', 'need to': 'must',
    'tryna': 'trying to', 'probs': 'probably', 'deffo': 'definitely',
    'atm': 'at the moment', 'fyi': 'for your information', 'ngl': 'to be honest',
    'afaik': 'as far as I know', 'lmk': 'let me know', 'tho': 'though',
    'bc': 'because', 'tldr': 'in summary', '2morrow': 'tomorrow',
    '2day': 'today', '4u': 'for you', 'b4': 'before', 'plz': 'please',
    'cud': 'could', 'wud': 'would', 'shud': 'should', 'wiv': 'with',
}

# Reverse, mild casualization
_CASUAL_WORDS = {
    'i am': "I'm", 'do not': "don't", 'cannot': "can't", 'will not': "won't",
    'it is': "it's", 'that is': "that's", 'there is': "there's",
    'we are': "we're", 'you are': "you're", 'they are': "they're",
    'is not': "isn't", 'are not': "aren't", 'was not': "wasn't",
    'were not': "weren't", 'did not': "didn't", 'does not': "doesn't",
    'would not': "wouldn't", 'could not': "couldn't", 'should not': "shouldn't",
    'thank you for': 'thanks for', 'thank you': 'thanks', 'hello': 'hey',
}

_TEXT_ONLY_CHANGES = {
    'shorter', 'longer', 'formal', 'casual', 'bullets',
    'add_greeting', 'add_closing', 'remove_greeting', 'remove_closing',
    'remove_exclamations', 'remove_question_marks', 'add_subject',
    'add_punctuation', 'spell_numbers', 'remove_breaks',
    'remove_first_sentence', 'remove_last_sentence',
    'remove_first_paragraph', 'remove_last_paragraph',
    'remove_first_line', 'remove_last_line',
    'remove_first_word', 'remove_last_word', 'remove_n',
    'add_title', 'remove_quotes', 'add_quotes', 'soften',
    'remove_subject', 'remove_title', 'remove_bullets',
    'remove_duplicates', 'add_line_breaks',
    'sort', 'reverse', 'remove_numbers', 'remove_punctuation',
    'remove_emojis', 'add_parentheses', 'remove_parentheses',
    'swap_first_last', 'add_date', 'remove_date',
    'double_space', 'single_space', 'make_question', 'remove_empty_lines',
    'make_past', 'make_present', 'make_negative', 'add_exclamations',
    'upper', 'lower', 'title_case',
    'polite',
}


def set_last_edit(kind, content):
    global _LAST_EDIT
    _LAST_EDIT = {'kind': kind, 'content': content}


def get_last_edit_content():
    return _LAST_EDIT.get('content') or ''


def get_last_edit_kind():
    return _LAST_EDIT.get('kind')


def _parse_change_clause(clause):
    """Map a single bare change phrase to an instruction, or None.

    Used for chained requests ("make it shorter and more formal", "add a
    greeting and a closing") where each half of the "and" must parse on its
    own. Accepts full forms ("remove the first sentence") and ellipsis forms
    ("the last sentence" after "remove the first sentence and ...").
    """
    c = clause.strip().lower()
    c = re.sub(r'^(?:please|now|then|just|kindly)\s+', '', c)
    c = re.sub(r'^make\s+(?:it|this|that|the\s+[\w-]+)(?:\s+(?:sound|look|read))?\s+', '', c)
    c = re.sub(r'\s+(?:it|this|that)$', '', c)
    if c in ('shorter', 'shorten', 'more concise', 'concise', 'condense', 'trim', 'cut it down'):
        return 'shorter'
    if c in ('longer', 'expand', 'more detailed', 'detailed'):
        return 'longer'
    if c in ('formal', 'more formal', 'professional', 'more professional', 'polite', 'more polite'):
        return 'formal'
    if c in ('casual', 'more casual', 'friendly', 'friendlier', 'more friendly', 'informal', 'relaxed'):
        return 'casual'
    if c in ('uppercase', 'all caps', 'upper'):
        return 'upper'
    if c in ('lowercase', 'lower'):
        return 'lower'
    if c in ('title case', 'titlecase', 'capitalize'):
        return 'title_case'
    if c in ('bullet points', 'bullets', 'a list', 'a bullet list', 'a list of bullet points'):
        return 'bullets'
    if c in ('add a greeting', 'add greeting', 'add a salutation', 'add salutation', 'a greeting', 'greeting'):
        return 'add_greeting'
    if c in ('add a closing', 'add closing', 'add a sign off', 'a closing', 'closing'):
        return 'add_closing'
    if c in ('remove the greeting', 'remove greeting', 'remove the salutation'):
        return 'remove_greeting'
    if c in ('remove the closing', 'remove closing', 'remove the sign off'):
        return 'remove_closing'
    if c in ('remove exclamations', 'remove the exclamations', 'remove exclamation marks', 'remove the exclamation marks'):
        return 'remove_exclamations'
    if c in ('remove question marks', 'remove the question marks'):
        return 'remove_question_marks'
    if c in ('add a subject line', 'add subject line', 'add a subject', 'add subject'):
        return 'add_subject'
    if c in ('add punctuation', 'add periods', 'add missing punctuation'):
        return 'add_punctuation'
    if c in ('spell out the numbers', 'spell out numbers', 'spell out the number', 'spell out number'):
        return 'spell_numbers'
    if c in ('make it one paragraph', 'one paragraph', 'remove line breaks', 'remove the line breaks', 'remove paragraph breaks'):
        return 'remove_breaks'
    if c in ('add a title', 'add title', 'add a headline', 'add headline'):
        return 'add_title'
    if c in ('remove the title', 'remove title', 'remove the headline'):
        return 'remove_title'
    if c in ('remove the subject line', 'remove subject line', 'remove the subject'):
        return 'remove_subject'
    if c in ('remove the bullet points', 'remove bullet points', 'remove the bullets', 'remove bullets', 'unbullet it', 'make it a paragraph'):
        return 'remove_bullets'
    if c in ('remove duplicate words', 'remove the duplicate words', 'remove repeated words', 'remove the repeated words'):
        return 'remove_duplicates'
    if c in ('put each sentence on its own line', 'put every sentence on its own line', 'one sentence per line', 'add line breaks', 'split it into lines'):
        return 'add_line_breaks'
    if c in ('sort it', 'sort the list', 'sort', 'sort it alphabetically', 'alphabetize it', 'alphabetize', 'sort the lines'):
        return 'sort'
    if c in ('reverse it', 'reverse the sentences', 'reverse the order', 'reverse the list', 'put the last sentence first', 'reverse the lines'):
        return 'reverse'
    if c in ('remove the numbers', 'remove numbers', 'remove all numbers'):
        return 'remove_numbers'
    if c in ('remove the punctuation', 'remove punctuation', 'remove all punctuation'):
        return 'remove_punctuation'
    if c in ('remove the emojis', 'remove emojis', 'remove all emojis'):
        return 'remove_emojis'
    if c in ('put it in parentheses', 'put it in brackets', 'wrap it in parentheses', 'add parentheses'):
        return 'add_parentheses'
    if c in ('remove the parentheses', 'remove parentheses', 'remove the brackets'):
        return 'remove_parentheses'
    if c in ('add a date', 'add the date', 'add todays date', "add today's date"):
        return 'add_date'
    if c in ('remove the date', 'remove date'):
        return 'remove_date'
    if c in ('make it double spaced', 'make it double-spaced', 'double space it'):
        return 'double_space'
    if c in ('make it single spaced', 'make it single-spaced', 'single space it'):
        return 'single_space'
    if c in ('make it a question', 'turn it into a question', 'convert it to a question', 'make this a question', 'a question', 'into a question'):
        return 'make_question'
    if c in ('make it past tense', 'make it past', 'put it in the past tense', 'convert it to past tense', 'past tense', 'past'):
        return 'make_past'
    if c in ('make it present tense', 'make it present', 'put it in the present tense', 'convert it to present tense', 'present tense', 'present'):
        return 'make_present'
    if c in ('make it negative', 'turn it into a negative statement', 'make this a negative statement', 'negative', 'a negative statement'):
        return 'make_negative'
    if c in ('add exclamation marks', 'add exclamation points', 'make it more exciting', 'make it more excited', 'add excitement'):
        return 'add_exclamations'
    if c in ('remove empty lines', 'remove the empty lines', 'remove blank lines'):
        return 'remove_empty_lines'
    if c in ('remove the quotes', 'remove quotes', 'remove all quotes'):
        return 'remove_quotes'
    if c in ('put it in quotes', 'add quotes', 'wrap it in quotes'):
        return 'add_quotes'
    if c in ('soften it', 'soften the tone', 'soften', 'tone it down', 'less angry'):
        return 'soften'
    m = re.match(r'^remove\s+(?:the\s+)?(first|last)\s+(sentence|paragraph|line)$', c)
    if m:
        return f'remove_{m.group(1)}_{m.group(2)}'
    m = re.match(r'^(?:the\s+)?(first|last)\s+(sentence|paragraph|line)$', c)
    if m:
        return f'remove_{m.group(1)}_{m.group(2)}'
    return None


def detect_change_request(query):
    """Detect a change/refinement request.

    Returns (instruction, params, inline_content) or None. instruction is one
    of: formal, casual, shorter, longer, upper, lower, title_case, bullets,
    replace, swap, chain, add_greeting, add_closing, remove_greeting,
    remove_closing, remove_exclamations, remove_question_marks, add_subject,
    add_punctuation, spell_numbers, remove_breaks, remove_first/last_*,
    add_title, remove_quotes, add_quotes, soften.
    """
    q = query.strip()
    if not q:
        return None
    inline = None
    if ':' in q:
        head, _, tail = q.partition(':')
        if len(tail.strip()) >= 4:
            inline = tail.strip()
            q = head.strip()
    if not q:
        return None
    q_l = q.lower()
    q_l = re.sub(r'^(?:can|could|will|would)\s+you\s+(?:please\s+)?', '', q_l)
    q_l = re.sub(r'^(?:please|now|then|just|kindly)\s+', '', q_l)

    # change/replace/rename X (to|with|into) Y — also "change ALL X to Y"
    # and "change the WORD X to Y"
    m = re.match(r'^(?:change|replace)\s+(?:all\s+|every\s+)?["\'\u201c\u201d]?(.+?)["\'\u201c\u201d]?\s+(?:to|with|into)\s+["\'\u201c\u201d]?(.+?)["\'\u201c\u201d]?\s*$', q_l)
    if m:
        old = re.sub(r'^(?:the|a|an)\s+', '', m.group(1).strip())
        old = re.sub(r'^(?:word|phrase|words|phrases|term|terms)\s+', '', old)
        return ('replace', (old, m.group(2).strip()), inline)
    m = re.match(r'^rename\s+([\w]+)\s+to\s+([\w]+)\s*$', q_l)
    if m:
        return ('replace', (m.group(1), m.group(2)), inline)

    # make it/this/the X (more) ADJ — "make it sound more professional",
    # "make it friendlier", "make this text shorter"
    _obj = r'(?:it|this|that|(?:this|that|the)\s+[\w-]+)'
    m = re.match(r'^make\s+' + _obj + r'(?:\s+(?:sound|look|read|come\s+across))?\s+(?:a\s+bit\s+|a\s+little\s+|much\s+|way\s+)?(?:more\s+)?(formal|professional|polite|casual|friendly|friendlier|informal|relaxed)\s*$', q_l)
    if m:
        t = m.group(1)
        if t == 'polite':
            return ('polite', None, inline)
        return ('formal' if t in ('formal', 'professional') else 'casual', None, inline)
    m = re.match(r'^make\s+' + _obj + r'(?:\s+(?:sound|look|read))?\s+(shorter|longer|more\s+concise|more\s+detailed|uppercase|lowercase|title\s+case|all\s+caps|bullet\s+points|a\s+list|more\s+polite)\s*$', q_l)
    if m:
        t = m.group(1).replace(' ', '_')
        if t in ('more_concise',):
            return ('shorter', None, inline)
        if t == 'more_detailed':
            return ('longer', None, inline)
        if t in ('uppercase', 'all_caps'):
            return ('upper', None, inline)
        if t == 'lowercase':
            return ('lower', None, inline)
        if t == 'title_case':
            return ('title_case', None, inline)
        if t in ('bullet_points', 'a_list'):
            return ('bullets', None, inline)
        if t == 'more_polite':
            return ('polite', None, inline)
        return (t, None, inline)

    # rewrite/reword/rephrase X (to be) more formal/casual/concise...
    m = re.match(r'^(?:rewrite|reword|rephrase)\s+(?:it|this|that|(?:this|the)\s+[\w-]+)?\s+(?:to\s+be\s+)?more\s+(formal|professional|polite|casual|friendly|concise|detailed)\b', q_l)
    if m:
        t = m.group(1)
        return ({'formal': 'formal', 'professional': 'formal', 'polite': 'polite',
                 'casual': 'casual', 'friendly': 'casual',
                 'concise': 'shorter', 'detailed': 'longer'}[t], None, inline)

    # bare commands: shorten it, uppercase this, condense that, soften it...
    m = re.match(r'^(shorten|uppercase|lowercase|capitalize|condense|trim|expand|soften|tone)\s+' + _obj + r'\s*$', q_l)
    if m:
        t = m.group(1)
        return ({'shorten': 'shorter', 'uppercase': 'upper', 'lowercase': 'lower',
                 'capitalize': 'title_case', 'condense': 'shorter', 'trim': 'shorter',
                 'expand': 'longer', 'soften': 'soften', 'tone': 'soften'}[t], None, inline)
    m = re.match(r'^(?:cut|trim)\s+(?:it|this|that)\s+down\s*$', q_l)
    if m:
        return ('shorter', None, inline)
    m = re.match(r'^tighten\s+(?:it|this|that)\s+up\s*$', q_l)
    if m:
        return ('shorter', None, inline)
    if q_l in ('make it shorter', 'shorter'):
        return ('shorter', None, inline)
    m = re.match(r'^add\s+(?:a\s+|an\s+)?(greeting|salutation|closing|sign[- ]off)\s*$', q_l)
    if m:
        return ('add_greeting' if m.group(1) in ('greeting', 'salutation') else 'add_closing', None, inline)
    # "remove the greeting and the closing" — both removed
    m = re.match(r'^remove\s+(?:the\s+)?(greeting|salutation|closing|sign[- ]off)\s+and\s+(?:the\s+)?(greeting|salutation|closing|sign[- ]off)\s*$', q_l)
    if m:
        _first = 'remove_greeting' if m.group(1) in ('greeting', 'salutation') else 'remove_closing'
        _second = 'remove_greeting' if m.group(2) in ('greeting', 'salutation') else 'remove_closing'
        return ('chain', [_first, _second], inline)
    m = re.match(r'^remove\s+(?:the\s+)?(greeting|salutation|closing|sign[- ]off)\s*$', q_l)
    if m:
        return ('remove_greeting' if m.group(1) in ('greeting', 'salutation') else 'remove_closing', None, inline)
    m = re.match(r'^remove\s+(?:all\s+|the\s+)?(exclamation\s*marks?|exclamations|question\s*marks?)\s*$', q_l)
    if m:
        return ('remove_exclamations' if 'exclam' in m.group(1) else 'remove_question_marks', None, inline)
    # "remove the first 2 sentences" / "remove the last three lines"
    # (must come BEFORE the singular remove pattern)
    _NUM_WORDS = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
                  'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10}
    m = re.match(r'^remove\s+(?:the\s+)?(first|last)\s+(\d+|[a-z]+)\s+(sentence|paragraph|line)s?\s*$', q_l)
    if m:
        _n = int(m.group(2)) if m.group(2).isdigit() else _NUM_WORDS.get(m.group(2), 1)
        return ('remove_n', (m.group(1), m.group(3), _n), inline)
    # "remove the first and last sentence" / "remove the first sentence and
    # the last sentence" — two removals in one request (must come BEFORE the
    # single remove pattern so the second half isn't silently dropped)
    m = re.match(r'^remove\s+(?:the\s+)?(first)\s+and\s+(?:the\s+)?(last)\s+(sentence|paragraph|line)\s*$', q_l)
    if m:
        return ('chain', [f'remove_{m.group(1)}_{m.group(3)}', f'remove_{m.group(2)}_{m.group(3)}'], inline)
    m = re.match(r'^remove\s+(?:the\s+)?(first|last)\s+(sentence|paragraph|line)\s+and\s+(?:the\s+)?(first|last)\s+(sentence|paragraph|line)\s*$', q_l)
    if m:
        return ('chain', [f'remove_{m.group(1)}_{m.group(2)}', f'remove_{m.group(3)}_{m.group(4)}'], inline)
    m = re.match(r'^remove\s+(?:the\s+)?(first|last)\s+(sentence|paragraph|line|word)\b', q_l)
    if m:
        which, unit = m.group(1), m.group(2)
        return (f'remove_{which}_{unit}', None, inline)
    m = re.match(r'^add\s+(?:a\s+|an\s+)?subject(?:\s+line)?\b', q_l)
    if m:
        return ('add_subject', None, inline)
    m = re.match(r'^add\s+(?:a\s+|an\s+)?(?:some\s+|missing\s+)?(punctuation|periods?|full\s+stop)s?\b', q_l)
    if m:
        return ('add_punctuation', None, inline)
    m = re.match(r'^spell\s+out\s+(?:the\s+)?numbers?\b', q_l)
    if m:
        return ('spell_numbers', None, inline)
    m = re.match(r'^remove\s+(?:the\s+)?(?:line\s+breaks?|paragraph\s+breaks?)\b', q_l)
    if m:
        return ('remove_breaks', None, inline)
    m = re.match(r'^make\s+(?:it|this|that)\s+one\s+paragraph\b', q_l)
    if m:
        return ('remove_breaks', None, inline)
    m = re.match(r'^turn\s+(?:it|this|that)\s+into\s+(?:a\s+)?(?:list|bullet\s*points|bullets)\s*$', q_l)
    if m:
        return ('bullets', None, inline)
    m = re.match(r'^(?:make|convert)\s+(?:it|this|that)\s+(?:in)?to\s+(?:a\s+)?(?:list|bullet\s*points|bullets)\s*$', q_l)
    if m:
        return ('bullets', None, inline)
    m = re.match(r'^convert\s+(?:it|this|that)\s+to\s+(?:a\s+)?list\s*$', q_l)
    if m:
        return ('bullets', None, inline)
    # add a title / headline
    m = re.match(r'^add\s+(?:a\s+|an\s+)?(title|headline)\s*$', q_l)
    if m:
        return ('add_title', None, inline)
    # remove the subject line / title (inverses)
    m = re.match(r'^remove\s+(?:the\s+)?subject(?:\s+line)?\b', q_l)
    if m:
        return ('remove_subject', None, inline)
    m = re.match(r'^remove\s+(?:the\s+)?(title|headline)\s*$', q_l)
    if m:
        return ('remove_title', None, inline)
    # remove bullet points (inverse of bullets)
    m = re.match(r'^(?:remove|un)\s*(?:the\s+)?(?:bullet\s*points?|bullets?|list\s+formatting|bulleted\s+list)\b', q_l)
    if m:
        return ('remove_bullets', None, inline)
    m = re.match(r'^make\s+(?:it|this|that)\s+(?:into\s+)?a\s+paragraph\b', q_l)
    if m:
        return ('remove_bullets', None, inline)
    # remove duplicate / repeated words
    m = re.match(r'^(?:remove|fix|delete)\s+(?:the\s+)?(?:duplicate|repeated|double)\s+words?\b', q_l)
    if m:
        return ('remove_duplicates', None, inline)
    # put each sentence on its own line
    m = re.match(r'^(?:put|make|split)\s+(?:each\s+|every\s+)?(?:sentence|line)\s+(?:on\s+its\s+own\s+line|per\s+line|into\s+(?:separate\s+)?lines?)\s*$', q_l)
    if m:
        return ('add_line_breaks', None, inline)
    m = re.match(r'^add\s+(?:line\s+)?breaks?\s*$', q_l)
    if m:
        return ('add_line_breaks', None, inline)
    # quotes
    m = re.match(r'^remove\s+(?:all\s+|the\s+)?quotes?\s*$', q_l)
    if m:
        return ('remove_quotes', None, inline)
    m = re.match(r'^(?:put\s+(?:it|this|that)\s+in|add|wrap\s+(?:it|this|that)\s+in)\s+(?:double\s+|single\s+)?quotes?\s*$', q_l)
    if m:
        return ('add_quotes', None, inline)
    # soften the tone
    m = re.match(r'^(?:soften|soothe)\s+(?:the\s+)?(?:tone|language|wording|it|this|that)\s*$', q_l)
    if m:
        return ('soften', None, inline)
    m = re.match(r'^tone\s+(?:it|this|that)\s+down\s*$', q_l)
    if m:
        return ('soften', None, inline)
    m = re.match(r'^make\s+(?:it|this|that|the\s+[\w-]+)\s+(?:sound\s+|come\s+across\s+)?less\s+(angry|harsh|aggressive|abrupt|rude|blunt|sharp|negative|mean|hostile|intense)\s*$', q_l)
    if m:
        return ('soften', None, inline)
    # swap the first and last word/sentence/paragraph/line (BEFORE the
    # generic "swap X and Y" so "swap the first and last word" isn't
    # parsed as swapping "first" with "last word")
    m = re.match(r'^swap\s+(?:the\s+)?(?:first\s+and\s+last|last\s+and\s+first)\s+(word|sentence|paragraph|line)\s*$', q_l)
    if m:
        return ('swap_first_last', m.group(1), inline)
    # swap/switch X and Y
    m = re.match(r'^(?:swap|switch)\s+["\'\u201c\u201d]?(.+?)["\'\u201c\u201d]?\s+(?:and|with)\s+["\'\u201c\u201d]?(.+?)["\'\u201c\u201d]?\s*$', q_l)
    if m:
        def _clean_swap(t):
            t = re.sub(r'^(?:the|a|an)\s+', '', t.strip())
            t = re.sub(r'\s+(?:words?|terms?|phrases?)$', '', t)
            return t
        return ('swap', (_clean_swap(m.group(1)), _clean_swap(m.group(2))), inline)
    # sort / alphabetize a list
    m = re.match(r'^(?:sort|alphabetize|alphabetise)\s*(?:it|this|that|the\s+(?:list|items|lines))?\s*(?:alphabetically)?\s*$', q_l)
    if m:
        return ('sort', None, inline)
    # reverse sentence/line/word order
    m = re.match(r'^reverse\s+(?:it|this|that|the\s+(?:order|list|sentences|lines|words))\s*$', q_l)
    if m:
        return ('reverse', None, inline)
    m = re.match(r'^reverse\s+(?:the\s+)?order\s+of\s+(?:the\s+)?(?:sentences?|lines?|words?|items?)\s*$', q_l)
    if m:
        return ('reverse', None, inline)
    m = re.match(r'^put\s+the\s+last\s+(sentence|paragraph|line)\s+first\s*$', q_l)
    if m:
        return ('reverse', None, inline)
    # remove numbers / punctuation
    m = re.match(r'^remove\s+(?:all\s+|the\s+)?numbers?\b', q_l)
    if m:
        return ('remove_numbers', None, inline)
    m = re.match(r'^remove\s+(?:all\s+|the\s+)?punctuation\b', q_l)
    if m:
        return ('remove_punctuation', None, inline)
    # add exclamation marks / make it more exciting
    m = re.match(r'^add\s+(?:an?\s+|some\s+|the\s+)?(?:exclamation\s*marks?|exclamation\s*points?|excitement)\s*$', q_l)
    if m:
        return ('add_exclamations', None, inline)
    m = re.match(r'^make\s+(?:it|this|that|this\s+text)\s+(?:sound\s+|read\s+)?more\s+(excited|exciting|enthusiastic|energetic|enthused)\s*$', q_l)
    if m:
        return ('add_exclamations', None, inline)
    m = re.match(r'^(?:remove|delete)\s+(?:all\s+|the\s+)?(?:emojis?|emoji\s*characters?|emoticons?|emotes?)\b', q_l)
    if m:
        return ('remove_emojis', None, inline)
    # parentheses
    m = re.match(r'^(?:put|wrap)\s+(?:it|this|that)\s+in(?:to)?\s+(?:parentheses|brackets)\s*$', q_l)
    if m:
        return ('add_parentheses', None, inline)
    m = re.match(r'^remove\s+(?:the\s+)?(?:parentheses|brackets)\s*$', q_l)
    if m:
        return ('remove_parentheses', None, inline)
    # add / remove a date line
    m = re.match(r'^add\s+(?:a\s+|the\s+|today\'?s\s+)?date\s*$', q_l)
    if m:
        return ('add_date', None, inline)
    m = re.match(r'^remove\s+(?:the\s+)?date\s*$', q_l)
    if m:
        return ('remove_date', None, inline)
    # double / single spacing
    m = re.match(r'^make\s+(?:it|this|that)\s+double[- ]spaced\s*$', q_l)
    if m:
        return ('double_space', None, inline)
    m = re.match(r'^make\s+(?:it|this|that)\s+single[- ]spaced\s*$', q_l)
    if m:
        return ('single_space', None, inline)
    # turn a statement into a question
    m = re.match(r'^(?:make|turn|convert)\s+(?:it|this|that|this\s+sentence|this\s+statement)\s+(?:into\s+|in\s+|to\s+)?(?:a\s+)?question\s*$', q_l)
    if m:
        return ('make_question', None, inline)
    # tense conversions
    m = re.match(r'^(?:make|put|convert|change)\s+(?:it|this|that|this\s+text|this\s+sentence|this\s+paragraph)\s+(?:into\s+|in\s+|to\s+)?(?:the\s+|past\s+)?(?:past\s+tense|past)\s*$', q_l)
    if m:
        return ('make_past', None, inline)
    m = re.match(r'^(?:make|put|convert|change)\s+(?:it|this|that|this\s+text|this\s+sentence|this\s+paragraph)\s+(?:into\s+|in\s+|to\s+)?(?:the\s+|present\s+)?(?:present\s+tense|present)\s*$', q_l)
    if m:
        return ('make_present', None, inline)
    m = re.match(r'^(?:make|turn|convert)\s+(?:it|this|that|this\s+sentence|this\s+statement)\s+(?:into\s+|in\s+|to\s+)?(?:a\s+)?negative\s*(?:statement)?\s*$', q_l)
    if m:
        return ('make_negative', None, inline)
    # remove empty lines
    m = re.match(r'^remove\s+(?:all\s+|the\s+)?(?:empty|blank)\s+lines?\b', q_l)
    if m:
        return ('remove_empty_lines', None, inline)
    # chained requests: "make it shorter and more formal", "add a greeting
    # and a closing" — both halves must parse as known change phrases
    _parts = re.split(r'\s+and\s+', q_l)
    if len(_parts) == 2:
        _i1, _i2 = _parse_change_clause(_parts[0]), _parse_change_clause(_parts[1])
        if _i1 and _i2:
            return ('chain', [_i1, _i2], inline)
    return None


def apply_change(instruction, content, params=None, kind=None):
    """Apply a detected change request to content. Returns (edited, notes)."""
    if kind in ('code', 'json', 'css', 'html', 'sql', 'bash') and instruction in _TEXT_ONLY_CHANGES:
        return content, ["That change doesn't apply to code/data — paste text instead, or ask for a rename/format change."]
    if instruction == 'chain':
        # Sequential chained changes: each sub-instruction applies to the
        # result of the previous one; text-only steps are skipped on code.
        notes = []
        for sub in (params or []):
            if kind in ('code', 'json', 'css', 'html', 'sql', 'bash') and sub in _TEXT_ONLY_CHANGES:
                notes.append(f'skipped "{sub}" — that change doesn\'t apply to code/data')
                continue
            content, sub_notes = apply_change(sub, content, None, kind=kind)
            notes.extend(sub_notes)
        return content, notes
    if instruction == 'formal':
        result = formalize(content)
        if result == content:
            return content, ["the text is already formal — nothing to change"]
        return result, ["made the text more formal"]
    if instruction == 'polite':
        return polite(content)
    if instruction == 'casual':
        return casualize(content), ["made the text more casual"]
    if instruction == 'shorter':
        result = shorten(content)
        if result == content:
            return content, ["the text is already concise — nothing to shorten"]
        return result, ["shortened the text"]
    if instruction == 'longer':
        # Deterministic lengthening: expand contractions and abbreviations
        # ("don't" -> "do not", "i.e." -> "that is", "&" -> "and") — never
        # invents new content.
        expanded = content
        for w, r in _FORMAL_WORDS.items():
            if "'" in w or w in ('im', 'dont', 'cant', 'wont'):
                expanded = re.sub(r'\b' + re.escape(w) + r'\b', r, expanded, flags=re.IGNORECASE)
        expanded = re.sub(r'\bi\.e\.(?=\s|[,;:!?]|$)', 'that is', expanded, flags=re.IGNORECASE)
        expanded = re.sub(r'\be\.g\.(?=\s|[,;:!?]|$)', 'for example', expanded, flags=re.IGNORECASE)
        expanded = re.sub(r'\bvs\.(?=\s|[,;:!?]|$)', 'versus', expanded, flags=re.IGNORECASE)
        expanded = re.sub(r'\s+&\s+', ' and ', expanded)  # AT&T stays put
        if expanded != content:
            return expanded, ["expanded contractions and abbreviations to make it longer"]
        return content, ["I can't invent new content — I kept it as-is. I can make it more formal, shorter, or add a greeting/closing."]
    if instruction == 'upper':
        return content.upper(), ["converted to uppercase"]
    if instruction == 'lower':
        return content.lower(), ["converted to lowercase"]
    if instruction == 'title_case':
        return content.title(), ["converted to title case"]
    if instruction == 'bullets':
        return to_bullets(content), ["turned into bullet points"]
    if instruction == 'replace':
        if not params or len(params) != 2:
            return content, ["I need a 'change X to Y' instruction with both terms."]
        old, new = params
        fixed = re.sub(r'\b' + re.escape(old) + r'\b', new, content, flags=re.IGNORECASE)
        if fixed == content:
            return content, [f'"{old}" not found — nothing to replace.']
        return fixed, [f'changed "{old}" -> "{new}"']
    if instruction == 'swap':
        if not params or len(params) != 2:
            return content, ["I need a 'swap X and Y' instruction with both terms."]
        x, y = params[0], params[1]
        ph_x, ph_y = '\u0001SWAPX\u0001', '\u0001SWAPY\u0001'
        tmp = re.sub(r'\b' + re.escape(x) + r'\b', ph_x, content, flags=re.IGNORECASE)
        tmp = re.sub(r'\b' + re.escape(y) + r'\b', ph_y, tmp, flags=re.IGNORECASE)
        fixed = tmp.replace(ph_y, x).replace(ph_x, y)
        # a swapped-in bare "i" must be capitalized ("i and you" -> "I and you")
        fixed = re.sub(r"(^|[\s.!?;:])i([\s.,!?;:'\"]|$)", r'\1I\2', fixed)
        if fixed == content:
            return content, [f'"{x}" or "{y}" not found — nothing to swap.']
        return fixed, [f'swapped "{x}" <-> "{y}"']
    if instruction == 'add_greeting':
        return 'Hello,\n\n' + content, ["added a greeting"]
    if instruction == 'add_closing':
        return content.rstrip() + '\n\nBest regards,', ["added a closing"]
    if instruction == 'remove_greeting':
        sep = '\n\n' if '\n\n' in content else '\n'
        lines = content.split(sep)
        if lines and re.match(r'^(?:hi|hello|hey|dear|good\s+(?:morning|afternoon|evening))\b', lines[0].strip(), re.IGNORECASE):
            return sep.join(lines[1:]), ["removed the greeting"]
        return content, ["no greeting found to remove"]
    if instruction == 'remove_closing':
        m = re.search(r'\n\n(?:best|kind|warm|thanks|thank you|regards|sincerely)[^\n]*\s*$', content, re.IGNORECASE)
        if m:
            return content[:m.start()], ["removed the closing"]
        return content, ["no closing found to remove"]
    if instruction == 'remove_exclamations':
        return content.replace('!', ''), ["removed exclamation marks"]
    if instruction == 'remove_question_marks':
        return content.replace('?', ''), ["removed question marks"]
    if instruction == 'add_title':
        if re.match(r'^title\s*:', content, re.IGNORECASE):
            return content, ["already has a title"]
        first_sent = re.split(r'(?<=[.!?])\s+', content)[0]
        return f'Title: {first_sent[:60].rstrip(".!?")}\n\n{content}', ["added a title"]
    if instruction == 'remove_quotes':
        stripped = content.strip()
        if len(stripped) >= 2 and stripped[0] in '\"\'“”‘’' and stripped[-1] in '\"\'“”‘’':
            return stripped[1:-1].strip(), ["removed the surrounding quotes"]
        fixed = (content.replace('"', '').replace("'", '').replace('“', '')
                 .replace('”', '').replace('‘', '').replace('’', ''))
        if fixed != content:
            return fixed, ["removed all quotation marks"]
        return content, ["no quotes found to remove"]
    if instruction == 'remove_subject':
        lines = content.split('\n')
        if lines and re.match(r'^subject\s*:', lines[0], re.IGNORECASE):
            return '\n'.join(lines[1:]).lstrip('\n'), ["removed the subject line"]
        return content, ["no subject line found to remove"]
    if instruction == 'remove_title':
        lines = content.split('\n')
        if lines and re.match(r'^title\s*:', lines[0], re.IGNORECASE):
            return '\n'.join(lines[1:]).lstrip('\n'), ["removed the title"]
        return content, ["no title found to remove"]
    if instruction == 'remove_bullets':
        if not re.search(r'^[-*•]\s+', content, re.MULTILINE):
            # no bullets: "make it a paragraph" on plain lines = join them
            fixed = re.sub(r'\s*\n+\s*', ' ', content).strip()
            if fixed != content:
                return fixed, ["joined it into one paragraph"]
            return content, ["no bullet points found to remove"]
        lines = [re.sub(r'^[-*•]\s+', '', ln) for ln in content.split('\n')]
        joined = ' '.join(ln.strip() for ln in lines if ln.strip())
        if joined and joined[-1] not in '.!?':
            joined = joined.rstrip() + '.'
        return joined, ["removed bullet points"]
    if instruction == 'remove_duplicates':
        def _dedup2(m):
            w = m.group(1)
            return m.group(0) if w.lower() in _DUP_ALLOW else w
        fixed = re.sub(r'\b([\w\']+)\s+\1\b', _dedup2, content, flags=re.IGNORECASE)
        if fixed == content:
            return content, ["no duplicate words found"]
        return fixed, ["removed accidentally repeated words"]
    if instruction == 'add_line_breaks':
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', content) if s.strip()]
        if len(sentences) <= 1 or '\n' in content:
            return content, ["already one sentence per line"]
        return '\n'.join(sentences), ["put each sentence on its own line"]
    if instruction == 'sort':
        lines = content.split('\n')
        if len(lines) > 1:
            key = lambda s: re.sub(r'^[-*•]\s+', '', s).strip().lower()
            fixed = '\n'.join(sorted(lines, key=key))
            if fixed != content:
                return fixed, ["sorted the list"]
            return content, ["the list is already sorted"]
        items = [i.strip() for i in re.split(r',\s+', content) if i.strip()]
        if len(items) > 1:
            return ', '.join(sorted(items, key=lambda s: s.lower())), ["sorted the items"]
        return content, ["nothing to sort — paste a list of lines or items"]
    if instruction == 'reverse':
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', content) if s.strip()]
        if len(sentences) > 1:
            return ' '.join(reversed(sentences)), ["reversed the sentence order"]
        lines = [l for l in content.split('\n') if l.strip()]
        if len(lines) > 1:
            return '\n'.join(reversed(lines)), ["reversed the line order"]
        words = content.split()
        if len(words) > 1:
            return ' '.join(reversed(words)), ["reversed the word order"]
        return content, ["only one item — nothing to reverse"]
    if instruction == 'remove_numbers':
        fixed = re.sub(r'\s{2,}', ' ', re.sub(r'\d+', '', content)).strip()
        if fixed == content:
            return content, ["no numbers found to remove"]
        return fixed, ["removed all numbers"]
    if instruction == 'remove_punctuation':
        fixed = re.sub(r'[.,;:!?"()\[\]{}<>“”‘’—–]', '', content)
        fixed = re.sub(r'\s{2,}', ' ', fixed).strip()
        if fixed == content:
            return content, ["no punctuation found to remove"]
        return fixed, ["removed all punctuation"]
    if instruction == 'remove_emojis':
        fixed = re.sub(
            r'[\U0001F000-\U0001FAFF\U0001F1E6-\U0001F1FF\u2600-\u27BF\u2B50\u2764\uFE0F\u2705\u274C\u2753-\u2757\u2660-\u2667\u25AA-\u25FE]',
            '', content)
        fixed = re.sub(r'\s{2,}', ' ', fixed).strip()
        if fixed == content:
            return content, ["no emojis found to remove"]
        return fixed, ["removed emojis"]
    if instruction == 'add_parentheses':
        return '(' + content.strip() + ')', ["wrapped in parentheses"]
    if instruction == 'remove_parentheses':
        stripped = content.strip()
        if len(stripped) >= 2 and stripped[0] == '(' and stripped[-1] == ')':
            return stripped[1:-1].strip(), ["removed the surrounding parentheses"]
        fixed = re.sub(r'[()]', '', content)
        if fixed != content:
            return fixed, ["removed all parentheses"]
        return content, ["no parentheses found to remove"]
    if instruction == 'swap_first_last':
        unit = params or 'word'
        if unit == 'sentence':
            parts = re.split(r'(?<=[.!?])\s+', content)
            sep = ' '
        elif unit == 'paragraph':
            parts = [p for p in content.split('\n\n') if p.strip()]
            sep = '\n\n'
        elif unit == 'line':
            parts = content.split('\n')
            sep = '\n'
        else:
            parts = content.split()
            sep = ' '
        if len(parts) < 2:
            return content, [f"only one {unit} — nothing to swap"]
        parts[0], parts[-1] = parts[-1], parts[0]
        return sep.join(parts), [f"swapped the first and last {unit}"]
    if instruction == 'add_date':
        import datetime as _dt
        _today = _dt.date.today()
        _months = ['January', 'February', 'March', 'April', 'May', 'June',
                   'July', 'August', 'September', 'October', 'November',
                   'December']
        _date_str = f"{_months[_today.month - 1]} {_today.day}, {_today.year}"
        return f'Date: {_date_str}\n\n{content}', ["added today's date"]
    if instruction == 'remove_date':
        lines = content.split('\n')
        if lines and re.match(r'^date\s*:', lines[0], re.IGNORECASE):
            return '\n'.join(lines[1:]).lstrip('\n'), ["removed the date line"]
        return content, ["no date line found to remove"]
    if instruction == 'double_space':
        if '\n\n' in content:
            return content, ["already double-spaced"]
        fixed = re.sub(r'\n+', '\n\n', content)
        if fixed != content:
            return fixed, ["made it double-spaced"]
        return content, ["already double-spaced"]
    if instruction == 'single_space':
        fixed = re.sub(r'\n{2,}', '\n', content)
        if fixed != content:
            return fixed, ["made it single-spaced"]
        return content, ["already single-spaced"]
    if instruction == 'remove_empty_lines':
        fixed = '\n'.join(l for l in content.split('\n') if l.strip())
        if fixed == content:
            return content, ["no empty lines found to remove"]
        return fixed, ["removed empty lines"]
    if instruction == 'make_question':
        q = make_question(content)
        if q is None:
            return content, ["I can only convert simple statements (e.g. 'She is ready.' or 'They went home.') into questions."]
        return q, ["converted the statement into a question"]
    if instruction == 'make_past':
        past = make_past(content)
        if past == content:
            return content, ["the text already reads as past tense — nothing to change"]
        return past, ["rewrote the text in the past tense"]
    if instruction == 'make_present':
        present = make_present(content)
        if present == content:
            return content, ["the text already reads as present tense — nothing to change"]
        return present, ["rewrote the text in the present tense"]
    if instruction == 'add_exclamations':
        fixed = re.sub(r'\.(?=\s|$)', '!', content)
        if fixed and fixed[-1] not in '.!?':
            fixed = fixed + '!'
        if fixed == content:
            return content, ["no sentences to add excitement to"]
        return fixed, ["turned sentence endings into exclamation marks"]
    if instruction == 'make_negative':
        neg = make_negative(content)
        if neg is None:
            return content, ["I can only negate simple statements (e.g. 'She likes pizza.' or 'They went home.')."]
        if neg == content:
            return content, ["the statement is already negative"]
        return neg, ["turned the statement negative"]
    if instruction == 'add_quotes':
        return '“' + content.strip() + '”', ["wrapped in quotes"]
    if instruction == 'soften':
        # Remove shouting: ALL-CAPS words (except common acronyms) become
        # lowercase, !!! become '.', then sentence starts are re-capitalized.
        _ACRONYMS = {'US', 'USA', 'UK', 'EU', 'UN', 'AI', 'CPU', 'GPU', 'RAM',
                     'ROM', 'HTTP', 'HTTPS', 'URL', 'HTML', 'CSS', 'API', 'JSON',
                     'SQL', 'NASA', 'FBI', 'CIA', 'NATO', 'ASAP', 'PDF', 'DNA',
                     'GPS', 'USB', 'CEO', 'CTO', 'CFO'}
        fixed = re.sub(r'\b([A-Z]{2,})\b',
                       lambda m: m.group(1) if m.group(1) in _ACRONYMS else m.group(1).lower(),
                       content)
        fixed = re.sub(r'!+', '.', fixed)
        fixed = re.sub(r'\s+([.,])', r'\1', fixed)
        fixed = _capitalize_sentence_starts(fixed)
        fixed = re.sub(r' +', ' ', fixed)
        if fixed == content:
            return content, ["the tone is already calm — nothing to soften"]
        return fixed, ["softened the tone (lowered shouting and removed exclamation marks)"]
    if instruction in ('remove_first_sentence', 'remove_last_sentence'):
        sentences = re.split(r'(?<=[.!?])\s+', content)
        if len(sentences) <= 1:
            return content, ["only one sentence — nothing to remove"]
        if instruction == 'remove_first_sentence':
            return ' '.join(sentences[1:]), ["removed the first sentence"]
        return ' '.join(sentences[:-1]), ["removed the last sentence"]
    if instruction in ('remove_first_word', 'remove_last_word'):
        words = content.split()
        if len(words) <= 1:
            return content, ["only one word — nothing to remove"]
        if instruction == 'remove_first_word':
            return ' '.join(words[1:]), ["removed the first word"]
        return ' '.join(words[:-1]), ["removed the last word"]
    if instruction == 'remove_n':
        if not params or len(params) != 3:
            return content, ["I need a 'remove the first/last N sentences' instruction."]
        which, unit, n = params
        if unit == 'sentence':
            parts = re.split(r'(?<=[.!?])\s+', content)
            sep = ' '
        elif unit == 'paragraph':
            parts = [p for p in content.split('\n\n') if p.strip()]
            sep = '\n\n'
        else:
            parts = content.split('\n')
            sep = '\n'
        if len(parts) <= n:
            return content, [f"only {len(parts)} {unit}s — nothing to remove"]
        if which == 'first':
            fixed = sep.join(parts[n:])
        else:
            fixed = sep.join(parts[:-n])
        return fixed, [f"removed the {which} {n} {unit}s"]
    if instruction in ('remove_first_paragraph', 'remove_last_paragraph'):
        paras = [p for p in content.split('\n\n') if p.strip()]
        if len(paras) <= 1:
            return content, ["only one paragraph — nothing to remove"]
        if instruction == 'remove_first_paragraph':
            return '\n\n'.join(paras[1:]), ["removed the first paragraph"]
        return '\n\n'.join(paras[:-1]), ["removed the last paragraph"]
    if instruction == 'remove_first_line':
        lines = content.split('\n')
        if len(lines) <= 1:
            return content, ["only one line — nothing to remove"]
        return '\n'.join(lines[1:]), ["removed the first line"]
    if instruction == 'remove_last_line':
        lines = content.split('\n')
        if len(lines) <= 1:
            return content, ["only one line — nothing to remove"]
        return '\n'.join(lines[:-1]), ["removed the last line"]
    if instruction == 'add_subject':
        if re.match(r'^subject\s*:', content, re.IGNORECASE):
            return content, ["already has a subject line"]
        first_sent = re.split(r'(?<=[.!?])\s+', content)[0]
        subject = first_sent[:60].rstrip('.!?')
        return f'Subject: {subject}\n\n{content}', ["added a subject line"]
    if instruction == 'add_punctuation':
        def _fix_end(s):
            s = s.rstrip()
            return s + '.' if s and s[-1] not in '.!?' else s
        out = [_fix_end(s) for s in re.split(r'(?<=[.!?])\s+', content)]
        fixed = ' '.join(out)
        return fixed, ["added missing sentence-ending punctuation"]
    if instruction == 'spell_numbers':
        _ones = ['', 'one', 'two', 'three', 'four', 'five', 'six', 'seven',
                 'eight', 'nine', 'ten', 'eleven', 'twelve', 'thirteen',
                 'fourteen', 'fifteen', 'sixteen', 'seventeen', 'eighteen',
                 'nineteen']
        _tens = ['', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty',
                 'seventy', 'eighty', 'ninety']
        def _to_words(n):
            n = int(n)
            if n < 20:
                return _ones[n] if n else 'zero'
            t, o = divmod(n, 10)
            return _tens[t] + ('-' + _ones[o] if o else '')
        # don't touch decimals (3.14), thousands (1,000), or years like 2024
        fixed = re.sub(
            r'(?<![.,])\b(\d{1,2})\b(?![.,\d])',
            lambda m: _to_words(m.group(1)), content)
        if fixed == content:
            return content, ["no numbers found to spell out"]
        fixed = re.sub(r"(^|[\s.!?;:])i([\s.,!?;:'\"]|$)", r'\1I\2', fixed)
        fixed = _capitalize_sentence_starts(fixed)
        fixed = re.sub(r' +', ' ', fixed)
        return fixed, ["spelled out numbers"]
    if instruction == 'remove_breaks':
        fixed = re.sub(r'\s*\n+\s*', ' ', content).strip()
        return fixed, ["removed line breaks"]
    return content, [f"I don't know how to apply '{instruction}' yet."]


def formalize(text):
    fixed = text
    for w, r in _FORMAL_WORDS.items():
        def _repl(m, r=r):
            return r if not m.group(0)[:1].isupper() else r[0].upper() + r[1:]
        fixed = re.sub(r'\b' + re.escape(w) + r'\b', _repl, fixed, flags=re.IGNORECASE)
    return fixed


def casualize(text):
    fixed = text
    for w, r in _CASUAL_WORDS.items():
        fixed = re.sub(r'\b' + re.escape(w) + r'\b', r, fixed, flags=re.IGNORECASE)
    return fixed


def shorten(text):
    _FILLERS = {'very', 'really', 'just', 'actually', 'basically', 'literally',
                'honestly', 'quite', 'simply', 'truly', 'totally', 'completely',
                'entirely', 'absolutely', 'definitely', 'certainly', 'pretty',
                'rather', 'somewhat', 'fairly'}
    words = [w for w in text.split() if w.lower().rstrip('.,!?') not in _FILLERS]
    reduced = ' '.join(words)
    # Trim trailing "and then <result>" / "and after that ..." clauses that
    # add length without adding information ("jumps ... and then it goes to
    # sleep" -> "jumps over the lazy dog").
    reduced = re.sub(r'\s+(?:and\s+then|and\s+after\s+that|and\s+afterwards|'
                     r'and\s+finally)\s+.*$', '', reduced, flags=re.IGNORECASE)
    # Trim trailing "in order to" purpose clauses when the text is short.
    reduced = re.sub(r'\s+(?:so\s+that|in\s+order\s+to|for\s+the\s+purpose\s+of)'
                     r'\s+.*$', '', reduced, flags=re.IGNORECASE)
    sentences = re.split(r'(?<=[.!?])\s+', reduced)
    if len(sentences) > 3:
        return ' '.join(sentences[:3]).rstrip() + ' …'
    return reduced


def polite(text):
    """Make a text more polite: soften demands, add please and a thank-you."""
    fixed = text.strip()
    original = fixed
    changes = []

    # soften request imperatives. "give me X" is rewritten to
    # "Could you please send me X", which must not be re-softened by the
    # send-me rule, so the give rule runs alone first.
    if 'could you please' not in fixed.lower():
        _softened = False
        fixed2 = re.sub(r'\b(?:gimme|give\s+me)\b', 'Could you please send me',
                        fixed, flags=re.IGNORECASE)
        if fixed2 != fixed:
            fixed = fixed2
            _softened = True
        if not _softened:
            fixed = re.sub(r'\bsend\s+me\b', 'Could you please send me',
                           fixed, flags=re.IGNORECASE)
            fixed = re.sub(r'\bget\s+me\b', 'Could you please get me',
                           fixed, flags=re.IGNORECASE)
    fixed = re.sub(r'\bi\s+want\b', 'I would like', fixed, flags=re.IGNORECASE)
    fixed = re.sub(r'\bneed\s+(?:the\s+|a\s+|an\s+)?',
                   'I would appreciate ', fixed, flags=re.IGNORECASE, count=1)
    fixed = re.sub(r'\b(?:tell\s+me|show\s+me)\b', 'Could you please tell me',
                   fixed, flags=re.IGNORECASE, count=1)
    # drop threats / ultimatums
    fixed = re.sub(r'\s+or\s+(?:else|i\'?ll\s+\w+|you\'?ll\s+\w+)[^.]*\.?',
                   '.', fixed)
    fixed = re.sub(r'\s+or\s+else\s*[.!]?', '.', fixed)
    # soften "by friday" -> "by Friday" and add please to remaining bare asks
    fixed = re.sub(
        r'\bby\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',
        lambda m: 'by ' + m.group(1).capitalize(), fixed,
        flags=re.IGNORECASE)
    if fixed != original:
        changes.append("softened the demands into polite requests")

    # add a please if the result is still a bare imperative with no courtesy
    _first = fixed.lstrip()[:80].lower()
    if re.match(r'^(?:give|send|return|complete|finish|submit|do|make|call|'
                r'send|email|reply|answer|fix|check|review|update|provide)\b',
                _first) and 'please' not in fixed.lower():
        # insert "please" after the first word
        _m = re.match(r'^(\s*\w+)(\s+)(.*)$', fixed, re.DOTALL)
        if _m:
            fixed = _m.group(1) + ' please' + _m.group(2) + _m.group(3)
            changes.append("added 'please'")

    # close a request with a thank-you
    if (re.search(r'\b(?:could you|would you|please|i would appreciate|'
                  r'i would like)\b', fixed, re.IGNORECASE)
            and 'thank' not in fixed.lower()
            and len(fixed) < 400):
        fixed = fixed.rstrip().rstrip('.!?') + '. Thank you.'
        changes.append("added a closing 'thank you'")

    if not changes:
        return fixed, ["the text is already polite — nothing to change"]
    return fixed, changes


# ── Extractive summarization ────────────────────────────────────────────────
_SUM_STOP = {'the', 'a', 'an', 'and', 'or', 'but', 'of', 'to', 'in', 'on',
             'at', 'by', 'for', 'with', 'from', 'is', 'are', 'was', 'were',
             'be', 'been', 'being', 'it', 'its', 'this', 'that', 'these',
             'those', 'i', 'you', 'we', 'they', 'he', 'she', 'them', 'his',
             'her', 'their', 'our', 'your', 'my', 'as', 'if', 'then', 'than',
             'so', 'such', 'there', 'here', 'which', 'who', 'whom', 'what',
             'when', 'where', 'why', 'how', 'have', 'has', 'had', 'do', 'does',
             'did', 'will', 'would', 'can', 'could', 'should', 'may', 'might',
             'not', 'no', 'yes', 'also', 'too', 'very', 'just', 'about', 'into',
             'over', 'under', 'between', 'through', 'during', 'before', 'after',
             'up', 'down', 'out', 'off', 'again', 'once', 'because', 'while'}


def summarize_text(text, max_sentences=None):
    """Extractive summary: keep the sentences with the most content words.

    Sentences are scored by how many of the text's significant words they
    contain (a TF-style heuristic), then the top ones are returned in their
    original order. Deterministic and safe — it never invents content.
    """
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text.strip())
                 if s.strip()]
    if len(sentences) <= 2:
        return text.strip(), ["the text is only a sentence or two — a summary "
                              "would just repeat it"]

    words = re.findall(r'[a-zA-Z]{3,}', text.lower())
    significant = [w for w in words if w not in _SUM_STOP]
    freq = {}
    for w in significant:
        freq[w] = freq.get(w, 0) + 1

    scored = []
    for i, s in enumerate(sentences):
        sw = re.findall(r'[a-zA-Z]{3,}', s.lower())
        score = sum(freq.get(w, 0) for w in sw if w not in _SUM_STOP)
        # slight boost for the first sentence (usually the topic sentence)
        if i == 0:
            score += max(freq.values()) if freq else 0
        scored.append((score, i, s))

    n = max_sentences or max(1, round(len(sentences) * 0.4))
    n = min(n, len(sentences) - 1)
    keep = sorted([idx for _, idx, _ in scored],
                  key=lambda i: scored[i][0], reverse=True)[:n]
    ordered = [sentences[i] for i in sorted(keep)]
    summary = ' '.join(ordered)
    return summary, [f"kept the {len(ordered)} most informative sentence"
                     + ('s' if len(ordered) != 1 else '')
                     + f" out of {len(sentences)}"]


# ── Phrasebook translation ──────────────────────────────────────────────────
# Honest, bounded translation: a curated phrasebook + a few statement
# templates for the common languages. Anything outside it is refused rather
# than machine-mangled.
_TRANSLATION_PHRASES = {
    'hello': {'es': 'Hola', 'fr': 'Bonjour', 'de': 'Hallo', 'it': 'Ciao',
              'pt': 'Olá', 'nl': 'Hallo'},
    'hi': {'es': 'Hola', 'fr': 'Salut', 'de': 'Hallo', 'it': 'Ciao',
           'pt': 'Oi', 'nl': 'Hoi'},
    'good morning': {'es': 'Buenos días', 'fr': 'Bonjour', 'de': 'Guten Morgen',
                     'it': 'Buongiorno', 'pt': 'Bom dia', 'nl': 'Goedemorgen'},
    'good afternoon': {'es': 'Buenas tardes', 'fr': 'Bon après-midi',
                       'de': 'Guten Nachmittag', 'it': 'Buon pomeriggio',
                       'pt': 'Boa tarde', 'nl': 'Goedemiddag'},
    'good evening': {'es': 'Buenas noches', 'fr': 'Bonsoir', 'de': 'Guten Abend',
                     'it': 'Buonasera', 'pt': 'Boa noite', 'nl': 'Goedenavond'},
    'good night': {'es': 'Buenas noches', 'fr': 'Bonne nuit',
                   'de': 'Gute Nacht', 'it': 'Buonanotte', 'pt': 'Boa noite',
                   'nl': 'Goedenacht'},
    'goodbye': {'es': 'Adiós', 'fr': 'Au revoir', 'de': 'Auf Wiedersehen',
                'it': 'Arrivederci', 'pt': 'Tchau', 'nl': 'Tot ziens'},
    'bye': {'es': 'Adiós', 'fr': 'Salut', 'de': 'Tschüss', 'it': 'Ciao',
            'pt': 'Tchau', 'nl': 'Doei'},
    'please': {'es': 'Por favor', 'fr': "S'il vous plaît", 'de': 'Bitte',
               'it': 'Per favore', 'pt': 'Por favor', 'nl': 'Alstublieft'},
    'thank you': {'es': 'Gracias', 'fr': 'Merci', 'de': 'Danke',
                  'it': 'Grazie', 'pt': 'Obrigado', 'nl': 'Dank je'},
    'thanks': {'es': 'Gracias', 'fr': 'Merci', 'de': 'Danke', 'it': 'Grazie',
               'pt': 'Valeu', 'nl': 'Bedankt'},
    'you are welcome': {'es': 'De nada', 'fr': 'De rien', 'de': 'Gern geschehen',
                        'it': 'Prego', 'pt': 'De nada', 'nl': 'Graag gedaan'},
    'yes': {'es': 'Sí', 'fr': 'Oui', 'de': 'Ja', 'it': 'Sì', 'pt': 'Sim',
            'nl': 'Ja'},
    'no': {'es': 'No', 'fr': 'Non', 'de': 'Nein', 'it': 'No', 'pt': 'Não',
           'nl': 'Nee'},
    'how are you': {'es': '¿Cómo estás?', 'fr': 'Comment ça va ?',
                    'de': 'Wie geht es dir?', 'it': 'Come stai?',
                    'pt': 'Como você está?', 'nl': 'Hoe gaat het?'},
    'how are you doing': {'es': '¿Cómo estás?', 'fr': 'Comment ça va ?',
                          'de': 'Wie geht es dir?', 'it': 'Come stai?',
                          'pt': 'Como você está?', 'nl': 'Hoe gaat het met je?'},
    "what is your name": {'es': '¿Cómo te llamas?', 'fr': "Comment tu t'appelles ?",
                          'de': 'Wie heißt du?', 'it': 'Come ti chiami?',
                          'pt': 'Como você se chama?', 'nl': 'Hoe heet je?'},
    "my name is": {'es': 'Me llamo', 'fr': "Je m'appelle", 'de': 'Ich heiße',
                    'it': 'Mi chiamo', 'pt': 'Meu nome é', 'nl': 'Ik heet'},
    'i love you': {'es': 'Te quiero', 'fr': 'Je t\'aime', 'de': 'Ich liebe dich',
                   'it': 'Ti amo', 'pt': 'Eu te amo', 'nl': 'Ik hou van je'},
    'see you later': {'es': 'Hasta luego', 'fr': 'À plus tard',
                      'de': 'Bis später', 'it': 'A dopo', 'pt': 'Até logo',
                      'nl': 'Tot later'},
    'good luck': {'es': 'Buena suerte', 'fr': 'Bonne chance', 'de': 'Viel Glück',
                  'it': 'Buona fortuna', 'pt': 'Boa sorte', 'nl': 'Veel succes'},
    'congratulations': {'es': 'Felicitaciones', 'fr': 'Félicitations',
                        'de': 'Herzlichen Glückwunsch', 'it': 'Congratulazioni',
                        'pt': 'Parabéns', 'nl': 'Gefeliciteerd'},
    "i don't understand": {'es': 'No entiendo', 'fr': "Je ne comprends pas",
                           'de': 'Ich verstehe nicht', 'it': 'Non capisco',
                           'pt': 'Não entendo', 'nl': 'Ik begrijp het niet'},
    'where is the bathroom': {'es': '¿Dónde está el baño?',
                              'fr': 'Où sont les toilettes ?',
                              'de': 'Wo ist die Toilette?',
                              'it': 'Dov\'è il bagno?',
                              'pt': 'Onde fica o banheiro?',
                              'nl': 'Waar is het toilet?'},
    "i'm sorry": {'es': 'Lo siento', 'fr': 'Je suis désolé',
                  'de': 'Es tut mir leid', 'it': 'Mi dispiace',
                  'pt': 'Me desculpe', 'nl': 'Het spijt me'},
    'excuse me': {'es': 'Disculpe', 'fr': 'Excusez-moi', 'de': 'Entschuldigung',
                  'it': 'Mi scusi', 'pt': 'Com licença', 'nl': 'Excuseer mij'},
}

# statement templates: "i like X" etc.
_TRANSLATION_TEMPLATES = {
    'i like': {'es': 'Me gusta {x}', 'fr': "J'aime {x}", 'de': 'Ich mag {x}',
               'it': 'Mi piace {x}', 'pt': 'Eu gosto de {x}', 'nl': 'Ik vind {x} leuk'},
    'i love': {'es': 'Me encanta {x}', 'fr': "J'adore {x}", 'de': 'Ich liebe {x}',
               'it': 'Adoro {x}', 'pt': 'Eu amo {x}', 'nl': 'Ik hou van {x}'},
    'i want': {'es': 'Quiero {x}', 'fr': 'Je veux {x}', 'de': 'Ich möchte {x}',
               'it': 'Voglio {x}', 'pt': 'Eu quero {x}', 'nl': 'Ik wil {x}'},
    'i have': {'es': 'Tengo {x}', 'fr': "J'ai {x}", 'de': 'Ich habe {x}',
               'it': 'Ho {x}', 'pt': 'Eu tenho {x}', 'nl': 'Ik heb {x}'},
    'i need': {'es': 'Necesito {x}', 'fr': "J'ai besoin de {x}",
               'de': 'Ich brauche {x}', 'it': 'Ho bisogno di {x}',
               'pt': 'Eu preciso de {x}', 'nl': 'Ik heb {x} nodig'},
}

_LANG_NAMES = {'spanish': 'es', 'espanol': 'es', 'español': 'es',
               'french': 'fr', 'francais': 'fr', 'français': 'fr',
               'german': 'de', 'deutsch': 'de', 'italian': 'it',
               'italiano': 'it', 'portuguese': 'pt', 'portugues': 'pt',
               'dutch': 'nl', 'nederlands': 'nl'}


def detect_translate_request(query):
    """Detect 'translate this to <lang>: <text>' — returns (lang, text)."""
    m = re.match(
        r'^(?:can\s+you\s+|please\s+)?translate\s+(?:this|the|that|it|'
        r'this\s+text|the\s+text|following|this\s+sentence)\s+'
        r'(?:text\s+)?(?:to|into|in)\s+([a-zà-ÿ]+)\s*[:\-]?\s*(.*)$',
        query, re.IGNORECASE)
    if not m:
        return None
    lang = _LANG_NAMES.get(m.group(1).lower())
    if not lang:
        return None
    return lang, m.group(2).strip()


def translate_text(text, lang):
    """Best-effort phrasebook translation. Returns (translated, notes)."""
    t = text.strip()
    if not t:
        return '', ["nothing to translate"]
    low = t.lower().strip('!.? ')

    # 1. exact phrasebook hit
    phrase = _TRANSLATION_PHRASES.get(low)
    if phrase and lang in phrase:
        return phrase[lang], ["translated from the phrasebook"]

    # 2. statement templates: "i like pizza." -> "Me gusta la pizza."
    for key, langs in _TRANSLATION_TEMPLATES.items():
        m = re.match(r'^' + re.escape(key) + r'\s+(.+?)\.?$', low)
        if m and lang in langs:
            obj = m.group(1).strip()
            # drop a leading article for languages that don't need it
            if lang == 'es' and re.match(r'^(?:el|la|los|las)\s+', obj):
                obj = re.sub(r'^(?:el|la|los|las)\s+', '', obj)
            return langs[lang].replace('{x}', obj) + '.', \
                ["translated using a statement template"]

    # 3. sentence-by-sentence: translate every sentence that the phrasebook
    #    covers, keep the rest untouched, and say which parts were skipped.
    #    Commas between short phrases count as separators too ("hello, how
    #    are you?"), but statement templates are tried before this so
    #    "i like pizza, please" doesn't split mid-template.
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+|,\s+', t)
                 if s.strip()]
    if len(sentences) > 1:
        out_parts = []
        covered = 0
        for s in sentences:
            s_low = s.lower().strip('!.? ')
            if _TRANSLATION_PHRASES.get(s_low, {}).get(lang):
                out_parts.append(_TRANSLATION_PHRASES[s_low][lang])
                covered += 1
            else:
                out_parts.append(s)
        if covered == len(sentences):
            return ' '.join(out_parts), ["translated sentence by sentence from "
                                         "the phrasebook"]
        if covered > 0:
            return (' '.join(out_parts),
                    [f"translated the {covered} sentence"
                     + ('s' if covered != 1 else '')
                     + " I knew, and left the rest as-is"])

    # 4. nothing covered: refuse rather than mangle
    return None, ["I only translate from a curated phrasebook (greetings, "
                  "thanks, simple 'I like X' statements). For free translation "
                  "of arbitrary text I'd need a real translator. I can instead "
                  "edit the text: make it more formal, shorter, more polite, "
                  "or fix its grammar."]


def to_bullets(text):
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
    return '\n'.join(f'- {s}' for s in sentences)


# ── Statement -> question conversion ──────────────────────────────────────────
# "She is ready." -> "Is she ready?", "They went home." -> "Did they go home?"
# Deterministic subject/auxiliary inversion with do-support. Only handles
# simple single-clause sentences; anything else is refused with a note.

# Common regular past-tense verbs whose base form is ambiguous to reconstruct
# (liked -> like, stopped -> stop, called -> call) — deterministic lookup
# before the general -ed heuristic.
_ED_BASE_FIXES = {
    'liked': 'like', 'moved': 'move', 'loved': 'love', 'used': 'use',
    'saved': 'save', 'closed': 'close', 'lived': 'live', 'hoped': 'hope',
    'danced': 'dance', 'called': 'call', 'placed': 'place', 'changed': 'change',
    'worked': 'work', 'wanted': 'want', 'needed': 'need', 'tried': 'try',
    'studied': 'study', 'played': 'play', 'stopped': 'stop', 'planned': 'plan',
    'started': 'start', 'helped': 'help', 'watched': 'watch', 'asked': 'ask',
    'walked': 'walk', 'talked': 'talk', 'waited': 'wait', 'looked': 'look',
    'wanted': 'want', 'played': 'play', 'cried': 'cry', 'carried': 'carry',
    'hurried': 'hurry', 'worried': 'worry', 'fitted': 'fit', 'jogged': 'jog',
}


_IRREG_PAST = {
    'went': 'go', 'ate': 'eat', 'saw': 'see', 'took': 'take', 'made': 'make',
    'got': 'get', 'came': 'come', 'had': 'have', 'did': 'do', 'was': 'be',
    'were': 'be', 'gave': 'give', 'found': 'find', 'knew': 'know',
    'thought': 'think', 'told': 'tell', 'said': 'say', 'felt': 'feel',
    'left': 'leave', 'ran': 'run', 'bought': 'buy', 'brought': 'bring',
    'wrote': 'write', 'read': 'read', 'spoke': 'speak', 'drove': 'drive',
    'wore': 'wear', 'sang': 'sing', 'swam': 'swim', 'began': 'begin',
    'broke': 'break', 'chose': 'choose', 'drew': 'draw', 'flew': 'fly',
    'grew': 'grow', 'heard': 'hear', 'held': 'hold', 'led': 'lead',
    'lost': 'lose', 'met': 'meet', 'paid': 'pay', 'put': 'put',
    'rode': 'ride', 'rose': 'rise', 'set': 'set', 'shook': 'shake',
    'slept': 'sleep', 'stood': 'stand', 'stole': 'steal', 'swore': 'swear',
    'threw': 'throw', 'understood': 'understand', 'won': 'win',
    'built': 'build', 'caught': 'catch', 'taught': 'teach', 'bought': 'buy',
    'sent': 'send', 'spent': 'spend', 'kept': 'keep', 'sold': 'sell',
    'told': 'tell', 'fell': 'fall', 'felt': 'feel', 'forgot': 'forget',
    'hid': 'hide', 'hit': 'hit', 'hurt': 'hurt', 'cut': 'cut',
}


def _base_form(word):
    """Best-effort reconstruction of the base form of a verb (past tense or
    3rd-person singular) for do-support questions."""
    w = word.lower()
    if w in _IRREG_PAST:
        return _IRREG_PAST[w]
    if w in _ED_BASE_FIXES:
        return _ED_BASE_FIXES[w]
    if w.endswith('ies') and len(w) > 3:
        return w[:-3] + 'y'          # studies -> study
    if (w.endswith(('ches', 'shes', 'xes', 'zes', 'oes')) or
            (len(w) > 3 and w[-3] in 'sxz' and w.endswith('es'))):
        return w[:-2]                # watches/goes/does/fixes -> watch/go/do/fix
    if w.endswith('s') and not w.endswith('ss') and len(w) > 2:
        return w[:-1]                # likes -> like, runs -> run
    if w.endswith('ied') and len(w) > 3:
        return w[:-3] + 'y'          # studied -> study
    if w.endswith('ed') and len(w) > 2:
        base = w[:-2]
        if len(base) >= 2 and base[-1] == base[-2]:
            return base[:-1]         # stopped -> stop
        return base                  # walked -> walk, played -> play
    return w


def make_question(content):
    """Convert a simple statement into a yes/no question.

    Returns the question string, or None if the sentence is too complex.
    """
    text = content.strip().rstrip('.!?')
    m = re.match(r'^([A-Za-z]+)\s+(.+)$', text)
    if not m:
        return None
    subj, rest = m.group(1), m.group(2)
    # only handle pronoun or capitalized-name subjects ("The quick brown
    # fox..." is too complex to invert safely)
    _NAME_STOP = {'the', 'a', 'an', 'this', 'that', 'these', 'those', 'my',
                  'our', 'your', 'his', 'her', 'their', 'its', 'some', 'many',
                  'most', 'every', 'each', 'all', 'few', 'no', 'one', 'two',
                  'three', 'there', 'here', 'it', 'they', 'we', 'you', 'what',
                  'when', 'where', 'why', 'how', 'i'}
    if subj.lower() not in ('i', 'you', 'he', 'she', 'it', 'we', 'they'):
        if subj.lower() in _NAME_STOP or not (subj[:1].isupper() and subj[1:].islower()):
            return None
    # "I" stays capitalized; other pronouns become lowercase mid-question
    if subj.lower() == 'i':
        _subj = 'I'
    elif subj.lower() in ('you', 'he', 'she', 'it', 'we', 'they'):
        _subj = subj.lower()
    else:
        _subj = subj
    m_vb = re.match(r'^(am|is|are|was|were|have|has|had|can|could|will|would|shall|should|may|might|must|do|does|did|cannot)\s+(.*)$', rest)
    if m_vb:
        vb, tail = m_vb.group(1), m_vb.group(2)
        if vb == 'cannot':
            return f'Can {_subj} not {tail}?'
        return f'{vb.capitalize()} {_subj} {tail}?'
    m2 = re.match(r'^([A-Za-z]+)(\s+.*)?$', rest)
    if not m2:
        return None
    verb, tail = m2.group(1), m2.group(2) or ''
    third = _subj.lower() in ('he', 'she', 'it') or (subj[:1].isupper() and subj[1:].islower())
    base = _base_form(verb)
    if verb.lower() in _IRREG_PAST or (verb.lower().endswith('ed') and len(verb) > 2):
        return f'Did {_subj} {base}{tail}?'
    if third and verb.lower().endswith('s'):
        return f'Does {_subj} {base}{tail}?'
    return f'Do {_subj} {base}{tail}?'


# ── Past-tense conversion ─────────────────────────────────────────────────────
# "She likes pizza." -> "She liked pizza.", "They go home." -> "They went
# home.", "He is running." -> "He was running." Word-level with auxiliary
# handling; already-past forms are left alone.

_IRREG_PRESENT_PAST = {
    'go': 'went', 'eat': 'ate', 'see': 'saw', 'take': 'took', 'make': 'made',
    'get': 'got', 'come': 'came', 'have': 'had', 'do': 'did', 'give': 'gave',
    'find': 'found', 'know': 'knew', 'think': 'thought', 'tell': 'told',
    'say': 'said', 'feel': 'felt', 'leave': 'left', 'run': 'ran',
    'buy': 'bought', 'bring': 'brought', 'write': 'wrote', 'read': 'read',
    'speak': 'spoke', 'drive': 'drove', 'wear': 'wore', 'sing': 'sang',
    'swim': 'swam', 'begin': 'began', 'break': 'broke', 'choose': 'chose',
    'draw': 'drew', 'fly': 'flew', 'grow': 'grew', 'hear': 'heard',
    'hold': 'held', 'lead': 'led', 'lose': 'lost', 'meet': 'met',
    'pay': 'paid', 'put': 'put', 'ride': 'rode', 'rise': 'rose', 'set': 'set',
    'shake': 'shook', 'sleep': 'slept', 'stand': 'stood', 'steal': 'stole',
    'swear': 'swore', 'throw': 'threw', 'understand': 'understood',
    'win': 'won', 'build': 'built', 'catch': 'caught', 'teach': 'taught',
    'send': 'sent', 'spend': 'spent', 'keep': 'kept', 'sell': 'sold',
    'fall': 'fell', 'forget': 'forgot', 'hide': 'hid', 'hit': 'hit',
    'hurt': 'hurt', 'cut': 'cut', 'sit': 'sat', 'drink': 'drank',
    'ring': 'rang', 'wake': 'woke', 'bite': 'bit', 'freeze': 'froze',
    'lend': 'lent', 'light': 'lit', 'shoot': 'shot', 'shut': 'shut',
    'sink': 'sank', 'slide': 'slid', 'stick': 'stuck', 'swing': 'swung',
    'tear': 'tore', 'weep': 'wept', 'wind': 'wound', 'lay': 'laid',
    'lie': 'lay', 'seek': 'sought', 'fight': 'fought', 'hang': 'hung',
    'bend': 'bent', 'become': 'became', 'feed': 'fed', 'bleed': 'bled',
    'breed': 'bred', 'deal': 'dealt', 'dig': 'dug', 'dive': 'dived',
    'dream': 'dreamed', 'leap': 'leapt', 'learn': 'learned', 'mean': 'meant',
}

_PAST_AUX = {
    'is': 'was', 'am': 'was', 'are': 'were', 'was': 'was', 'were': 'were',
    'has': 'had', 'have': 'had', 'had': 'had',
    'do': 'did', 'does': 'did', 'did': 'did',
    'will': 'would', 'would': 'would', 'can': 'could', 'could': 'could',
    'shall': 'should', 'should': 'should', 'may': 'might', 'might': 'might',
    'must': 'must',
    "isn't": "wasn't", "aren't": "weren't", "hasn't": "hadn't",
    "haven't": "hadn't", "hadn't": "hadn't", "don't": "didn't",
    "doesn't": "didn't", "didn't": "didn't", "can't": "couldn't",
    "couldn't": "couldn't", "won't": "wouldn't", "wouldn't": "wouldn't",
    "shouldn't": "shouldn't", "mustn't": "mustn't", "cannot": "could not",
    # no-apostrophe typo forms
    'doesnt': "didn't", 'dont': "didn't", 'isnt': "wasn't", 'arent': "weren't",
    'hasnt': "hadn't", 'havent': "hadn't", 'cant': "couldn't", 'wont': "wouldn't",
}

# Words after which a following verb must stay in its base form
_AUX_BASE_KEEP = {
    'do', 'does', 'did', "don't", "doesn't", "didn't", 'can', 'could',
    'will', 'would', 'shall', 'should', 'may', 'might', 'must', 'to', 'not',
}

# Irregular past participles (follow a form of have/has/had or be) — already
# "past", never past-ified: "She has gone." -> "She had gone."
_PAST_PARTICIPLES = {
    'gone', 'been', 'seen', 'eaten', 'taken', 'written', 'spoken', 'driven',
    'worn', 'sung', 'swum', 'begun', 'broken', 'chosen', 'drawn', 'flown',
    'grown', 'ridden', 'risen', 'shaken', 'stolen', 'sworn', 'thrown',
    'understood', 'forgotten', 'hidden', 'fallen', 'built', 'caught',
    'taught', 'sent', 'spent', 'kept', 'sold', 'slept', 'stood', 'held',
    'heard', 'left', 'lost', 'met', 'paid', 'put', 'set', 'sat', 'hit',
    'hurt', 'cut', 'found', 'told', 'said', 'felt', 'given', 'made', 'done',
    'come', 'known', 'thought', 'bought', 'brought', 'read', 'heard',
    'won', 'bent', 'dug', 'fed', 'bled', 'dealt', 'meant', 'lit', 'shot',
    'shut', 'sank', 'sunk', 'slid', 'stuck', 'swung', 'torn', 'wept',
    'wound', 'laid', 'lain', 'sought', 'fought', 'hung', 'become', 'began',
}


# Present-tense verbs that happen to end in "ed" — everything else ending in
# "ed" is treated as already past.
_PRESENT_ED_VERBS = {
    'need', 'feed', 'breed', 'heed', 'seed', 'weed', 'speed', 'proceed',
    'succeed', 'exceed', 'lead', 'read', 'knead', 'plead', 'tread', 'wheedle',
}


def _present_base(w):
    """Strip 3rd-person -s/-es/-ies to get the plain present base form."""
    if w in _IRREG_PRESENT_PAST:
        return w
    if w.endswith('ies') and len(w) > 3:
        return w[:-3] + 'y'
    if w.endswith(('ches', 'shes', 'xes', 'zes', 'oes')):
        return w[:-2]
    if w.endswith('s') and not w.endswith('ss') and len(w) > 2:
        return w[:-1]
    return w


def _past_form(word):
    """Best-effort base/present verb -> simple past form."""
    w = word.lower()
    if w in _IRREG_PRESENT_PAST:
        return _IRREG_PRESENT_PAST[w]
    if w.endswith('e'):
        return w + 'd'                    # like -> liked
    if w.endswith('y') and len(w) > 2 and w[-2] not in 'aeiou':
        return w[:-1] + 'ied'             # study -> studied
    base = w
    # short CVC words double the final consonant (stop -> stopped, plan ->
    # planned), but not words like fix/play/open/happen
    if (3 <= len(base) <= 4 and base[-1] not in 'aeiouwxy'
            and base[-2] in 'aeiou' and len(base) >= 3 and base[-3] not in 'aeiou'
            and not base.endswith(('en', 'er', 'el', 'ow', 'ed', 'ss'))):
        base = base + base[-1]
    return base + 'ed'


def _tokenize_words(text):
    """Split into (word, trailing_punct) preserving case info."""
    out = []
    for w in text.split():
        m = re.match(r'^([A-Za-z\']+)([^A-Za-z\']*)$', w)
        if m:
            out.append((m.group(1), m.group(2)))
        else:
            out.append((w, ''))
    return out


_NAME_STOP = {'the', 'a', 'an', 'this', 'that', 'these', 'those', 'my',
              'our', 'your', 'his', 'her', 'their', 'its', 'some', 'many',
              'most', 'every', 'each', 'all', 'few', 'no', 'one', 'two',
              'three', 'there', 'here', 'it', 'they', 'we', 'you', 'what',
              'when', 'where', 'why', 'how', 'i'}

_PRONOUNS = {'i', 'you', 'he', 'she', 'it', 'we', 'they'}


def _is_name_subj(word):
    return word[:1].isupper() and word[1:].islower() and word.lower() not in _NAME_STOP


def _preserve_case(word, new):
    if word[:1].isupper() and new[:1].islower():
        return new[0].upper() + new[1:]
    if word.islower() and new[:1].isupper():
        return new[0].lower() + new[1:]
    return new


def _past_clause(clause):
    """Past-tense a single clause (auxiliaries anywhere; main verb only after
    a pronoun/name subject, so complex subjects stay mostly unchanged)."""
    words = _tokenize_words(clause)
    # pass 1: auxiliaries anywhere (unambiguous)
    for i, (w, p) in enumerate(words):
        lw = w.lower()
        if lw in _PAST_AUX:
            words[i] = (_preserve_case(w, _PAST_AUX[lw]), p)
    # pass 2: main verb after a pronoun/name subject
    if words:
        first = words[0][0].lower()
        simple_subj = first in _PRONOUNS or _is_name_subj(words[0][0])
        if simple_subj and len(words) >= 2:
            for vi in range(1, len(words)):
                vw, vp = words[vi]
                lv = vw.lower()
                prev = words[vi - 1][0].lower()
                if lv.endswith('ing') or lv in _PAST_AUX:
                    break
                if prev in _AUX_BASE_KEEP or lv in _AUX_BASE_KEEP:
                    break
                if lv in _PAST_PARTICIPLES or lv in _IRREG_PRESENT_PAST.values():
                    break
                if lv.endswith('ed') and lv not in _PRESENT_ED_VERBS:
                    break  # already past ("played", "walked")
                past = _past_form(_present_base(lv))
                if past != lv:
                    words[vi] = (_preserve_case(vw, past), vp)
                break
    return ' '.join(w + p for w, p in words)


def make_past(content):
    """Rewrite text into the simple past tense (best effort).

    Splits on sentence punctuation and "and" clauses; auxiliaries are always
    converted, main verbs only in simple pronoun/name-subject clauses, so
    complex subjects ("The play was good.") are left mostly alone.
    """
    sentences = re.split(r'(?<=[.!?])\s+', content)
    out_sents = []
    for sent in sentences:
        clauses = re.split(r'\s+and\s+', sent)
        out_sents.append(' and '.join(_past_clause(c) for c in clauses))
    return ' '.join(out_sents)


# ── Negation ──────────────────────────────────────────────────────────────────
# "She likes pizza." -> "She doesn't like pizza.", "They went home." ->
# "They didn't go home.", "She is ready." -> "She is not ready."

def make_negative(content):
    """Negate a simple statement (best effort)."""
    text = content.strip().rstrip('.!?')
    m = re.match(r'^([A-Za-z]+)\s+(.+)$', text)
    if not m:
        return None
    subj, rest = m.group(1), m.group(2)
    # only negate pronoun or capitalized-name subjects; "The report is
    # ready." is left alone rather than mangled
    if subj.lower() not in _PRONOUNS:
        if subj.lower() in _NAME_STOP or not _is_name_subj(subj):
            return None
    m_vb = re.match(r'^(am|is|are|was|were|have|has|had|can|could|will|would|shall|should|may|might|must|do|does|did)\s+(.*)$', rest)
    if m_vb:
        vb, tail = m_vb.group(1), m_vb.group(2)
        not_form = 'not'
        if vb == 'can':
            return f'{subj} cannot {tail}'.strip()
        if vb == 'could':
            return f'{subj} could not {tail}'.strip()
        return f'{subj} {vb} {not_form} {tail}'.strip()
    m2 = re.match(r'^([A-Za-z]+)(\s+.*)?$', rest)
    if not m2:
        return None
    verb, tail = m2.group(1), m2.group(2) or ''
    third = subj.lower() in ('he', 'she', 'it') or _is_name_subj(subj)
    base = _base_form(verb)
    if verb.lower() in _IRREG_PAST or (verb.lower().endswith('ed') and len(verb) > 2):
        return f'{subj} didn\'t {base}{tail}'.strip()
    if third:
        return f'{subj} doesn\'t {base}{tail}'.strip()
    return f'{subj} don\'t {base}{tail}'.strip()


# ── Present-tense conversion ─────────────────────────────────────────────────
# "She walked home." -> "She walks home.", "They went home." -> "They go
# home.", "He was running." -> "He is running." (3rd-person -s agreement).

def _present_aux(word, subj_lower, third):
    """Past auxiliary -> present form given the subject's person."""
    lw = word.lower()
    if lw == 'was':
        return 'am' if subj_lower == 'i' else ('is' if third else 'are')
    if lw == 'were':
        return 'are'
    if lw == 'had':
        return 'has' if third else 'have'
    if lw == 'did':
        return 'does' if third else 'do'
    if lw == 'would':
        return 'will'
    if lw == 'could':
        return 'can'
    if lw == 'should':
        return 'shall'
    if lw == 'might':
        return 'may'
    if lw == "wasn't":
        return "isn't" if third else "aren't"
    if lw == 'wasnt':
        return "isn't" if third else "aren't"
    if lw == "weren't":
        return "aren't"
    if lw == 'werent':
        return "aren't"
    if lw == "hadn't":
        return "hasn't" if third else "haven't"
    if lw == 'hadnt':
        return "hasn't" if third else "haven't"
    if lw == "didn't":
        return "doesn't" if third else "don't"
    if lw == 'didnt':
        return "doesn't" if third else "don't"
    if lw == "couldn't":
        return "can't"
    if lw == 'couldnt':
        return "can't"
    if lw == "wouldn't":
        return "won't"
    if lw == 'wouldnt':
        return "won't"
    return None


_PAST_AUX_KEYS = {'was', 'were', 'had', 'did', 'would', 'could', 'should',
                  'might', "wasn't", "weren't", "hadn't", "didn't",
                  "couldn't", "wouldn't", 'didnt', 'couldnt', 'wouldnt',
                  'wasnt', 'werent', 'hadnt'}


def _add_s(base):
    """3rd-person singular present ending."""
    if base.endswith(('s', 'x', 'z', 'ch', 'sh', 'o')):
        return base + 'es'
    if base.endswith('y') and len(base) > 1 and base[-2] not in 'aeiou':
        return base[:-1] + 'ies'
    return base + 's'


def _present_clause(clause):
    words = _tokenize_words(clause)
    if not words:
        return clause
    subj_lower = words[0][0].lower()
    if subj_lower in ('he', 'she', 'it'):
        third = True
    elif subj_lower in _PRONOUNS:
        third = False
    elif _is_name_subj(words[0][0]):
        third = True
    else:
        # "the report was..." -> is; "the reports were..." -> are
        third = not subj_lower.endswith('s')
    # pass 1: past auxiliaries -> present
    for i, (w, p) in enumerate(words):
        lw = w.lower()
        if lw in _PAST_AUX_KEYS:
            new = _present_aux(lw, subj_lower, third)
            if new:
                words[i] = (_preserve_case(w, new), p)
    # pass 2: past main verb -> present (with -s agreement)
    first = words[0][0].lower()
    simple_subj = first in _PRONOUNS or _is_name_subj(words[0][0])
    if simple_subj and len(words) >= 2:
        for vi in range(1, len(words)):
            vw, vp = words[vi]
            lv = vw.lower()
            prev = words[vi - 1][0].lower()
            if lv.endswith('ing'):
                break
            if lv in _PAST_AUX or prev in _AUX_BASE_KEEP:
                break
            if not (lv in _IRREG_PAST or lv in _ED_BASE_FIXES
                    or (lv.endswith('ed') and lv not in _PRESENT_ED_VERBS)):
                break  # already present tense
            base = _base_form(lv)
            new = _add_s(base) if third else base
            if new != lv:
                words[vi] = (_preserve_case(vw, new), vp)
            break
    return ' '.join(w + p for w, p in words)


def make_present(content):
    """Rewrite text into the simple present tense (best effort)."""
    sentences = re.split(r'(?<=[.!?])\s+', content)
    out_sents = []
    for sent in sentences:
        clauses = re.split(r'\s+and\s+', sent)
        out_sents.append(' and '.join(_present_clause(c) for c in clauses))
    return ' '.join(out_sents)


def edit_content(kind: str, content: str, query: str = '') -> Tuple[str, List[str]]:
    """Dispatch an edit by kind. Returns (edited, changes)."""
    if kind == 'code':
        return edit_code(content, query)
    if kind == 'json':
        return edit_json(content)
    if kind == 'json_check':
        return check_json(content)
    return edit_text(content)


def check_json(content: str) -> Tuple[str, List[str]]:
    """Report whether the content is valid JSON (no rewriting)."""
    import json as _json
    try:
        _json.loads(content)
        return "Valid JSON!" + (" It was reformatted below." if False else ""), ["JSON parsed successfully"]
    except _json.JSONDecodeError as e:
        return f"Invalid JSON: {e}", ["JSON parse error"]


# ── JSON repair ──────────────────────────────────────────────────────────────

_JSON_REPAIR_STEPS = [
    # 1. Trailing commas: {"a": 1,} -> {"a": 1}
    (r',\s*([}\]])', r'\1'),
    # 2. Single quotes -> double quotes (single-quoted JSON)
    (r"'", '"'),
    # 3. Missing commas: {"a":1 "b":2} -> {"a":1, "b":2}
    (r'([}\]\"])\s+(\"[^\"]+\"\s*:)', r'\1, \2'),
    (r'(\d)\s+(\"[^\"]+\"\s*:)', r'\1, \2'),
    # 4. Unquoted keys: {name: "x"} -> {"name": "x"}
    (r'\{([A-Za-z_][\w]*)\s*:', r'{"\1":'),
    (r',\s*([A-Za-z_][\w]*)\s*:', r', "\1":'),
    # 5. Empty-value commas: {"a": , "b": 2} -> drop the empty slot
    (r':\s*,\s*', ': '),
]


def edit_json(content: str) -> Tuple[str, List[str]]:
    """Validate JSON; if invalid, apply deterministic repairs and report what
    changed. Returns (json_text, status_lines)."""
    import json as _json
    original = content.strip()
    if not original:
        return original, ["no content to check"]

    def _load(s):
        try:
            return _json.loads(s), None
        except _json.JSONDecodeError as e:
            return None, str(e)

    # Try as-is first
    parsed, err = _load(original)
    if parsed is not None:
        return _json.dumps(parsed, indent=2, ensure_ascii=False), ["valid JSON — reformatted with 2-space indentation"]

    # Apply repairs step by step, retrying after each
    fixed = original
    applied = []
    for pat, repl in _JSON_REPAIR_STEPS:
        attempt = re.sub(pat, repl, fixed)
        if attempt != fixed:
            fixed = attempt
            parsed, err = _load(fixed)
            if parsed is not None:
                applied.append(f"repaired and re-parsed after: {pat[:28]}...")
                return _json.dumps(parsed, indent=2, ensure_ascii=False), applied
    # Nothing parsed; report the best effort + the original error
    parsed, err = _load(fixed)
    if parsed is not None:
        return _json.dumps(parsed, indent=2, ensure_ascii=False), applied or ["repaired"]
    return fixed, [f"could not repair automatically — JSON error: {err}"]


# ── Text metrics ─────────────────────────────────────────────────────────────
# "how many words in this text: ...", "count the sentences: ..." — pure
# counting, no editing.

_METRIC_UNITS = {'word', 'words', 'sentence', 'sentences', 'character',
                 'characters', 'letter', 'letters', 'line', 'lines',
                 'paragraph', 'paragraphs'}


def detect_metrics_request(query):
    """Detect a text-metrics question. Returns (unit, content) or None.

    unit is one of: words, sentences, characters, letters, lines, paragraphs,
    length. Content is the text to measure.
    """
    q = query.strip()
    if not q:
        return None
    m = re.match(
        r'^(?:how\s+many\s+(words?|sentences?|characters?|letters?|lines?|paragraphs?)'
        r'|count\s+(?:the\s+)?(?:number\s+of\s+)?(words?|sentences?|characters?|letters?|lines?|paragraphs?)'
        r'|how\s+long\s+is\s+(?:this|that)(?:\s+(?:text|paragraph|essay|article|document|email|e-mail|message|letter|story|report|post|comment|poem|review|note|writing))?)'
        r'\b',
        q, re.IGNORECASE)
    if not m:
        return None
    unit = (m.group(1) or m.group(2) or 'length').lower()
    if unit not in ('length',):
        unit = unit.rstrip('s')
        if unit not in _METRIC_UNITS:
            return None
        unit += 's'
    rest = q[m.end():].lstrip()
    rest = re.sub(r'^(?:of|in|for|on)\s+', '', rest, flags=re.IGNORECASE)      # "in this text:"
    rest = re.sub(r'^(?:this|that|the)\s+[\w-]+', '', rest, flags=re.IGNORECASE)  # "this text:"
    rest = re.sub(r'^(?:this|that|the)\s*', '', rest, flags=re.IGNORECASE)         # bare "this"
    rest = re.sub(r'^[:]?\s*', '', rest)
    rest = re.sub(r'^[\w-]+:\s*', '', rest)  # leftover "text: hello" from "this text:"
    content = rest.strip().strip('"\'“”‘’')
    if not content or len(content) < 2:
        return None
    # no colon and a question-fragment remainder means the query had no text
    # ("how many words are there") — not a metrics request with content
    if ':' not in q and re.match(
            r'^(?:are\s+there|is\s+there|is\s+this|is\s+that|is\s+it|do\s+you|does\s+this|did\s+you|can\s+you|in\s+this|in\s+the|of\s+this|of\s+the)\b',
            content, re.IGNORECASE):
        return None
    if ':' not in q and len(content.split()) < 2:
        return None
    # A noun phrase naming a code construct ("count the number of characters
    # in a string") is a coding how-to, not a request to measure the literal
    # words "a string". Without real text to measure, this isn't a metrics
    # request — the engine should route it to the code handler.
    if ':' not in q and re.match(
            r'^(?:a|an|the|any|every|this|that|some|each)\s+(?:string|list|'
            r'array|dict|dictionary|tuple|set|file|word|words|sentence|'
            r'sentences|character|characters|letter|letters|line|lines|'
            r'paragraph|paragraphs|number|numbers|text|string|phrase|passage)'
            r'\b', content, re.IGNORECASE):
        return None
    return (unit, content)


def text_metrics(unit, content):
    """Return a formatted metrics answer for the given content."""
    words = re.findall(r'\S+', content)
    n_words = len(words)
    n_chars = len(content)
    n_letters = len(re.findall(r'[A-Za-z]', content))
    n_sentences = len([s for s in re.split(r'[.!?]+', content) if s.strip()])
    n_lines = len(content.splitlines())
    n_paras = len([p for p in content.split('\n\n') if p.strip()])
    reading_secs = max(1, round(n_words / 200 * 60))
    if reading_secs < 60:
        reading = f"about {reading_secs} second{'s' if reading_secs != 1 else ''} of reading"
    else:
        reading = f"about {reading_secs // 60} minute{'s' if reading_secs >= 120 else ''} of reading"
    counts = {
        'words': n_words, 'sentences': n_sentences, 'characters': n_chars,
        'letters': n_letters, 'lines': n_lines, 'paragraphs': n_paras,
    }
    if unit == 'length':
        return (f"That text has {n_words} words ({n_chars} characters, "
                f"{n_sentences} sentence{'s' if n_sentences != 1 else ''}) — "
                f"{reading} at 200 words per minute.")
    n = counts.get(unit, n_words)
    label = unit if n != 1 else unit.rstrip('s')
    return f"That text has {n} {label}."
