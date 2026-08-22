# Chef Claude — Web Nutrition Verification (hand-off for Claude Code)

## What this is

~2,481 recipes in the database are missing nutrition entirely (not the TV Show
Cookbook ones with estimated values — those are separate). Many of these were
originally clipped from real websites, and RecipeKeeper's browser clipper often
left the source site's name baked into the recipe title (e.g. "— Chef Charity
Morgan", "| What Great Grandma Ate", "- SAVEUR"). That means the *original*
recipe, with its *actual published nutrition label*, is often still findable
online — no estimation needed, just verification.

This is NOT a pure script — it's a judgment task. You (Claude Code) do the
searching, reading, and matching yourself, the same way you'd research
anything else. A helper script (below) handles the bookkeeping so you don't
have to hand-write JSON merges.

**This was piloted manually in a chat session first**: 5 recipes checked, 2
confirmed, and the two failure modes below were found empirically, not
theorized. Trust them.

## The core rule: verify ingredients, not just the title

A recipe *title* is not a unique identifier. Generic names ("Chipotle Sloppy
Joes", "Chicken Salad") have dozens of unrelated versions online with wildly
different nutrition — one pilot search found saturated fat ranging from 3g to
36g across different "Chipotle Sloppy Joes" recipes. Attaching any of those to
the wrong recipe would look authoritative while being flat wrong — worse than
no data at all, because nothing about it looks uncertain.

**Before accepting any nutrition data, compare the candidate page's full
ingredient list against the recipe's stored `ings` list.** Quantities and
items need to match closely (minor wording differences are fine — "onion,
finely chopped" vs "finely chopped onion" — but the actual foods and amounts
must line up). If a page is a *plausible* match but you can't confirm the
ingredients line up, reject it — do not guess.

Two outcomes only:
- **Confirmed**: ingredient list matches closely enough that you're confident
  this is the same recipe, AND the page has a real computed nutrition
  panel (calories + saturated fat at minimum).
- **Checked, no match**: anything else — wrong recipe, no nutrition panel
  found even though the recipe matched, or nothing findable at all. Record
  *why*, briefly, so it's not re-attempted pointlessly.

## Prioritization (do these first — much higher hit rate)

Titles that still carry a site attribution are far more likely to resolve to
an exact, verifiable match than generic titles, because you know exactly
which page to look for instead of guessing among lookalikes. Markers to look
for in the `name` field:
- An em dash or hyphen followed by a proper noun or site name: `— Chef Charity
  Morgan`, `- Wente Vineyards`, `- SAVEUR`
- A pipe followed by a site name: `| What Great Grandma Ate`, `| Edible East
  Bay`
- Distinctive multi-word or foreign-language titles (still worth trying, but
  lower hit rate than site-attributed ones — search first, don't over-invest
  if nothing turns up in 1-2 searches)

Deprioritize (skip or do last): short generic names with common food words
only (e.g. "Green Peas and Leeks", "Chicken Salad") — these are the least
likely to resolve safely and were the source of the one dangerous near-miss
in the pilot (Chipotle Sloppy Joes).

## Workflow

1. **Get the recipe database.** You need `chef_claude_recipe_database.json`
   (the combined RecipeKeeper export). It is NOT currently in the GitHub repo
   — it lives as a Project file in Claude.ai. The user needs to either commit
   it to the repo (e.g. `data/chef_claude_recipe_database.json`) or place it
   locally where you're running. Confirm its location before starting.

2. **Pull current progress.** Read (or `git pull`) the two tracking files from
   the repo:
   - `data/nutrition_web_verified.json`
   - `data/nutrition_web_checked_no_match.json`
   If they don't exist yet, initialize them with the starter content in
   `seed_files/` (provided alongside this handoff — contains the 2 confirmed
   + 6 checked-no-match from the pilot session).

3. **Get the next batch.** Run `get_next_batch.py` (below) to get a
   prioritized list of N recipes (default 20) that are missing nutrition and
   NOT already in either tracking file. Start with a batch of ~20-30 to
   calibrate your pace before doing larger runs.

4. **For each recipe in the batch:**
   a. Web search the recipe name (include distinguishing ingredient terms if
      the name alone is generic).
   b. If a plausible source page turns up, fetch it and read the full
      ingredient list and any nutrition panel.
   c. Compare ingredients against the recipe's `ings` field. Only proceed if
      they genuinely match.
   d. If matched AND a nutrition panel exists: extract calories, saturated
      fat, and total fat if given (protein/carbs too if easily available).
      Append to the confirmed list with the source URL and a one-line note on
      why you're confident it's a match.
   e. Otherwise: append to the checked-no-match list with a brief reason
      (e.g. "no exact match found", "page found but no nutrition panel",
      "generic name, multiple conflicting versions online, none matched").
   f. If a source website looks dead (404, domain expired), try the Wayback
      Machine (`web.archive.org/web/*/<url>`) before giving up — but only if
      you already have a specific URL to check (don't Wayback-search blind).

5. **Save after every batch, not just at the end.** Use `save_progress.py`
   (below) to merge new results into the two JSON files (it de-dupes by
   recipe id automatically) and write them back out.

6. **Commit and push after every batch**, so progress survives interruption:
   ```bash
   git add data/nutrition_web_verified.json data/nutrition_web_checked_no_match.json
   git commit -m "Web nutrition verification: batch of N (X confirmed, Y no-match)"
   git push
   ```

7. **Repeat** with the next batch. Stop whenever the user's time/budget for
   this session runs out — nothing is lost, next run just calls
   `get_next_batch.py` again and picks up where you left off.

## Data conventions (must match existing schema)

Confirmed entry shape (append to `data/nutrition_web_verified.json`):
```json
{
  "id": "<recipe id from chef_claude_recipe_database.json>",
  "name": "<exact recipe name>",
  "cal": 230,
  "satfat": 3.5,
  "totalfat": 6.6,
  "source": "web-verified",
  "method": "web-search",
  "source_url": "https://...",
  "match_confidence": "<one line: why you're confident this is the same recipe>",
  "verified_at": "YYYY-MM-DD"
}
```

Checked-no-match entry shape (append to `data/nutrition_web_checked_no_match.json`):
```json
{
  "name": "<exact recipe name>",
  "reason": "<brief reason, one line>"
}
```

Do not invent or estimate numbers here under any circumstances — this whole
pipeline exists because estimation already failed the accuracy bar. Every
number in `nutrition_web_verified.json` must come from a real, matched,
published source.

## Expectations on hit rate (from the pilot)

Roughly 1 in 3 recipes checked yield a confirmed match, better among
site-attributed titles. Budget accordingly — this is a long-tail cleanup
task, not something to expect to finish in one run. A partial pass that adds
30-50 genuinely confirmed recipes is a good outcome for a session.
