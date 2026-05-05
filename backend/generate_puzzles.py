#!/usr/bin/env python3
"""
Backsearch Daily Puzzle Pipeline
================================
Fetches real Google autocomplete suggestions for seed entities,
builds puzzle candidates, runs quality gate, outputs JSON.

Usage:
    python backend/generate_puzzles.py

Outputs:
    data/global/YYYY-MM-DD.json
    data/local/YYYY-MM-DD.json
"""

import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

# ─── CONFIG ──────────────────────────────────────────────────────────────────
AUTOCOMPLETE_URL = "https://suggestqueries.google.com/complete/search"
AUTOCOMPLETE_TIMEOUT = 12
REQUEST_DELAY = 0.25
PUZZLES_PER_LOCALE = 5
DISTRACTORS_PER_PUZZLE = 7

# Specific facts / locations that make a good "smoking gun"
SMOKING_GUN_TERMS = {
    "albuquerque", "chicago", "new york", "los angeles", "london", "paris",
    "tokyo", "bangkok", "phuket", "bali", "thailand", "korea", "india",
    "bollywood", "hollywood", "mexico", "brazil", "spain", "italy", "japan",
    "sandwich", "restaurant", "michelin", "street food", "chef", "kitchen",
    "netflix", "hbo", "disney", "apple tv", "hulu", "prime video",
    "grammy", "oscar", "emmy", "trophy", "award", "nominated",
    "season 2", "season 3", "season 4", "season 5", "season 6",
    "episode", "finale", "pilot", "remake", "sequel", "spin-off",
    "dollar", "million", "billion", "price", "cost", "expensive", "cheap",
    "waterproof", "wireless", "charger", "battery", "camera", "screen",
    "vegan", "gluten", "spicy", "recipe", "homemade",
    "festival", "celebration", "parade", "holiday",
    "ban", "illegal", "legal", "law", "regulation",
}

# Non-English markers (reject if these appear)
NON_ENGLISH_MARKERS = [
    " ist ", " ist", "ist ", " das ", " der ", " die ", " ein ", " eine ",
    " verheiratet", " verlobt", " schwanger", " haare", " haar",
    " wasserdicht", " langsam", " gut", " schlecht", " kostenlos",
    " ka\u00e7 ", " saat", " flug", " flugzeit", " nerede", " nas\u0131l",
    " es ", " la ", " el ", " los ", " las ", " una ", " un ", " como ",
    " que ", " por ", " para ", " con ", " del ", " je ", " suis ",
    " tu ", " il ", " elle ", " c'est ", " \u0435\u0441\u0442\u044c ",
    " \u0438 ", " \u0432 ", " \u043d\u0430 ", " \u0447\u0442\u043e ",
    " muslimisch", " christlich", " j\u00fcdisch",
]

# Exclusion list for moderation
EXCLUSION_PATTERNS = [
    r"\b(dead|died|death|killed|murder|suicide)\b",
    r"\b(cancer|tumor|disease|symptom|diagnosis)\b",
    r"\b(sex|porn|nude|naked|onlyfans)\b",
    r"\b(racist|racism|nazi|hitler|holocaust)\b",
    r"\b(terrorist|terrorism|bomb|shooting|attack)\b",
    r"\b(arrested|jail|prison|crime|criminal|trial|lawsuit)\b",
    r"\b(pedophile|molest|rape|abuse|assault)\b",
    r"\b(gay|lesbian|transgender|homosexual)\b",  # can be weaponized in search
    r"\b(scam|scammer|fraud|fake|hoax)\b",
    r"\b(ugly|fat|stupid|idiot|dumb)\b",
]

