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
data/state.json       <- synced state: { eaten, week, ratings, swaps, carry, eatenLog } across devices
api/_github.js        <- shared helper: reads/writes repo files via the GitHub Contents API
api/requests.js       <- POST /api/requests  -> appends to data/requests.json
api/publish.js        <- POST /api/publish   -> validates + writes data/meals.json
api/state.js          <- GET/POST /api/state -> reads/merges data/state.json (eaten, ratings, swaps, carry)
```

## Views: by day / by course
A header toggle switches between **By day** (each day's breakfast/lunch/dinner together) and
**By course** (all 7 breakfasts, then all lunches, then all dinners — each row labeled with its day).
Handy when you mix and match — e.g. one day's breakfast with another day's lunch. Desserts and the
Extra options section show in both views. The choice is remembered per device.

## Per-meal actions (copy / rate / carry / swap)
Every meal row has: a **📋 copy** button (copies the exact recipe name for pasting into a recipe
app), **👍 / 👎** rating (👍 = keep in rotation, 👎 = don't repeat — keyed by recipe *name* so it
applies wherever that dish appears), **⏭ next wk** (carry this meal into the upcoming week — for a
dish you didn't get to but still want), and **⇄ swap** (flag this slot to be replaced). Meals,
desserts, and extras can all be checked off as eaten (dessert/extra checkmarks are tracked but kept
out of the "X / 21 meals" day-meal count). Desserts and extras get copy + rating + carry (no swap).
All syncs across devices.

## Extra options (spare picks)
Each week can include an `extras` block — one spare breakfast, lunch, dinner, and dessert — shown in
an "Extra options" card at the end. These are extra choices to pull from if a planned meal doesn't
happen. Chef Claude curates them at planning time.

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

**Chef Claude reads these at planning time** from the raw state file — ratings tell it what to keep
or avoid, swaps tell it which current-menu slots to replace, carry tells it which meals to pull into
the upcoming week, and eatenLog tells it what was actually eaten (so un-eaten dishes return sooner):
`https://raw.githubusercontent.com/chubRock1/ChefClaude/main/data/state.json`

state.json shape: `{ eaten:{ "<menuSig>|<week>|<day>|<slot>":true }, week, ratings:{ "<recipe name>":{rating,at} }, swaps:{ "<weekLabel>||<day>||<slot>":{name,at} }, carry:{ same key shape } }`

## Install on each device (iPhone/iPad)
Open the Vercel URL in Safari -> Share -> **Add to Home Screen**. Launches full-screen with the
chef-hat icon. Do this once per device, then open Settings (gear) and enter your PIN so that
device can send requests, publish, and sync checkmarks.
Deploy layout: put `index.html` and `data/` at the repo root (or the Vercel static root)
and `api/` at the repo root. Vercel serves `index.html` statically and turns each file in
`api/` into a serverless function automatically — no config needed.

## How the loop works (no cost, no pasting, no commits)
1. Send requests: the app's Requests sheet POSTs your picks to `/api/requests`, which
   commits them to `data/requests.json`. Chef Claude reads that file's raw URL when you
   next plan together — so you never paste requests.
2. Plan: Chef Claude builds the week with you in chat and hands you a `meals.json`.
3. Publish: paste it into Settings -> Publish a new week. `/api/publish` validates every
   day is <= 10 g sat fat, then commits `data/meals.json`. Vercel auto-redeploys and the
   app fetches the new data — no manual commit, no file editing.

The app degrades gracefully: with no backend deployed it still runs as a static site
(Send falls back to copy-to-clipboard, Publish shows "backend not reachable"). So it works
the moment you push it, and gains the automation once the env vars below are set.

## Weekly planning brief (what Chef Claude reads)
To start a session: **"Chef Claude, pull our updates from the links and let's plan next week."**

Read these raw files each planning session (GitHub caches them ~5 min):
1. Requests — `https://raw.githubusercontent.com/chubRock1/ChefClaude/main/data/requests.json`
   (vegetables / proteins / notes the user tapped in ✎ Requests).
2. State — `https://raw.githubusercontent.com/chubRock1/ChefClaude/main/data/state.json`
   - `ratings` (keyed by recipe NAME): "up" = keep in rotation, "down" = don't repeat.
   - `swaps` (key "WeekLabel||Day||slot"): replace this current-menu slot.
   - `carry` (same key shape): the user missed this — include it in the upcoming week.
   - `eatenLog` (keyed by recipe NAME → {at, week}): what was actually eaten. Meals that were
     served but are NOT in the log are candidates to bring back sooner; recently-eaten ones get spaced out.
3. Current menu (context) — `https://raw.githubusercontent.com/chubRock1/ChefClaude/main/data/meals.json`

Then build the two weeks and apply the standing rules (see **Nutrition integrity** below), fill each
week's `extras` (one spare breakfast/lunch/dinner/dessert), and hand over a `meals.json` to publish.

## One-time setup (done — kept here for reference / redeploys)
Vercel env vars already configured for this project (Project -> Settings -> Environment Variables):
   - `GITHUB_TOKEN`  = fine-grained PAT scoped to `chubRock1/ChefClaude`, Contents: Read and write
   - `GITHUB_REPO`   = `chubRock1/ChefClaude`
   - `GITHUB_BRANCH` = `main`
   - `PUBLISH_SECRET`= the PIN entered once per device under the gear icon (gates send/publish/sync)

Chef Claude reads requests without pasting from the public raw URL each planning session:
`https://raw.githubusercontent.com/chubRock1/ChefClaude/main/data/requests.json`
(holds only vegetables/proteins/notes — nothing sensitive).

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
      "extras": {                          // optional: one spare pick per course
        "breakfast": { "name","satfat","cal","time","note" },
        "lunch": { ... }, "dinner": { ... }, "dessert": { ... } } }
    // ... Week 2 ...
  ]
}
```
Note: `extras` are not subject to the ≤10 g/day rule (they aren't a day); `api/publish.js` only
validates the 7 days. The eaten-checkmark signature (`computeSig`) is based on day-meal names only,
so adding/adjusting extras does not trigger a checkmark reset.
