# Nutrition Enrichment — hand-off for Claude Code

Fills in per-serving nutrition for recipes that are missing it, using the free **USDA FoodData
Central (FDC)** API. It captures the **full macro panel** per serving — calories, protein, total
fat, carbs, sugar, fiber, sodium, and saturated fat (`MACRO_KEYS` in the script). Designed to be
honest: it doesn't assert accuracy, it **measures** it — backtesting against recipes that already
have real numbers, finding the confidence level that yields ≥90% of estimates within ±10%, and
filling only recipes at/above that bar. If nothing clears it, it writes nothing.

> **Measured result (2026-08-21, 5,121-recipe database):** no confidence threshold cleared the
> 90%/±10% bar — accuracy was ~9–10% within ±10% and flat across all confidence levels, a
> systematic gram-estimation/USDA-matching limitation, not tunable noise. **So the tool wrote no
> `recipes_enriched.json`; the app database was left untouched.** See `datasets/` for the evidence.

## Files
- `enrich_nutrition.py` — the pipeline (parse → estimate → calibrate → enrich).
- `requirements.txt` — deps (`requests`, `beautifulsoup4`, `lxml`).
- `datasets/` — exported evidence from the full run (see **Datasets** below).

## What you need
1. **A free USDA FDC API key:** https://fdc.nal.usda.gov/api-key-signup.html
   ```
   export USDA_API_KEY=your_key_here
   ```
2. **The recipe source(s):** the RecipeKeeper HTML export(s) — the `recipes.html` file(s) from
   the user's uploads (the same ones behind `chef_claude_recipe_database.json`). Point `--input`
   at them (glob ok). *The script reads RecipeKeeper's microdata HTML directly.*
3. `pip install -r requirements.txt`

## Run it
```bash
# 1) Backtest + calibrate ONLY (see the accuracy table, decide the threshold) — no writes:
python enrich_nutrition.py --input "recipes_src/**/recipes.html" --mode backtest

# 2) Full run: calibrate, then enrich missing recipes at/above the calibrated threshold:
python enrich_nutrition.py --input "recipes_src/**/recipes.html" \
    --out data/recipes_enriched.json --mode both
```
Useful flags: `--tolerance 0.10` (the ±band = "90% accurate"), `--target 0.90` (required hit-rate),
`--threshold 0.95` (skip calibration, force a confidence cutoff), `--max-backtest 1200`,
`--max-per-hour 950` (proactive throttle to stay under FDC's free-key ~1,000 req/hour cap — the
script sleeps `3600/max_per_hour` seconds between live calls; cached lookups are free).

## How it works (and why it's safe)
1. **Parse** every recipe (name, yield, ingredients) from the RecipeKeeper HTML.
2. **Estimate** each recipe: parse each ingredient's quantity/unit → grams (handles cups, tbsp/tsp
   with fat-specific weights, counts like "3 cloves", unicode fractions like `1½`, and stated
   weights in parentheses like `(14.5 oz)`), look up the per-100 g macro panel (calories, protein,
   fat, carbs, sugar, fiber, sodium, sat fat) from USDA FDC (Foundation / SR Legacy), sum each
   macro, divide by servings. Salt/water/pepper are treated as ~0. The `.fdc_cache.json` stores the
   whole panel per food; a food is only accepted if it carries both energy (kcal) and sat fat.
   A **confidence** score rewards a high ingredient-match fraction and a parsed serving count, and
   is **slashed if a high-fat ingredient (oil/butter/cheese/nuts/bacon…) went unmatched** — because
   that's exactly when sat fat would be under-counted.
3. **Calibrate** against recipes that already have real numbers: it prints a table of
   `confidence ≥ X → % of estimates within ±10%` and picks the lowest X meeting the 90% target.
4. **Enrich** only the missing recipes at/above that X. Output is `data/recipes_enriched.json`:
   ```json
   { "confidence_threshold": 0.xx, "count": N,
     "recipes": [ { "id","name",
                    "cal","protein","fat","carbs","sugar","fiber","sodium","satfat",
                    "source":"estimated","method":"usda-fdc","confidence":0.xx,
                    "match_frac":0.xx,"servings":N,"estimated_at":"YYYY-MM-DD" } ] }
   ```
   (In the 2026-08-21 run no recipe cleared the bar, so this file was not written.)

## Datasets (`datasets/`)
Full-run exports, all eight macros per serving. Only sat fat and calories have RecipeKeeper ground
truth, so only those carry `_real`/`_ratio` accuracy columns.
- `backtest_dataset_macros.csv` — 1,200 recipes that already have real numbers: estimated vs. real,
  with `satfat_ratio`/`cal_ratio` (est ÷ real). This is the accuracy evidence.
- `missing_estimates_macros.csv` — the 2,233 recipes missing nutrition: raw estimates + confidence
  (what the tool *would* fill). Estimate-only, no ground truth.
- `cached_foods_macros.csv` — 6,685 USDA foods resolved during the run, full per-100 g panel
  (6,343 matched, 342 unmatched). Doubles as a lookup-quality audit — scan for per-100 g values that
  look wrong for the ingredient (the main error source is first-match food selection).

## Integration
- Commit `data/recipes_enriched.json` to the **ChefClaude repo**. Chef Claude pulls and merges it
  each session, keeping `source:"estimated"` **separate** from source-verified nutrition.
- Estimated values are used **conservatively** in planning (upper-bound sat fat; verified preferred),
  and never override a real value.
- Re-run when the source database grows (new cookbook imports). Caching (`.fdc_cache.json`) keeps
  repeat runs fast and within FDC's rate limit (~1,000 req/hour on a free key).

## Honesty guarantees baked in
- Never guesses when it can't parse: unmatched ingredients lower confidence rather than being faked.
- Won't write values that don't clear the measured 90%/±10% bar.
- Tags everything it does write, so nothing is mistaken for source-verified data.

## Optional upgrade
Swap the built-in regex name-cleaner for the `ingredient-parser-nlp` PyPI package for better
ingredient-name extraction (then re-run the backtest — the calibration will re-measure accuracy).
