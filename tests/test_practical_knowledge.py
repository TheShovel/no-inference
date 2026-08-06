#!/usr/bin/env python3
"""Regression battery for the practical-knowledge KB entries.

Each case is (query, [required_substrings], [forbidden_substrings]).
The response must contain every required substring and none of the forbidden
ones. This protects the curated how-to / everyday entries added during the
knowledge-expansion pass from being broken by future routing changes.

Run with:  python3 tests/test_practical_knowledge.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from cos.engine import process_query, reset_conversation

FALLBACK_PHRASES = [
    "i do not have enough specific information",
    "i could not find enough",
    "i couldn't find solid information",
    "i don't have a ready-made answer",
    "not sure about that",
]

# (query, [required], [forbidden])
CASES = [
    # ── practical how-tos ────────────────────────────────────────────────
    ("how to boil an egg perfectly", ["boil", "ice bath"], []),
    ("how to sharpen a knife", ["whetstone", "angle"], []),
    ("how to store fresh herbs", ["water", "fridge"], []),
    ("how to get rid of fruit flies", ["vinegar", "trap"], []),
    ("how to remove gum from hair", ["ice", "oil"], []),
    ("how to get smell out of shoes", ["baking soda", "dry"], []),
    ("how to revive a dying plant", ["overwatering", "drainage"], []),
    ("how to jump start a car", ["red", "black", "positive"], []),
    ("how to check your oil level", ["dipstick", "wipe"], []),
    ("how to change a flat tire", ["lug nuts", "jack"], []),
    ("how to check tire pressure", ["valve", "psi"], []),
    # ── computer / OS tasks ──────────────────────────────────────────────
    ("how to recover an unsaved word document", ["autorecover", "unsaved"], []),
    ("how to find my ip address", ["ipconfig", "192.168"], []),
    ("how to transfer files from pc to phone", ["localsend", "usb"], []),
    ("how to speed up a slow computer", ["restart", "ssd"], []),
    ("how to create a bootable usb drive", ["rufus", "iso"], []),
    ("how to check if my pc can run a game", ["gpu", "requirements"], []),
    ("how to record the screen on mac", ["shift-command-5"], []),
    ("how to split screen on windows", ["win + left", "snap"], []),
    ("how to password protect a folder", ["7-zip", "encrypt"], []),
    ("how to format a usb drive", ["fat32", "exfat"], []),
    ("how to uninstall a program on windows", ["settings", "uninstall"], []),
    ("how to take a screenshot on windows", ["win + shift + s", "snipping"], []),
    ("how to clear the cache in chrome", ["cached images", "clear"], []),
    ("how to check my pc specs", ["task manager", "dxdiag"], []),
    ("how to connect to wifi on windows", ["wi-fi", "password"], []),
    ("how to check if my pc has a virus", ["defender", "full scan"], []),
    # ── health / fitness ─────────────────────────────────────────────────
    ("how to get rid of a headache", ["water", "quiet"], []),
    ("how to treat a burn", ["cool", "running water"], []),
    ("how to stop snoring", ["side", "alcohol"], []),
    ("how to improve my posture", ["wall test", "chin"], []),
    ("how to lose belly fat", ["calorie deficit", "spot reduction"], ["six-pack"]),
    ("what is a calorie deficit", ["tdee", "500"], []),
    ("how many reps should i do", ["6-12", "strength"], []),
    # ── travel / life ────────────────────────────────────────────────────
    ("how to pack a suitcase efficiently", ["roll", "packing cubes"], []),
    ("what to do when your flight is delayed", ["rebook", "compensation"], []),
    ("how to get a passport", ["ds-11", "photo"], []),
    ("how to get a visa", ["embassy", "apply"], []),
    ("how to tip in the us", ["15-20%", "20%"], []),
    ("how does jet lag work", ["circadian", "melatonin"], []),
    ("how to remember things better", ["memory palace", "spaced"], []),
    ("how to take notes", ["cornell", "summary"], []),
    # ── money / career ───────────────────────────────────────────────────
    ("how to get out of debt", ["snowball", "avalanche"], []),
    ("how to cut your monthly expenses", ["subscriptions", "insurance"], []),
    ("how does a 401k match work", ["50%", "match", "free money"], []),
    ("what is a high yield savings account", ["apy", "fdic"], []),
    ("what is a fico score", ["payment history", "35%"], []),
    ("how to read a paystub", ["ytd", "gross pay", "net pay"], []),
    ("how to negotiate a job offer", ["market rate", "in writing"], []),
    ("how to quit a job gracefully", ["2 weeks", "in person"], []),
    ("how to ask for a raise", ["market rate", "business case"], []),
    ("how to write a thank you email after an interview", ["24 hours", "specific"], []),
    ("how to set smart goals", ["specific", "measurable", "time-bound"], []),
    ("how to prioritize tasks", ["eisenhower", "2-minute"], []),
    ("how to work from home effectively", ["dedicated", "rituals"], []),
    # ── parenting / pets ─────────────────────────────────────────────────
    ("how to potty train a puppy", ["schedule", "crate"], []),
    ("how to stop a dog from barking", ["counter-conditioning", "exercise"], []),
    ("how to stop a cat from scratching furniture", ["scratching post", "tape"], []),
    ("how to talk to your teenager", ["listen", "drive-time"], []),
    ("how to handle a childs temper tantrum in public", ["calm", "name the feeling"], []),
    # ── security / dev concepts ──────────────────────────────────────────
    ("how to spot a phishing email", ["urgency", "hover", "domain"], []),
    ("how to protect yourself from identity theft", ["freeze your credit", "2fa"], []),
    ("how to check if a website is safe", ["https", "lookalike"], []),
    ("how to report identity theft", ["identitytheft.gov", "fraud alert"], []),
    ("what is a vpn and should i use one", ["encrypt", "public wi-fi"], []),
    ("what is acid in databases", ["atomicity", "durability"], []),
    ("what is xss", ["injects", "escape"], []),
    ("what is a denial of service attack", ["botnet", "flood"], []),
    ("what is oauth", ["token", "scopes", "password"], []),
    ("what is a pull request", ["review", "merge"], []),
    ("what is a message queue", ["producer", "consumer"], []),
    ("what is sharding", ["shard key", "horizontal"], []),
    ("what is a cdn", ["edge", "cache"], []),
    ("what is load balancing", ["round robin", "health-checks"], []),
    ("what is a web socket", ["full-duplex", "push"], []),
    ("what is a distributed system", ["partial failure", "cap theorem"], []),
    ("what is a state machine", ["states", "transitions"], []),
    ("what is technical debt", ["interest", "shortcut"], []),
    ("what is the difference between refactoring and rewriting", ["behavior", "tests"], []),
    ("how to use a debugger", ["breakpoint", "step into"], []),
    ("how to estimate software projects", ["three-point", "range"], []),
    # ── survival / household ─────────────────────────────────────────────
    ("how to survive in the wilderness", ["shelter", "signal"], []),
    ("how to start a fire without matches", ["ferro rod", "bow drill"], []),
    ("how to find clean water in the wild", ["boil", "filter"], []),
    ("how to treat hypothermia", ["core", "dry clothes"], []),
    ("how to treat a snake bite", ["antivenom", "hospital"], []),
    ("how to get rid of bed bugs", ["heat", "encase"], []),
    ("how to whiten yellowed white clothes", ["oxygen bleach", "sun"], []),
    ("how to iron a shirt", ["collar", "slightly damp"], []),
    ("how to clean a microwave", ["steam", "vinegar"], []),
    ("how to remove burnt food from a pan", ["baking soda", "boil"], []),
    ("how to get rid of kitchen smells", ["vinegar", "ventilate"], []),
    ("how to remove a red wine stain", ["blot", "salt"], []),
    # ── comparisons ──────────────────────────────────────────────────────
    ("what is the difference between a resume and a cv", ["academic", "pages"], []),
    ("what is the difference between a boss and a leader", ["authority", "influence"], []),
    ("what is the difference between listening and hearing", ["automatic", "deliberate"], []),
    ("what is the difference between a habit and a routine", ["automatic", "cue"], []),
    ("what is the difference between confidence and arrogance", ["admit", "wrong"], []),
    ("what is the difference between a job and a career", ["long arc", "progression"], []),
    # ── code-transform smoke tests (must still work) ─────────────────────
    ("add error handling to this code: def divide(a, b):\n    return a / b",
     ["try:", "except"], []),
    ("convert this code from python to javascript: def double(x):\n    return x * 2",
     ["function double"], ["def double"]),
    # ── round 4: homeownership / cooking / medicine / relationships ───────
    ("what is a homeowners association", ["cc&rs", "dues"], []),
    ("how to make the perfect steak", ["rest", "thermometer"], []),
    ("how to make pasta from scratch", ["flour", "eggs", "knead"], []),
    ("how to make bread", ["yeast", "dutch oven"], []),
    ("how to cook rice without a rice cooker", ["rinse", "simmer", "fluff"], []),
    ("how to tell if eggs are still good", ["float", "water test"], []),
    ("how to freeze food properly", ["freezer burn", "air"], []),
    ("how to meal prep for the week", ["batch", "containers"], []),
    ("how to reduce salt in cooking", ["acid", "umami"], []),
    ("how do antibiotics work", ["bacteria", "cell wall"], []),
    ("how does anesthesia work", ["general", "gaba"], []),
    ("how to have a difficult conversation", ["facts", "listen"], []),
    ("how to apologize to your partner", ["specific", "impact"], []),
    ("how to set boundaries with family", ["from 'i'", "consequence"], []),
    ("how to know if a relationship is healthy", ["conflict", "independence"], []),
    ("how to forgive someone", ["not excusing", "releasing"], []),
    # ── round 5: analytics / cars / social ────────────────────────────────
    ("what is a funnel", ["awareness", "conversion"], []),
    ("what is a cohort", ["group", "retention"], []),
    ("what is the difference between correlation and causation",
     ["third variable", "randomized"], []),
    ("what is a p value", ["0.05", "surprise"] , []),
    ("what is a null hypothesis", ["no effect", "reject"], []),
    ("what is statistical significance", ["chance", "p-value"], []),
    ("how to buy a used car", ["carfax", "inspection"], []),
    ("how to negotiate the price of a car", ["out-the-door", "walk away"], []),
    ("how to wrap a gift", ["tape", "ribbon"], []),
    ("how to host a dinner party", ["make ahead", "table"], []),
    ("how to set a table", ["knife", "blade facing"], []),
    ("how to plan a party", ["invite", "playlist"], []),
    ("how to make small talk", ["ford", "follow-up"], []),
    ("how to remember names", ["repeat", "association"], []),
    ("how to compliment someone genuinely", ["specific", "effort"], []),
    # ── round 6: retirement / estate / education / science ────────────────
    ("how much do i need for retirement", ["25x", "4%"], []),
    ("what is the 4 percent rule", ["trinity study", "withdrawal"], []),
    ("what is social security", ["35 highest-earning", "full retirement age"], []),
    ("what is a trust", ["revocable", "probate"], []),
    ("what is power of attorney", ["durable", "financial"], []),
    ("what is probate", ["executor", "debts"], []),
    ("how to help my child with homework", ["questions", "independence"], []),
    ("how to talk to kids about money", ["save", "spend", "give"], []),
    ("how to teach a child to read", ["phonics", "decodable"], []),
    ("how does a rocket work", ["newton's third law", "oxidizer"], []),
    # ── round 7: analytics / cooking / relationships (already covered) ─────
    ("how to make a good cup of coffee", ["coffee", "brew"], []),
    ("how to deal with a breakup", ["grief", "no contact"], []),
    ("how to choose running shoes", ["thumb's width", "comfortable"], []),
    ("how to buy a house", ["pre-approved", "inspection"], []),
    # ── round 7: wellbeing / handy repairs / nature ────────────────────────
    ("how to improve self esteem", ["competence", "self-compassion"], []),
    ("how to deal with anger", ["20 minutes", "breathe"], []),
    ("how to be more optimistic", ["explanatory style", "gratitude"], []),
    ("how to cope with grief", ["waves", "continuing bonds"], []),
    ("how to unclog a toilet", ["plunger", "auger"], []),
    ("how to fix a squeaky door", ["hinge", "lubricant"], []),
    ("how to patch a hole in the wall", ["spackle", "joint compound"], []),
    ("how to hang shelves on drywall", ["studs", "toggle"], []),
    ("how to caulk a bathtub", ["silicone", "remove the old caulk"], []),
    ("how to fix a garbage disposal", ["reset", "hex wrench"], []),
    ("how do fish breathe underwater", ["gills", "countercurrent"], []),
    # ── round 8: dev concepts / stains / first aid / sleep ─────────────────
    ("what is terraform", ["infrastructure-as-code", "plan/apply"], []),
    ("what is a microfrontend", ["independent", "module federation"], []),
    ("what is mvc", ["model", "controller", "view"], []),
    ("what is a sdk", ["libraries", "wrapper"], []),
    ("what is an ide", ["debugger", "integrated"], []),
    ("how to get a stain out of a carpet", ["blot", "vinegar"], []),
    ("how to remove nail polish from clothes", ["acetone", "blot"], []),
    ("how to get paint out of clothes", ["latex", "alcohol"], []),
    ("how to remove a sticker from glass", ["hairdryer", "oil"], []),
    ("how to heal a canker sore", ["salt water", "benzocaine"], []),
    ("how to stop a nosebleed", ["lean forward", "pinch"], []),
    ("how to remove a splinter", ["tweezers", "sterilize"], []),
    ("how to get rid of a cold fast", ["honey", "saline"], ["antibiotics cure"]),
    ("how to soothe a sore throat", ["salt water", "honey"], []),
    ("how to reduce a fever", ["100.4", "acetaminophen"], []),
    ("how to stop coughing at night", ["honey", "elevate"], []),
    ("how to unclog a stuffy nose", ["saline", "steam"], []),
    ("how to get rid of heartburn fast", ["antacids", "wedge"], []),
    ("how to get rid of a wart", ["salicylic acid", "file"], []),
    ("how to treat sunburn", ["aloe", "cool"], []),
    ("how to treat a bee sting", ["credit card", "cold"], []),
    ("how to remove a tick safely", ["tweezers", "straight upward"], []),
    ("how to stop mosquito bites from itching", ["histamine", "antihistamine"], []),
    # ── round 9: coding concepts / sql / agile ─────────────────────────────
    ("what is a palindrome", ["racecar", "two-pointer"], []),
    ("what is a 404", ["client error", "not found"], []),
    ("what is a join", ["inner join", "left join"], []),
    ("what is a group by", ["aggregate", "having"], []),
    ("what is a stored procedure", ["call", "vendor-specific"], []),
    ("what is normalization", ["1nf", "3nf", "foreign keys"], []),
    ("what is a sprint", ["timebox", "retrospective"], []),
    ("what is agile", ["manifesto", "increments"], []),
    ("what is a kpi", ["strategic goal", "goodhart"], []),
    ("what is a heuristic", ["rule of thumb", "approximation"], []),
    ("how to wake up earlier", ["gradually", "light"], []),
    ("how to nap properly", ["20 minutes", "afternoon"], []),
]


def main():
    reset_conversation()
    passed = failed = 0
    failures = []
    for query, required, forbidden in CASES:
        response = process_query(query)
        low = response.lower()
        missing = [k for k in required if k.lower() not in low]
        bad = [f for f in (forbidden + FALLBACK_PHRASES) if f.lower() in low]
        if missing or bad:
            failed += 1
            failures.append((query, missing, bad, response[:200]))
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
