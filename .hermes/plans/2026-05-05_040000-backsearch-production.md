# Backsearch — Production Implementation Plan

**Goal:** Transform the existing Backsearch v4 prototype into the production-grade daily reverse-autocomplete puzzle game specified in the full PRD, with progressive completion reveal, LLM-powered content generation, editorial visual design, and growth-ready sharing.

**Date:** May 5, 2026
**Current State:** v4 single-file HTML (877 lines, 39KB), deployed to `yaronbada.github.io/autocomplete-showdown`, 5 hardcoded puzzles, basic tap-card grid, 3-tier scoring.
**Target State:** Full production spec with 7-completion progressive reveal, 5-tier scoring, LLM pipeline, curator UI, OG images, locale fallback chain.

---

## Architecture Decision: Stay Single-File HTML + JS, NOT Next.js

The spec says "Next.js + edge functions" but for v1, the frontend can remain a **single-file HTML PWA** while the backend pipeline remains Python scripts. Reasons:

1. **No user auth, no database** — the spec explicitly says "Player state in localStorage only — no auth, no user DB in v1." There is nothing Next.js SSR gives us that matters for the gameplay.
2. **The data pipeline already works** — `backend/generate_puzzles.py` generates JSON files that are served as static assets from GitHub Pages. No edge functions needed.
3. **OG image**: Can be a pre-generated static PNG committed alongside daily data, served from GitHub Pages. No runtime SSR needed.
4. **Percentile aggregation**: The spec's client-side mock with daily seed is already implemented and functional. Server-side aggregation can be added later when real player counts exist.
5. **Speed**: Single-file HTML deploys instantly. No build step. No `node_modules`. No npm. No Next.js config. The existing pipeline already works for the data layer.

**What we DO need from "Next.js"**: Nothing in v1. The data pipeline is Python. The frontend is HTML/JS/CSS. GitHub Pages serves it all.

---

## Phase 1: Frontend Game Engine Rewrite (Core Mechanics)

This is the biggest single change. The current v4 game uses the old "5 completions revealed all at once, score based on wrong guesses" mechanic. The spec requires a fundamentally different mechanic.

### 1.1 Data Schema Change
Each puzzle changes from 5 completions to 7, with an explicit reveal order and specificity:

```js
// OLD
{ answer, prefixVerb, category, completions: [5 strings], distractors: [7 strings] }

// NEW
{
  answer, prefixVerb, category,
  completions: [
    { text: "...", position: 1, specificity: "ambiguous" },
    { text: "...", position: 2, specificity: "ambiguous" },
    { text: "...", position: 3, specificity: "triangulating" },
    { text: "...", position: 4, specificity: "triangulating" },
    { text: "...", position: 5, specificity: "narrowing" },
    { text: "...", position: 6, specificity: "narrowing" },
    { text: "...", position: 7, specificity: "smoking_gun" }
  ],
  distractors: [7 strings],
  entityType: "show",  // renamed from 'category' for clarity
  difficulty: "easy|medium|hard",
  whyTrending: "one-line context"
}
```

### 1.2 Progressive Reveal System

**Start state:** 2 completions visible. Remaining 5 hidden.
**"Reveal another" button:** Each click reveals the next completion in sequence (position 3→4→5→6→7). Each reveal costs 1 point from max.
**After 7 reveals (all shown):** Button becomes "Reveal answer" → tapping = 0 pts for that puzzle.

**Scoring table:**
| Completions revealed when solved | Points |
|---|---|
| 2 (start) | 5 |
| 3 | 4 |
| 4 | 3 |
| 5 | 2 |
| 6 or 7 | 1 |
| Failed / auto-reveal | 0 |
| **Daily max** | **25** |

### 1.3 Wrong Guess Behavior (Critical Change)
- **Wrong guesses are FREE.** They do NOT cost points.
- Wrong guesses do NOT reveal more completions.
- Wrong guesses simply dim the tapped card (visual feedback only).
- Player can keep guessing wrong indefinitely — only voluntary reveals cost points.
- This separates "I'm not sure" from "I'm wrong" — the key insight from the spec.

### 1.4 State Machine Changes

```js
let state = {
  screen: "landing",
  round: 0,
  results: [],           // per-round outcomes
  revealedCount: 2,      // how many completions currently visible this round
  wrongCards: [],        // indices of wrong-guessed cards this round
  mode: "local",
  completed: false,
  percentile: null
};

// Per-round result:
{
  answer: "Taylor Swift",
  score: 4,              // 0-5
  revealedCompletions: 3, // how many were visible when solved
  wrongGuesses: 2,
  failed: false
}
```

### 1.5 Share Grid Change (Variable-Row Format)

