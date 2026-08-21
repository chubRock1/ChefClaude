# Chef Claude — Weekly Meal Tracker

A private phone web app to view a two-week meal plan, check off meals as eaten, rate them,
flag ones to swap or carry forward, send "next week" requests, and publish new menus —
**with no AI at runtime and no per-use cost**. Chef Claude still plans each week with the
user in chat; the app just removes the manual pasting and manual git commits.

- **Live app:** https://chef-claude-red-beta.vercel.app  (install via Safari → Add to Home Screen)
- **Repo:** https://github.com/chubRock1/ChefClaude (public) · hosted on Vercel (auto-deploys on push to `main`)
- **Installable PWA** (offline app shell + home-screen icon) and **cross-device sync** for everything you tap.

## Files
```
index.html            <- the app (single file; data is also inlined as an offline fallback)
manifest.webmanifest  <- PWA manifest -> "Add to Home Screen" installable on each device
sw.js                 <- service worker: offline app shell; never caches /api; always-fresh menu
icons/                <- app icons (192/512/apple-touch/favicon) — chef's toque on brand orange
data/meals.json       <- the live menu the app fetches at runtime (published menus land here)
data/requests.json    <- rolling log of requests sent from the app (newest first)
data/state.json       <- synced state: { eaten, planned, week, ratings, swaps, carry, eatenLog } across devices
api/_github.js        <- shared helper: reads/writes repo files via the GitHub Contents API
api/requests.js       <- POST /api/requests  -> appends to data/requests.json
api/publish.js        <- POST /api/publish   -> validates + writes data/meals.json
api/state.js          <- GET/POST /api/state -> reads/merges data/state.json (eaten, ratings, swaps, carry)
tools/                <- offline build tools (run locally, not part of the app runtime)
  enrich_nutrition.py <- estimates missing sat-fat + calories via USDA FoodData Central
  requirements.txt    <- python deps for the tool
  README.md           <- full run instructions for the enrichment tool
```

## Tools: nutrition enrichment (`tools/enrich_nutrition.py`)

