"""Frozen entity-extraction fixtures (roadmap item 66, IBM VLDB 2026 gate).

Each case: {content, expected}. expected is the hand-labeled entity set a
good extractor should emit (normalized lowercase, whitespace collapsed).
Common-noun bridge entities are included where they carry multi-hop weight
(item 65): "sister", "espresso", "bakery". NEVER edit a case casually -
this set is the acceptance gate comparing deterministic vs LLM extraction.
"""

def _c(content, expected):
    return {"content": content, "expected": sorted(e.lower() for e in expected)}

CASES = [
    _c("Ethan's sister is Sarah.", ["ethan", "sister", "sarah"]),
    _c("Sarah likes espresso from the Bluecup cafe.", ["sarah", "espresso", "bluecup cafe"]),
    _c("Uncle Marco runs the bakery on Fifth Street.", ["uncle marco", "bakery", "fifth street"]),
    _c("Postgres is the production database.", ["postgres", "production database"]),
    _c("The deploy freezes every Friday.", ["deploy", "friday"]),
    _c("Remind me to call Dana at 3pm tomorrow.", ["dana"]),
    _c("My accountant Dana prefers email over phone.", ["accountant", "dana", "email", "phone"]),
    _c("The Q3 board meeting moved to the Morrison Hotel.", ["q3", "board meeting", "morrison hotel"]),
    _c("Jules works at Acme Corp as a designer.", ["jules", "acme corp", "designer"]),
    _c("The onboarding doc lives in Notion.", ["onboarding doc", "notion"]),
    _c("Priya said the API migration finishes in October.", ["priya", "api migration", "october"]),
    _c("Water the plants every Sunday morning.", ["plants", "sunday"]),
    _c("The wifi password is written on the fridge.", ["wifi password", "fridge"]),
    _c("Grandma Rosa's birthday is March 12.", ["grandma rosa", "birthday", "march 12"]),
    _c("The standing desk arrived from Fully.", ["standing desk", "fully"]),
    _c("Dr. Chen prescribed ibuprofen for the back pain.", ["dr. chen", "ibuprofen", "back pain"]),
    _c("The flight to Lisbon leaves from gate B22.", ["flight", "lisbon", "gate b22"]),
    _c("Sam owes me $40 for the concert tickets.", ["sam", "concert tickets"]),
]