```
Backsearch — May 4 — Bangkok 🇹🇭
17/25 · solved in 2-3-5-4-2 (avg 3.2)
· better than 73% of Bangkok

🟩🟩
🟩🟩🟩
🟩🟩🟩🟩🟩
🟩🟩🟩🟩
🟩🟩

Tomorrow's puzzle includes: BLACKPINK

Guess the search from autocomplete-style clues.
backsearch.app
```

Each row has N green squares where N = completions visible when solved. Failed = 7 grey squares. Row length tells the story of the player's path, not the answer.

### 1.6 Round Screen Layout (Spec-Compliant)

```
┌──────────────────────────────┐
│ Backsearch · 4/5 · 12pts     │  ← minimal header bar
├──────────────────────────────┤
│         ___█                  │  ← prefix blank with blinking cursor
│                              │
│  1. first completion text    │  ← plain italic serif, no card chrome
│  2. second completion text   │
│  3. third completion text    │  ← faded in after reveal
│                              │
│  Reveal another (-1 pt)      │  ← subtle text-link style button
│                              │
│  Which show?                 │  ← entity-type in accent color
│                              │
│  ┌─────────┐ ┌─────────┐    │
│  │ Card A  │ │ Card B  │    │  ← 4×2 card grid
│  ├─────────┤ ├─────────┤    │  ← names only, no images
│  │ Card C  │ │ Card D  │    │
│  ├─────────┤ ├─────────┤    │
│  │ Card E  │ │ Card F  │    │
│  ├─────────┤ ├─────────┤    │
│  │ Card G  │ │ Card H  │    │
│  └─────────┘ └─────────┘    │
└──────────────────────────────┘
```

### 1.7 End Screen Layout (Asymmetric, Spec-Compliant)

```
┌──────────────────────────────────┐
│                                  │
│              17/25               │  ← centered, accent, large serif
│        better than 73% of BKK    │
│                                  │
│  TOMORROW'S PUZZLE INCLUDES     │  ← left-aligned editorial block
│  BLACKPINK                       │  ← large italic serif, no card
│                                  │
│  ┌────────────────────────────┐  │
│  │ Backsearch — May 4 — 🇹🇭   │  │  ← grid box
│  │                            │  │
│  │ 🟩🟩                       │  │
│  │ 🟩🟩🟩                     │  │
│  │ 🟩🟩🟩🟩🟩                │  │
│  │ 🟩🟩🟩🟩                   │  │
│  │ 🟩🟩                       │  │
│  └────────────────────────────┘  │
│                                  │
│  [Copy results]                  │  ← dark ink-tone, not accent
│                                  │
│  Play again                      │  ← small text link
│                                  │
│  Guess the search from           │  ← tiny elevator pitch
│  autocomplete-style clues.       │
│  backsearch.app                  │
└──────────────────────────────────┘
```

---

## Phase 2: Visual Design Implementation

### 2.1 Completions: Strip Card Chrome
- Remove: `background`, `border`, `border-radius`, `box-shadow` from completion items
- Keep: plain italic serif (`Fraunces`), generous line-height (1.55+), numerals as muted sans
- New completions fade in with 400ms ease + slight upward slide
- Already-revealed completions stay at full opacity

### 2.2 Accent Color Discipline
- **Round screen:** Accent only on the entity-type word in "Which *show*?"
- **End screen:** Accent only on the score number
- Score number in round header: bold near-black, NOT accent

### 2.3 Candidate Cards
- Keep card treatment: serif names only, no images, no metadata
- 2 columns on narrow mobile (≤480px), 4 columns on wider
- Dimmed state: opacity 0.3, no pointer events
- Correct state: green border + green-light background

### 2.4 Reveal Button
- Near-text-link styling: subtle, not a tempting candy
- "Reveal another (−1 pt)" → small, accent-light background, dashed border
- After 7 reveals → "Reveal answer" (same styling, different text)

### 2.5 Reveal Animation (On Correct Guess)
1. Answer entity name fades in above candidate list
2. Each completion re-renders one at a time with entity prepended (~600ms stagger)
3. Player taps "Next puzzle →" to advance

### 2.6 Tomorrow's Teaser on End Screen
- Small caps label "TOMORROW'S PUZZLE INCLUDES"
- Real entity name in large italic serif below
- No card chrome — treated as an epigraph
- Left-aligned to break centered-everything pattern

---

## Phase 3: Data Pipeline — LLM Completion Generation

This is the highest-stakes part. The current pipeline uses raw Google autocomplete with quality filtering. The spec requires LLM-generated completions for puzzle quality, with raw autocomplete as input signal only.