# Suffixes / topics that make boring completions
BORING_PATTERNS = [
    r"\b(net worth|age|height|birthday|real name|wife|husband|girlfriend|boyfriend|dating|married|divorce)\b",
    r"\b(kids|children|family|parents|siblings|nationality|ethnicity|religion|zodiac)\b",
    r"\b(instagram|twitter|facebook|tiktok|youtube|reddit|snapchat)\b",
    r"\b(wiki|wikipedia|biography|bio|phone number|email|address)\b",
    r"\b(where from|from where|born in|where born|where is)\b",
    r"\b(jacket|shirt|dress|outfit|shoes|hair|hairstyle|makeup)\b",
    r"\b(schedule|itinerary|tour dates|concert dates|setlist)\b",
    r"\b(ticket price|tickets|vip|meet and greet)\b",
]

# Known brand/website names that sneak into suggestions
BRAND_NAMES = {
    "justwatch", "netflix", "hulu", "disney+", "prime video", "apple tv+",
    "youtube", "spotify", "tidal", "soundcloud", "bandcamp",
    "imdb", "rotten tomatoes", "metacritic", "letterboxd",
    "wikipedia", "wiki", "reddit", "twitter", "x.com",
    "justtrade", "robinhood", "coinbase", "binance",
    "meme", "tiktok", "reels", "shorts",
}

# Common first names that indicate cross-person searches
COMMON_NAMES = {
    "justin", "timberlake", "bieber", "baldoni", "wilson", "blake", "lively",
    "william", "walton", "faulkner", "poulter", "cate", "blanchett",
    "masha", "albert", "marcus", "isaacson", "isaac", "kappy",
    "sun", "mamdani", "traveller", "traveler",
}

# ─── UTILITIES ───────────────────────────────────────────────────────────────

def today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=True, indent=2)

# ─── AUTOCOMPLETE ────────────────────────────────────────────────────────────