An **offline** build tool (never runs in the app, no runtime cost) that fills in per-serving
**saturated fat + calories** for recipes missing them, using the free
[USDA FoodData Central](https://fdc.nal.usda.gov/api-key-signup.html) API. It's honest by design:
it **backtests** against recipes that already have real numbers, **calibrates** the confidence
level at which ≥90% of estimates land within ±10%, and **enriches only** the missing recipes at or
above that bar. If nothing clears it, it writes nothing. Every value it writes is tagged
`"source":"estimated"` so it's never confused with source-verified nutrition, and Chef Claude plans
with it conservatively (upper-bound sat fat, verified values preferred).

**Inputs you supply:** a free `USDA_API_KEY` (your credential — set it yourself) and the
RecipeKeeper `recipes.html` export(s) to point `--input` at. Both stay local — the API cache
(`tools/.fdc_cache.json`) and raw exports (`tools/recipes_src/`) are gitignored.

```bash
cd tools
pip install -r requirements.txt
export USDA_API_KEY=your_key_here          # PowerShell: $env:USDA_API_KEY="your_key_here"

# See the accuracy table only (no writes):
python enrich_nutrition.py --input "recipes_src/**/recipes.html" --mode backtest

# Calibrate, then write estimates that clear the bar:
python enrich_nutrition.py --input "recipes_src/**/recipes.html" \
    --out ../data/recipes_enriched.json --mode both
```

Commit the resulting `data/recipes_enriched.json` so Chef Claude merges it each planning session.
See [tools/README.md](tools/README.md) for flags and the full write-up.

## Views: by day / by course
A header toggle switches between **By day** (each day's breakfast/lunch/dinner together) and
**By course** (all 7 breakfasts, then all lunches, then all dinners — each row labeled with its day).
Handy when you mix and match — e.g. one day's breakfast with another day's lunch. Desserts and the
Extra options section show in both views. The choice is remembered per device.

## Planned vs. Eaten (two ticks per row)
Every meal row has **two ticks** on the left, labeled **Plan** and **Eaten**. **Plan** flags a meal
as chosen for the week and highlights the whole row green (with a "planned" badge) — so you can
assemble a day from meals anywhere in the menu (great with the By-course view) and see at a glance
what's on deck, even when the dish isn't from that calendar day. **Eaten** (tap the row, or its
check) marks it actually eaten (strike-through). They're independent: a meal can be planned, eaten,
or both. Planned flags are `menuSig`-scoped like eaten, so publishing a new menu clears them
automatically. Both sync across devices. When at least one meal is planned, the footer shows a green
**Planned: N meals · X g sat · Y kcal** line — the running sat-fat + calorie total of everything
you've picked, so a day assembled across the menu shows its custom totals at a glance.

## Per-meal actions (copy / rate / carry / swap)
Every meal row also has: a **📋 copy** button (copies the exact recipe name for pasting into a recipe
app), **👍 / 👎** rating (👍 = keep in rotation, 👎 = don't repeat — keyed by recipe *name* so it
applies wherever that dish appears), **⏭ next wk** (carry this meal into the upcoming week — for a
dish you didn't get to but still want), and **⇄ swap** (flag this slot to be replaced). Meals,
desserts, and extras can all be checked off as eaten, and the footer "X / N eaten this week" counter
includes all of them (N = 21 day meals + desserts + extras). Desserts and extras get plan + copy +
rating + carry (no swap). All syncs across devices.

## Extra options (spare picks)
Each week includes a required `extras` block — one spare breakfast, lunch, dinner, and dessert —
shown in an "Extra options" card at the end. These are extra choices to pull from if a planned meal
doesn't happen. Chef Claude curates them at planning time (see the required note in **Weekly planning
brief**). The app still renders fine if a week lacks extras, but every menu Chef Claude publishes
should include them.

## Eaten history (what you actually ate)
Every meal you check off is logged by recipe name + week + date in `state.json`'s `eatenLog`
(persistent, survives new menus — capped at the most recent 200). Chef Claude reads it at planning
time: meals that were served but **never** eaten are candidates to bring back into rotation sooner,
and recently-eaten dishes get spaced out.

## Checkmarks reset automatically on a new menu
Eaten checkmarks are scoped to the specific published menu (keyed by a signature of its meal
names). Publishing a genuinely new menu starts everyone with a clean slate — no manual reset
needed. Re-publishing the exact same menu keeps your progress. The "Reset week" button still
exists for clearing the current week's checkmarks mid-week if you want to re-track.

**Swap and carry flags also clear on a new menu** (they applied to the old menu's slots), via a
`clearFlags` call the app makes when it first loads a changed menu. Ratings persist (they're
name-based preferences, not tied to one menu).

## Cross-device sync (eaten, ratings, swaps, carry)
Anything you tap — checking a meal eaten, a 👍/👎 rating, a ⇄ swap or ⏭ carry flag — shows up on
your other devices within a few seconds. The app reads state *live through `/api/state`* (not the
redeployed static file), so there's no wait for a redeploy. Eaten writes are debounced; ratings /
swaps / carry post immediately and adopt the server's merged result; all merges are per-key with a
sha-conflict retry. Everything degrades to per-device localStorage when offline or before the PIN
is set.

**Sync is PIN-gated, and a header pill shows its state.** A device only pushes/pulls when its PIN
is entered (`syncOn = !!pin`). The header shows **✓ Synced** when it is and **⚠ Not syncing** when
it isn't (tap the pill to open Settings). This matters because iOS evicts a PWA's `localStorage`
after ~7 idle days, which silently wipes the stored PIN and turns sync off — the pill makes that
visible instead of leaving you wondering why checkmarks stopped crossing over. The app also calls
`navigator.storage.persist()` to reduce that eviction (installed-to-home-screen PWAs benefit most).
When a PIN is (re)entered, the device **merges its local-only checkmarks/ratings/flags up** to the
server before adopting server state, so marks made while it wasn't syncing aren't lost (additive —
it never deletes another device's marks). **If a device stops syncing, re-enter its PIN in Settings.**

**Chef Claude reads these at planning time** from `data/state.json` — ratings tell it what to keep
or avoid, swaps tell it which current-menu slots to replace, carry tells it which meals to pull into
the upcoming week, and eatenLog tells it what was actually eaten (so un-eaten dishes return sooner).
Read it via the GitHub Contents API (fresh, not the CDN-cached raw URL) — see **Weekly planning
brief** below for the exact fetch.

state.json shape: `{ eaten:{ "<menuSig>|<week>|<day>|<slot>":true }, planned:{ same key shape as eaten }, week, ratings:{ "<recipe name>":{rating,at} }, swaps:{ "<weekLabel>||<day>||<slot>":{name,at} }, carry:{ same key shape } }`

## Install on each device (iPhone/iPad)
Open the Vercel URL in Safari -> Share -> **Add to Home Screen**. Launches full-screen with the
chef-hat icon. Do this once per device, then open Settings (gear) and enter your PIN so that
device can send requests, publish, and sync checkmarks.
Deploy layout: put `index.html` and `data/` at the repo root (or the Vercel static root)
and `api/` at the repo root. Vercel serves `index.html` statically and turns each file in
`api/` into a serverless function automatically — no config needed.

## How the loop works (no cost, no pasting, no commits)
1. Send requests: the app's Requests sheet POSTs your picks to `/api/requests`, which
   commits them to `data/requests.json`. Chef Claude reads that file (via the GitHub Contents
   API — see **Weekly planning brief**) when you next plan together — so you never paste requests.
2. Plan: Chef Claude builds the week with you in chat and hands you a `meals.json`.
3. Publish: paste it into Settings -> Publish a new week. `/api/publish` validates every
   day is <= 10 g sat fat, then commits `data/meals.json`. Vercel auto-redeploys and the
   app fetches the new data — no manual commit, no file editing.

The app degrades gracefully: with no backend deployed it still runs as a static site
(Send falls back to copy-to-clipboard, Publish shows "backend not reachable"). So it works
the moment you push it, and gains the automation once the env vars below are set.

## Weekly planning brief (what Chef Claude reads)
To start a session: **"Chef Claude, pull our updates from the links and let's plan next week."**

**Read via the GitHub Contents API, NOT the raw URL.** `raw.githubusercontent.com` is behind a CDN
that caches each file ~5 min, so it often serves a stale copy at planning time. The Contents API is
not on that CDN and always returns the latest commit. Fetch each file with header
`Accept: application/vnd.github.raw` (returns the file content directly), e.g.:
```
curl -s -H "Accept: application/vnd.github.raw" \
  "https://api.github.com/repos/chubRock1/ChefClaude/contents/data/state.json?ref=main"
```
(If a tool can't set headers, use the raw URL with a cache-buster query, e.g.
`.../data/state.json?nocache=<random>` — but the API endpoint above is the reliable one.)

Read these three files each planning session:
1. Requests — `…/contents/data/requests.json?ref=main`
   (vegetables / proteins / notes the user tapped in ✎ Requests).
2. State — `…/contents/data/state.json?ref=main`
   - `ratings` (keyed by recipe NAME): "up" = keep in rotation, "down" = don't repeat.
   - `swaps` (key "WeekLabel||Day||slot"): replace this current-menu slot.
   - `carry` (same key shape): the user missed this — include it in the upcoming week.
   - `eatenLog` (keyed by recipe NAME → {at, week}): what was actually eaten. Meals that were
     served but are NOT in the log are candidates to bring back sooner; recently-eaten ones get spaced out.
3. Current menu (context) — `…/contents/data/meals.json?ref=main`

(base path `https://api.github.com/repos/chubRock1/ChefClaude`)

Then build the two weeks, apply the standing rules (see **Nutrition integrity** below), and hand over
a `meals.json` to publish.

**REQUIRED — every published menu must include an `extras` block for EACH week:** one spare
`breakfast`, one `lunch`, one `dinner`, and one `dessert` (four items per week), each with the same
fields as a normal meal (`name, satfat, cal, time, note, leftover`). These are the app's "Extra
options" spare picks. Do not omit them. They are not counted toward any day's ≤10 g sat-fat total,
but each individual extra should still be a sensible low-sat-fat choice and follow every standing
rule (no shellfish/lamb, fish never as a leftover, verbatim RecipeKeeper names, etc.).

## One-time setup (done — kept here for reference / redeploys)
Vercel env vars already configured for this project (Project -> Settings -> Environment Variables):
   - `GITHUB_TOKEN`  = fine-grained PAT scoped to `chubRock1/ChefClaude`, Contents: Read and write
   - `GITHUB_REPO`   = `chubRock1/ChefClaude`
   - `GITHUB_BRANCH` = `main`
   - `PUBLISH_SECRET`= the PIN entered once per device under the gear icon (gates send/publish/sync)

Chef Claude reads requests without pasting each planning session via the GitHub Contents API
(fresh, avoids the raw CDN cache): `GET https://api.github.com/repos/chubRock1/ChefClaude/contents/data/requests.json?ref=main`
with header `Accept: application/vnd.github.raw` (holds only vegetables/proteins/notes — nothing sensitive).

## Security notes
- All three endpoints (`/api/requests`, `/api/publish`, `/api/state`) require the
  `x-publish-secret` header to match `PUBLISH_SECRET`, so a public site can't be spammed,
  have menus published, or have state written by anyone but you.
- The GitHub token lives ONLY in Vercel env vars (server-side), never in `index.html`.
- No API keys are in the client. No AI is called anywhere, so nothing is metered — this
  stays on free tiers for a personal app.

## Nutrition integrity (please preserve)
- Recipe names are verbatim from the RecipeKeeper database (for lookup) — don't rename.
- Sat fat / calories are per person, per serving, from that database.
- `api/publish.js` enforces <= 10 g sat fat per day and rejects anything over. Other
  standing rules are applied by Chef Claude at planning time: no shellfish, no lamb, pork
  OK (incl. bacon/pancetta), fish never as a leftover, only 2 non-consecutive make-ahead
  lunches per week, and beef at most once a month.
- **Every published menu MUST include an `extras` block per week** (a spare breakfast, lunch,
  dinner, and dessert). This is a menu-construction requirement, not optional. See the
  "Weekly planning brief" section above for details.

## Done since the original package
- Header **↻ refresh** button: re-fetches the menu + synced state in place (no reopen) — shows a
  spinner, then "New week loaded ✓" if the menu changed or "You're up to date" if not.
- PWA: `manifest.webmanifest` + `sw.js` + generated icons — installable, offline app shell.
- Cross-device sync of eaten / ratings / swaps / carry via `data/state.json` + `api/state.js`.
- Per-meal 📋 copy, 👍/👎 rating, ⏭ carry-to-next-week, ⇄ swap; desserts checkable + copy/rate/carry.
- Eaten checkmarks scoped to the published menu (auto-reset on a new menu); swap/carry flags auto-clear on a new menu.
- iOS zoom fix (16px inputs so the Publish sheet doesn't zoom/hide its Close button).

## Optional next touches
- A "pending requests" / "flagged items" view (GET data/state.json) so you can review 👎 / ⇄ / ⏭ before planning.
- A weekly sat-fat chart, a snack-budget tally (13 g minus meals eaten), a "today" scroll.

## meals.json shape
```
{
  "title": "...", "chef": "Chef Claude",
  "targets": { "satfatMealsMax": 10, "satfatDailyCeiling": 13 },
  "weeks": [
    { "label": "Week 1 · Summer",
      "days": [
        { "day": "Monday", "weekend": false,
          "meals": {
            "breakfast": { "name","satfat","cal","time","note","leftover" },
            "lunch": { ... }, "dinner": { ... } } }
        // ... 7 days ...
      ],
      "desserts": [ { "name","satfat","cal","time","note" } ],
      "extras": {                          // REQUIRED every menu: one spare pick per course
        "breakfast": { "name","satfat","cal","time","note","leftover" },
        "lunch": { ... }, "dinner": { ... }, "dessert": { ... } } }
    // ... Week 2 ...
  ]
}
```
Note: `extras` are not subject to the ≤10 g/day rule (they aren't a day); `api/publish.js` only
validates the 7 days. The eaten-checkmark signature (`computeSig`) is based on day-meal names only,
so adding/adjusting extras does not trigger a checkmark reset.
