# Chef Claude — Weekly Meal Tracker (Option 1: automated plumbing, no per-use cost)

A private phone web app to view a two-week meal plan, check off meals as eaten, send
"next week" requests, and publish new menus — **with no AI at runtime and no
per-use cost**. Chef Claude still plans each week with the user in chat; the app just
removes the manual pasting and manual git commits.

## Files
```
index.html            <- the app (single file; data is also inlined as an offline fallback)
manifest.webmanifest  <- PWA manifest -> "Add to Home Screen" installable on each device
sw.js                 <- service worker: offline app shell; never caches /api; always-fresh menu
icons/                <- app icons (192/512/apple-touch/favicon) — chef's toque on brand orange
data/meals.json       <- the live menu the app fetches at runtime (published menus land here)
data/requests.json    <- rolling log of requests sent from the app (newest first)
data/state.json       <- shared "eaten" checkmarks, synced across your devices
api/_github.js        <- shared helper: reads/writes repo files via the GitHub Contents API
api/requests.js       <- POST /api/requests  -> appends to data/requests.json
api/publish.js        <- POST /api/publish   -> validates + writes data/meals.json
api/state.js          <- GET/POST /api/state -> reads/merges data/state.json (checkmark sync)
```

## Cross-device sync (checkmarks)
Marking a meal eaten on one device shows up on the others within a few seconds. The app reads
state *live through `/api/state`* (not the redeployed static file), so there's no wait for a
redeploy. Writes are debounced and merged server-side (per-key, with a sha-conflict retry), and
the whole thing degrades to per-device localStorage when offline or before the PIN is set.

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

## One-time setup (Claude Code can do this)
1. GitHub token: create a fine-grained personal access token scoped to THIS repo only,
   with Contents: Read and write.
2. Vercel env vars (Project -> Settings -> Environment Variables):
   - `GITHUB_TOKEN`  = the token above
   - `GITHUB_REPO`   = `owner/repo`
   - `GITHUB_BRANCH` = `main` (optional; defaults to main)
   - `PUBLISH_SECRET`= a PIN you choose. Enter it once in the app under the gear icon so
     only you can send/publish.
3. Redeploy. Open the app -> gear -> enter the PIN.
4. Let Chef Claude read requests without pasting: if the repo is public, share this raw
   URL once and Chef Claude fetches it each planning session:
   `https://raw.githubusercontent.com/<owner>/<repo>/<branch>/data/requests.json`
   (it holds only vegetables/proteins/notes — nothing sensitive). If the repo is private,
   add a tiny public GET read route, or just tell Chef Claude the picks in chat.

## Security notes
- Both endpoints require the `x-publish-secret` header to match `PUBLISH_SECRET`, so a
  public site can't be spammed or have menus published by anyone but you.
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

## Optional next touches
- PWA: add `manifest.json` (theme #D24400, icons) + a small service worker for
  Add-to-Home-Screen and offline use.
- A "pending requests" view (GET data/requests.json) so you can see what's queued.
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
      "desserts": [ { "name","satfat","cal","time","note" } ] }
    // ... Week 2 ...
  ]
}
```