def fetch_autocomplete(query: str) -> list[str]:
    """Fetch autocomplete suggestions for a query."""
    try:
        params = {"client": "firefox", "q": query}
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(
            AUTOCOMPLETE_URL,
            params=params,
            headers=headers,
            timeout=AUTOCOMPLETE_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        if len(data) > 1 and isinstance(data[1], list):
            return [s for s in data[1] if isinstance(s, str)]
    except Exception as e:
        print(f"  Autocomplete error for '{query}': {e}", file=sys.stderr)
    return []


def strip_entity_prefix(suggestion: str, entity_name: str) -> str:
    """Strip entity name and connector words from suggestion."""
    lower_s = suggestion.lower()
    entity_lower = entity_name.lower()
    idx = lower_s.find(entity_lower)
    if idx == -1:
        return suggestion

    result = suggestion[idx + len(entity_name):].lstrip()

    connectors = [
        r"^(is a|is|are|was|were|has a|has|have|had|will|would|can|could|should|may|might|just|getting)\s+",
        r"^(a|an|the|to|in|on|at|for|with|from|by|about|into|through|during|before|after|of)\s+",
        r"^(it|there|that|this|these|those|what|how|why|when|where|who|which)\s+",
    ]
    for pattern in connectors:
        result = re.sub(pattern, "", result, flags=re.IGNORECASE)

    return result.strip(" -:;.?!\"'()")


def is_english_text(text: str) -> bool:
    """Quick heuristic: reject if too many non-ASCII chars or known foreign markers."""
    lower = text.lower()
    for marker in NON_ENGLISH_MARKERS:
        if marker in lower:
            return False
    # Count non-ASCII
    non_ascii = sum(1 for c in text if ord(c) > 127)
    if len(text) > 0 and non_ascii / len(text) > 0.15:
        return False
    return True


def contains_proper_noun(text: str) -> bool:
    """Check if text contains capitalized words mid-sentence (likely other proper nouns)."""
    words = text.split()
    for i, word in enumerate(words):
        clean = re.sub(r"[^\w]", "", word)
        if len(clean) < 3:
            continue
        # First word can be capitalized (start of sentence)
        if i == 0:
            continue
        # All-caps words like TV, HBO, OK
        if clean.isupper() and len(clean) <= 4:
            continue
        # Capitalized mid-sentence = likely proper noun
        if clean[0].isupper() and clean[1:].islower():
            return True
    return False


def contains_brand_name(text: str) -> bool:
    lower = text.lower()
    for brand in BRAND_NAMES:
        if brand in lower:
            return True
    return False


def contains_common_cross_name(text: str) -> bool:
    lower = text.lower()
    for name in COMMON_NAMES:
        if name in lower:
            return True
    return False


def clean_completion(completion: str, entity_name: str) -> str | None:
    """Clean and validate an autocomplete suggestion."""
    if not completion or len(completion) < 5:
        return None

    stripped = strip_entity_prefix(completion, entity_name)
    if not stripped or len(stripped) < 8:
        return None
    if len(stripped) > 120:
        return None

    lower = stripped.lower()

    # Language check
    if not is_english_text(stripped):
        return None

    # Boring patterns
    for pattern in BORING_PATTERNS:
        if re.search(pattern, lower):
            return None

    # Moderation
    for pattern in EXCLUSION_PATTERNS:
        if re.search(pattern, lower):
            return None

    # Reject if contains other proper nouns (cross-searches)
    if contains_proper_noun(stripped):
        return None

    # Reject brand names
    if contains_brand_name(stripped):
        return None

    # Reject common cross-person names
    if contains_common_cross_name(stripped):
        return None

    # Reject if still contains entity name
    entity_lower = entity_name.lower()
    if entity_lower in lower:
        return None

    # Reject short questions
    if stripped.endswith("?") and len(stripped) < 15:
        return None

    # Reject single words after cleaning
    if len(stripped.split()) < 2:
        return None

    return stripped


def gather_completions(entity: dict) -> list[str]:
    """Gather autocomplete completions for an entity."""
    entity_name = entity["name"]
    # Use "is a" and "just" as primary prefixes - they produce the best sentence-like completions
    prefixes = entity.get("prefixes", ["is a", "is", "just", "has a", "will"])
    all_suggestions: list[str] = []

    for prefix in prefixes:
        query = f"{entity_name} {prefix}"
        suggestions = fetch_autocomplete(query)
        for suggestion in suggestions:
            cleaned = clean_completion(suggestion, entity_name)
            if cleaned and cleaned not in all_suggestions:
                all_suggestions.append(cleaned)
        time.sleep(REQUEST_DELAY)

    return all_suggestions


# ─── QUALITY GATE ────────────────────────────────────────────────────────────

def has_smoking_gun(completions: list[str]) -> bool:
    """At least one completion contains a specific fact."""
    for c in completions:
        lower = c.lower()
        for loc in SMOKING_GUN_TERMS:
            if loc in lower:
                return True
        if re.search(r"\b\d{2,4}\b", c):
            return True
        if re.search(r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b", lower):
            return True
        if re.search(r"\$\d+", c):
            return True
        if re.search(r"\d+%", c):
            return True
    return False


def score_diversity(completions: list[str]) -> float:
    if len(completions) < 2:
        return 0.0
    words_list = [set(re.findall(r"\b\w+\b", c.lower())) for c in completions]
    overlaps = []
    for i in range(len(words_list)):
        for j in range(i + 1, len(words_list)):
            intersection = len(words_list[i] & words_list[j])
            union = len(words_list[i] | words_list[j])
            if union > 0:
                overlaps.append(intersection / union)
    if not overlaps:
        return 1.0
    avg_overlap = sum(overlaps) / len(overlaps)
    return 1.0 - avg_overlap


def run_quality_gate(entity: dict, completions: list[str]) -> dict | None:
    entity_name = entity["name"]
    category = entity["category"]

    if len(completions) < 5:
        return None

    entity_lower = entity_name.lower()
    for c in completions:
        lower = c.lower()
        if entity_lower in lower:
            return None

    if not has_smoking_gun(completions):
        return None

    diversity = score_diversity(completions)
    if diversity < 0.25:
        return None

    selected = completions[:5]

    return {
        "answer": entity_name,
        "prefixVerb": entity.get("prefixes", ["is"])[0],
        "category": category,
        "completions": selected,
        "distractors": [],
    }


# ─── PUZZLE BUILDER ──────────────────────────────────────────────────────────

def build_puzzles(entities: list[dict], locale: str) -> list[dict]:
    candidates: list[dict] = []
    print(f"\nBuilding puzzles for {locale}...")

    for entity in entities:
        print(f"  Processing: {entity['name']}")
        completions = gather_completions(entity)
        print(f"    Found {len(completions)} valid completions")
        if completions:
            print(f"    Samples: {completions[:5]}")

        puzzle = run_quality_gate(entity, completions)
        if puzzle:
            candidates.append(puzzle)
            print(f"    PASSED quality gate")
        else:
            print(f"    FAILED quality gate")

    selected = candidates[:PUZZLES_PER_LOCALE]
    if len(selected) < PUZZLES_PER_LOCALE:
        print(f"  WARNING: Only {len(selected)} puzzles passed (wanted {PUZZLES_PER_LOCALE})")

    return selected


def add_distractors(puzzles: list[dict], all_entities: list[dict]) -> list[dict]:
    for puzzle in puzzles:
        category = puzzle["category"]
        answer = puzzle["answer"]
        same_category = [
            e["name"] for e in all_entities
            if e["category"] == category and e["name"] != answer
        ]
        if len(same_category) >= DISTRACTORS_PER_PUZZLE:
            distractors = random.sample(same_category, DISTRACTORS_PER_PUZZLE)
        else:
            others = [
                e["name"] for e in all_entities
                if e["name"] != answer and e["name"] not in same_category
            ]
            needed = DISTRACTORS_PER_PUZZLE - len(same_category)
            extra = random.sample(others, min(needed, len(others))) if others else []
            distractors = same_category + extra
        puzzle["distractors"] = distractors
    return puzzles


def pick_tomorrow_teaser(entities: list[dict], used_answers: set[str]) -> dict:
    available = [e for e in entities if e["name"] not in used_answers]
    if available:
        chosen = random.choice(available)
    else:
        chosen = random.choice(entities)
    return {"entity": chosen["name"], "typeLabel": chosen["category"]}


# ─── MAIN ────────────────────────────────────────────────────────────────────

def generate_for_locale(locale: str, entities: list[dict]) -> dict:
    date_str = today_str()
    city = "Global" if locale == "global" else "Bangkok"
    flag = "\ud83c\udf10" if locale == "global" else "\ud83c\uddf9\ud83c\udded"

    puzzles = build_puzzles(entities, locale)
    puzzles = add_distractors(puzzles, entities)

    used_answers = {p["answer"] for p in puzzles}
    tomorrow_teaser = pick_tomorrow_teaser(entities, used_answers)

    return {
        "date": date_str,
        "city": city,
        "flag": flag,
        "tomorrowTeaser": tomorrow_teaser,
        "puzzles": puzzles,
        "_generatedAt": datetime.now(timezone.utc).isoformat(),
        "_source": "autocomplete_pipeline_v1",
    }


def main() -> int:
    repo_root = Path(__file__).parent.parent
    seed_path = repo_root / "backend" / "seed_entities.json"

    if not seed_path.exists():
        print(f"ERROR: Seed file not found: {seed_path}", file=sys.stderr)
        return 1

    seeds = load_json(seed_path)
    exit_code = 0

    for locale in ["global", "local"]:
        entities = seeds.get(locale, [])
        if not entities:
            print(f"WARNING: No seed entities for locale '{locale}'")
            continue

        output = generate_for_locale(locale, entities)

        out_dir = repo_root / "data" / locale
        out_path = out_dir / f"{output['date']}.json"
        save_json(out_path, output)
        print(f"  Saved: {out_path}")
        print(f"  Puzzles: {len(output['puzzles'])}")

        if len(output["puzzles"]) < PUZZLES_PER_LOCALE:
            print(f"  WARNING: Only {len(output['puzzles'])} puzzles generated")
            exit_code = 2

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