### 3.1 Three-Source Input Pipeline

**Source 1 — Trending Now entity picker:**
- Pull daily trending entities from Google Trends RSS/API for the locale
- Filter by category: prefer entertainment, food, sports, viral memes
- Skip: deaths, criminal cases, grim topics
- For each puzzle: pick 1 answer + 7 distractors of same type from same day's pool

**Source 2 — Raw autocomplete as topical signal:**
- Fetch real Google autocomplete for the answer entity (existing `fetch_autocomplete` function)
- Use as INPUT SIGNAL for LLM, not final content
- Tell LLM what people are actually curious about

**Source 3 — Recent news headlines (optional):**
- Pull recent news fact about the answer entity
- Becomes the seed for the smoking-gun completion
- Without this, smoking-guns tend to be generic

### 3.2 LLM Completion Generation Prompt

The spec provides a detailed system instruction and per-puzzle prompt template. Key requirements:
- 7 completions, 2-6 words each, lowercase, no punctuation
- Sentence-fragment style (like real autocomplete)
- One smoking-gun completion (position 7)
- Order from most ambiguous → most specific
- No entity naming, no cross-searches, no brand collisions
- Reject: boring personal-life topics, moderation-flagged content

### 3.3 Implementation Approach

The LLM pipeline is the biggest new subsystem. For v1, we have two options:

**Option A: External API (OpenAI/Claude)** — Call an LLM API from the Python pipeline script. Requires an API key. Best quality but adds cost and dependency.

**Option B: Template-based generation (interim)** — Use the existing raw autocomplete pipeline plus human-written templates to generate 7-completion puzzles. Lower quality but works immediately. We can swap to LLM later.

**Recommendation:** Start with Option B (template-based) for immediate shipping, then add LLM generation as a separate upgrade path. The spec says "Don't ship the pipeline until ~80% of cold-reads feel solvable-but-not-trivial" — this calibration takes days, so we should ship the game engine first with template-based puzzles and calibrate in parallel.

### 3.4 Post-Generation Quality Checks (Automated)

For each generated puzzle:
1. **Shape check:** Each completion 2-6 words, lowercase, no terminal punctuation
2. **Name leakage:** No completion contains answer's name/nicknames/entity-type
3. **Distractor leakage (LLM grader):** A second LLM call checks if the answer can be uniquely identified from completions alone
4. **Moderation:** Hard exclusion list applied
5. **Smoking-gun verification:** Position-7 completion is meaningfully more specific
6. Up to 2 regeneration retries, then reject and pick different entity

### 3.5 Human Gate (Curator UI)

A simple HTML page that shows:
- Answer entity, why trending, distractor list
- 7 completions in reveal order with smoking-gun flagged
- Confidence score, LLM notes
- Actions: Approve, Swap one completion, Reject

Estimated 5 min/day of human review.

---

## Phase 4: OG Image Generation

### 4.1 Design
- Render today's 5 most evocative completions as a found poem on cream
- 8 candidate names in small grid below (no answer revealed)
- Title: "Backsearch — [date] — [city]"
- Nothing else — the mystery sells itself

### 4.2 Implementation
- Python script using Pillow (already available) or headless browser screenshot
- Generated during daily pipeline run
- Saved as `og-{locale}-{date}.png` alongside puzzle data
- Referenced via `<meta property="og:image">` in HTML

---

## Phase 5: Locale System

### 5.1 Current State
- Two modes: local (Bangkok) / global
- Mode toggle on landing page
- localStorage preference persistence

### 5.2 Spec Requirements (Not Yet Implemented)
- IP-based default detection (server-side or client-side geo-IP)
- Multiple locale support (Bangkok, Tel Aviv, etc.)
- Locale fallback chain:
  1. City-level trending
  2. Country-level trending
  3. Curated evergreen pool
  4. Yesterday's puzzle with banner (last resort)

### 5.3 v1 Scope
For v1, stay with the current Bangkok/Global toggle. The locale fallback chain requires trending data infrastructure that doesn't exist yet. Add additional cities incrementally.

---

## Phase 6: Infrastructure

### 6.1 Cron Job for Daily Generation
- GitHub Actions workflow: `backend/generate_puzzles.py` runs daily at 02:30 UTC
- Generates `data/{local,global}/YYYY-MM-DD.json`
- Also generates OG images
- Auto-commits and pushes to `main`
- **Note:** PAT needs `workflow` scope (the user's current token lacks this — needs updating)

### 6.2 Data Loading (Frontend)
- Already implemented: fetch chain (daily JSON → evergreen JSON → hardcoded fallback)
- Needs updating: handle new puzzle schema (7 completions with metadata)
- Cache-busting with `?v=Date.now()` already in place

### 6.3 PWA
- `manifest.json` already set up
- Service worker for offline caching (add if not present)
- Apple touch icon

---

## Phase 7: Calibration (Pre-Launch)

The spec requires 20 hand-run puzzles validated before the LLM pipeline goes live. Steps:

1. Generate 20 puzzles using the pipeline (template-based initially, then LLM)
2. For each: cold-read the 7 completions and try to guess the entity from the list of 8
3. Answer: solvable but not trivial? Smoking-gun actually a smoking-gun?
4. Did anything make you smile?
5. Iterate on prompts/templates based on failures
6. Ship only when ~80% feel solvable-but-not-trivial

---

## Implementation Order (Priority)

### Step 1: Update Puzzle Data Format (1 hour)
- Change puzzle schema to include 7 completions with specificity metadata
- Update fallback data (both local and global)
- Update evergreen JSON files
- Update backend pipeline output format

### Step 2: Rewrite Frontend Game Engine (3-4 hours)
This is the core of the implementation:
- Progressive reveal system (start with 2, reveal up to 7)
- New scoring (5-tier: 5/4/3/2/1/0, max 25)
- Wrong guesses = free (no point cost)
- "Reveal another" button that transforms to "Reveal answer" after 7
- Updated state machine
- Updated share grid (variable-row format)
- Updated reveal animation
- Updated round screen layout

### Step 3: Visual Design Polish (2 hours)
- Strip card chrome from completions
- Accent color discipline
- Tomorrow's teaser redesign (entity name, not completion text)
- End screen asymmetric layout
- Animations for completion reveal

### Step 4: Backend Pipeline Update (2 hours)
- Generate 7 completions instead of 5
- Add specificity metadata
- Add "why trending" context
- OG image generation script (Pillow)
- Update GitHub Actions workflow

### Step 5: Curator UI (1-2 hours)
- Simple HTML page for human review
- Shows generated puzzles with approve/swap/reject

### Step 6: Deploy & Test (1 hour)
- Push all changes
- Browser testing on mobile
- End-to-end gameplay test
- Verify share grid formatting

---

## Anti-Patterns (From Spec — DO NOT VIOLATE)

- ❌ Don't market completions as "real Google autocomplete"
- ❌ Don't generate puzzles in batches and cherry-pick
- ❌ Don't skip calibration
- ❌ Don't skip human gate
- ❌ Don't make "reveal another" time-triggered
- ❌ Don't penalize wrong guesses with extra reveals
- ❌ Don't show how many completions remain
- ❌ Don't show difficulty rating on round screen
- ❌ Don't use card chrome on completions
- ❌ Don't center every element
- ❌ Don't ship platform-specific share buttons
- ❌ Don't include user identifiers in share text
- ❌ Don't show solved completions in share
- ❌ Don't show entity images on candidate cards
- ❌ Don't generate distractor entities (must be real)
- ❌ Don't ship without locale fallback chain

---

## Files Changed

| File | Change |
|---|---|
| `index.html` | **Major rewrite** — new game engine, scoring, UI |
| `data/evergreen/local.json` | Update to 7-completion schema |
| `data/evergreen/global.json` | Update to 7-completion schema |
| `data/local/*.json` | New puzzle format |
| `data/global/*.json` | New puzzle format |
| `backend/generate_puzzles.py` | 7 completions, specificity, OG image |
| `backend/seed_entities.json` | Add "why trending" field |
| `backend/generate_og.py` | **New file** — OG image generation |
| `backend/curator.html` | **New file** — human gate UI |
| `backend/requirements.txt` | Add Pillow |
| `.github/workflows/daily-puzzle.yml` | Add OG generation step |

---

## Risks & Open Questions

1. **PAT workflow scope:** Current token lacks `workflow` scope. GitHub Actions push will fail. User needs to update token at github.com/settings/tokens.
2. **LLM API cost:** Using OpenAI/Claude API for completion generation adds recurring cost. Template-based approach avoids this initially.
3. **Google Trends API:** Not free, heavily rate-limited. The spec says "Trending Now feed (the structured, region-filtered surface)" — we need to investigate what API/feed this refers to. For v1, we can use the existing seed entity list as a stand-in.
4. **News API:** For smoking-gun factual hooks, we need a news source. Google News RSS is free but limited. For v1, manually written "why trending" context in seed entities works.
5. **Domain name:** The spec references `backsearch.app`. Currently deployed at `yaronbada.github.io/autocomplete-showdown/`. A custom domain would need purchasing and configuring.
6. **Repo rename:** `autocomplete-showdown` → `backsearch` would be cleaner but risks breaking existing links.
