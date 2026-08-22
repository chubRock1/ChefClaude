#!/usr/bin/env python3
"""
Chef Claude — nutrition enrichment (calibrated, honest-by-design)
=================================================================
Fills in per-serving saturated fat + calories for RecipeKeeper recipes that are
missing them, using the free USDA FoodData Central (FDC) API for real per-ingredient
nutrition.

The core idea: we DON'T claim 90% accuracy — we MEASURE it.
  1) BACKTEST: run the estimator on recipes that already have real numbers.
  2) CALIBRATE: find the confidence threshold at which >=90% of estimates land
     within +/-10% of the true value (your bar).
  3) ENRICH: fill ONLY the missing recipes whose confidence >= that threshold.
If no threshold reaches the target, it writes nothing and says so.

Every filled recipe is tagged  "source": "estimated"  with its confidence, so it is
never confused with source-verified data, and Chef Claude plans with it conservatively
(upper-bound sat fat).

Usage
-----
  export USDA_API_KEY=xxxxxxxx            # free: https://fdc.nal.usda.gov/api-key-signup.html
  pip install -r requirements.txt
  python enrich_nutrition.py \
      --input "recipes_src/**/recipes.html" \
      --out   data/recipes_enriched.json \
      --mode  both            # both = backtest+calibrate, then enrich

Input = one or more RecipeKeeper HTML exports (the same `recipes.html` files from the
uploads). Point --input at them (glob ok). Output = data/recipes_enriched.json for the repo.
"""

import argparse, glob, json, os, re, sys, time, hashlib
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("Missing deps. Run:  pip install -r requirements.txt")

FDC_SEARCH = "https://api.nal.usda.gov/fdc/v1/foods/search"
ENERGY_ID, SATFAT_ID = 1008, 1258          # USDA nutrient IDs (per 100 g for Foundation/SR)
# Full macro panel we pull from each USDA food (per 100 g). Ordered; drives cache + CSV columns.
NUTRIENTS = {"cal": 1008, "protein": 1003, "fat": 1004, "carbs": 1005,
             "sugar": 2000, "fiber": 1079, "sodium": 1093, "satfat": 1258}
ID2KEY = {v: k for k, v in NUTRIENTS.items()}
MACRO_KEYS = list(NUTRIENTS)               # cal, protein, fat, carbs, sugar, fiber, sodium, satfat
PREFERRED_TYPES = ["Foundation", "SR Legacy"]  # generic, per-100g edible portion

# ---------------------------------------------------------------- unit / portion maps
UNI = {'¼':.25,'½':.5,'¾':.75,'⅓':1/3,'⅔':2/3,'⅛':.125,'⅜':.375,'⅝':.625,'⅞':.875,'⅕':.2,'⅖':.4,'⅗':.6,'⅙':1/6}
UNIT_G = {  # unit -> grams (volume treated as ml≈g; refined for fats below)
 "tablespoon":15,"tablespoons":15,"tbsp":15,"tbs":15,"teaspoon":5,"teaspoons":5,"tsp":5,
 "cup":240,"cups":240,"ounce":28.35,"ounces":28.35,"oz":28.35,"pound":454,"pounds":454,"lb":454,"lbs":454,
 "gram":1,"grams":1,"g":1,"kg":1000,"kilogram":1000,"ml":1,"milliliter":1,"milliliters":1,
 "liter":1000,"liters":1000,"l":1000,"pinch":0.3,"quart":960,"pint":480,"stick":113}
# grams-per-cup overrides by ingredient class (keyword -> g/cup)
GPCUP = {"flour":125,"sugar":200,"brown sugar":220,"rice":185,"oat":90,"breadcrumb":108,"cornmeal":160,
 "honey":340,"broth":240,"stock":240,"milk":240,"water":240,"yogurt":245,"cream":238,"chickpea":164,
 "bean":177,"lentil":192,"couscous":173,"bulgur":140,"quinoa":170,"barley":200,"farro":200,"pasta":100,
 "orzo":200,"cheese":100,"parmesan":100,"olive":135,"tomato":180,"spinach":30,"arugula":20,"corn":150,
 "pea":145,"nut":120,"almond":143,"raisin":145,"oil":218,"butter":227}
# count-based item weights (keyword -> grams each)
ITEM = {"egg":50,"onion":110,"shallot":40,"clove":3,"garlic":3,"tomato":123,"potato":170,"sweet potato":130,
 "lemon":58,"lime":67,"orange":140,"bell pepper":120,"pepper":120,"zucchini":196,"eggplant":250,"carrot":61,
 "cucumber":200,"banana":118,"apple":182,"peach":150,"nectarine":142,"pear":178,"avocado":150,
 "chicken breast":174,"chicken thigh":100,"scallion":15,"celery":40,"fennel":234,"leek":89,"jalapeno":14,
 "can":400,"package":280,"slice":25,"strip":8,"fillet":170}
FAT_REFINE = {"oil":(15,"tbsp",13.6),"butter":(15,"tbsp",14.2)}  # tbsp weight refinement for fats

# ingredients whose fat we must not under-count; if UNMATCHED, confidence is slashed
HIGH_FAT_HINT = re.compile(r"\b(oil|butter|ghee|cream|cheese|parmesan|feta|mozzarella|cheddar|ricotta|"
                           r"bacon|pancetta|sausage|chorizo|coconut|nut|nuts|tahini|mayonnaise|lard|"
                           r"almond|walnut|pistachio|pecan|cashew|pine nut|peanut)\b", re.I)
# lines we treat as ~zero and never send to the API
ZERO = re.compile(r"^\s*(salt|kosher salt|sea salt|pepper|black pepper|water|ice|"
                  r"cooking spray|nonstick spray)\b", re.I)
SKIP_DESC = re.compile(r"\b(chopped|minced|diced|sliced|divided|fresh|freshly|ground|to taste|for (serving|"
                       r"garnish|drizzling|frying)|as needed|optional|peeled|seeded|halved|quartered|"
                       r"trimmed|rinsed|drained|cooked|uncooked|large|medium|small|ripe|about|approximately|"
                       r"plus more|room temperature|softened|melted|beaten|packed|thawed)\b", re.I)

WEIGHT_U = {"ounce":28.35,"ounces":28.35,"oz":28.35,"pound":454,"pounds":454,"lb":454,"lbs":454,
            "gram":1,"grams":1,"g":1,"kg":1000,"kilogram":1000,"kilograms":1000,"kg.":1000}

def parse_qty(s):
    s = " " + s.strip() + " "
    for u, v in UNI.items(): s = s.replace(u, f" {v} ")
    s = re.sub(r'(\d+)\s+(\d+)\s*/\s*(\d+)', lambda m: str(int(m.group(1))+int(m.group(2))/int(m.group(3))), s)
    s = re.sub(r'(\d+)\s*/\s*(\d+)', lambda m: str(int(m.group(1))/int(m.group(2))), s)
    s = re.sub(r'(\d+)\s+(0?\.\d+)\b', lambda m: str(int(m.group(1))+float(m.group(2))), s)  # "1 0.5" (from 1½) -> 1.5
    m = re.match(r'\s*(\d+(?:\.\d+)?)(?:\s*(?:to|-|–|or)\s*(\d+(?:\.\d+)?))?', s.strip())
    if not m: return None
    a = float(m.group(1)); b = float(m.group(2)) if m.group(2) else None
    return (a + b) / 2 if b else a

def extract_paren_weight(line):
    """A weight stated in parentheses, e.g. '(14.5 oz)' or '(about 1 1/2 pounds)', is authoritative."""
    for pm in re.findall(r'\(([^)]*)\)', line):
        low = pm.lower()
        um = re.search(r'\b(' + '|'.join(sorted(WEIGHT_U, key=len, reverse=True)) + r')\b', low)
        if not um: continue
        q = parse_qty(re.sub(r'^(about|approx\.?|approximately|around|roughly)\s+', '', low))
        if q is not None:
            return q * WEIGHT_U[um.group(1)]
    return None

def clean_name(line):
    """Reduce an ingredient line to a search-friendly food name."""
    s = line.lower()
    s = re.sub(r'\([^)]*\)', ' ', s)                 # drop parentheticals
    s = s.split(',')[0]                              # keep head before first comma
    s = re.sub(r'\d+(?:\.\d+)?', ' ', s)             # numbers
    s = re.sub(r'|'.join(UNI.keys()), ' ', s)
    unit_re = r'\b(' + '|'.join(sorted(UNIT_G, key=len, reverse=True)) + r')\b'
    s = re.sub(unit_re, ' ', s)
    s = SKIP_DESC.sub(' ', s)
    s = re.sub(r'[^a-z\- ]', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()

def grams_for(line):
    pw = extract_paren_weight(line)          # a stated weight in ( ) wins
    if pw: return pw
    base = re.sub(r'\([^)]*\)', ' ', line)   # otherwise drop parentheticals so stray units don't mislead
    low = base.lower()
    qty = parse_qty(base)
    um = re.search(r'\b(' + '|'.join(sorted(UNIT_G, key=len, reverse=True)) + r')\b', low)
    if qty is not None and um:
        u = um.group(1); g = qty * UNIT_G[u]
        if u in ("cup", "cups"):
            for k, v in GPCUP.items():
                if k in low: g = qty * v; break
        elif u in ("tablespoon","tablespoons","tbsp","tbs"):
            for k,(_,_,w) in FAT_REFINE.items():
                if k in low: g = qty * w; break
        return g
    if qty is not None:
        for k, w in sorted(ITEM.items(), key=lambda x: -len(x[0])):
            if k in low: return qty * w
        return qty * 100   # bare count, unknown item -> assume ~100 g
    return None

def yield_servings(y):
    m = re.search(r'(\d+)', y or '')
    return int(m.group(1)) if m else None

# ------------------------------------------------------------------- USDA lookup (cached)
class FDC:
    def __init__(self, api_key, cache_path, max_per_hour=950):
        self.key = api_key
        self.cache_path = cache_path
        self.cache = {}
        if Path(cache_path).exists():
            try: self.cache = json.load(open(cache_path))
            except Exception: self.cache = {}
        # Backfill migration: drop legacy 2-field [kcal, satfat] entries so they are
        # re-fetched into the full macro panel. Keep dict panels and None (no-match).
        self.cache = {k: v for k, v in self.cache.items()
                      if v is None or isinstance(v, dict)}
        self.calls = 0
        # Proactive throttle: keep real API calls under the free-key ~1000/hour limit.
        self.min_interval = 3600.0 / max_per_hour if max_per_hour else 0.0
        self._last_call = 0.0

    def save(self):
        json.dump(self.cache, open(self.cache_path, "w"))

    def _throttle(self):
        if self.min_interval <= 0: return
        wait = self.min_interval - (time.time() - self._last_call)
        if wait > 0: time.sleep(wait)
        self._last_call = time.time()

    def lookup(self, food_name):
        """Return a per-100 g macro dict (keys = MACRO_KEYS) or None. Cached by cleaned name."""
        key = food_name.strip().lower()
        if not key: return None
        if key in self.cache:
            return self.cache[key] or None
        params = {"api_key": self.key, "query": key, "pageSize": 5,
                  "dataType": PREFERRED_TYPES}
        for attempt in range(4):
            try:
                self._throttle()
                r = requests.get(FDC_SEARCH, params=params, timeout=30)
                self.calls += 1
                if r.status_code == 429:
                    time.sleep(2 ** attempt * 3); continue
                r.raise_for_status()
                foods = r.json().get("foods", [])
                val = self._extract(foods)
                self.cache[key] = val if val else None
                if self.calls % 50 == 0: self.save()
                return val
            except requests.RequestException:
                time.sleep(2 ** attempt)
        return None

    @staticmethod
    def _extract(foods):
        """First food carrying both energy (kcal) and sat fat wins; return full macro panel per 100 g."""
        for f in foods:
            vals = {}
            for n in f.get("foodNutrients", []):
                nid = n.get("nutrientId") or n.get("nutrient", {}).get("id")
                v = n.get("value", n.get("amount"))
                if nid not in ID2KEY or v is None: continue
                key = ID2KEY[nid]
                if key == "cal" and n.get("unitName", "kcal").lower() not in ("kcal", ""): continue
                vals[key] = float(v)
            if "cal" in vals and "satfat" in vals:
                return {k: vals.get(k, 0.0) for k in MACRO_KEYS}
        return None

# ------------------------------------------------------------------- estimate one recipe
def estimate(recipe, fdc):
    n_ing = matched = 0
    totals = {k: 0.0 for k in MACRO_KEYS}
    unmatched_highfat = False
    for line in recipe["ings"]:
        t = line.strip()
        if not t or t.endswith(":"): continue
        n_ing += 1
        if ZERO.match(t):                 # salt/water/etc → ~0, counts as matched
            matched += 1; continue
        g = grams_for(t)
        name = clean_name(t)
        vals = fdc.lookup(name) if name else None
        if vals is None or g is None or g <= 0:
            if HIGH_FAT_HINT.search(t): unmatched_highfat = True
            continue
        for k in MACRO_KEYS:
            totals[k] += g * vals[k] / 100.0
        matched += 1
    serv = yield_servings(recipe.get("yield"))
    serv_ok = serv is not None and serv >= 1
    if not serv_ok: serv = 4
    match_frac = matched / n_ing if n_ing else 0.0
    # confidence: reward high match fraction & parsed servings; punish an unmatched high-fat item hard
    conf = match_frac
    if not serv_ok: conf *= 0.75
    if unmatched_highfat: conf *= 0.25
    per = {k: round(totals[k] / serv, 1) for k in MACRO_KEYS}
    per["cal"] = round(totals["cal"] / serv)   # kcal as whole number
    return {**per,
            "confidence": round(conf, 3), "match_frac": round(match_frac, 3),
            "n_ing": n_ing, "servings": serv, "serv_parsed": serv_ok,
            "unmatched_highfat": unmatched_highfat}

# ------------------------------------------------------------------- RecipeKeeper parse
def parse_recipes(paths):
    out = []
    for p in paths:
        soup = BeautifulSoup(open(p, encoding="utf-8").read(), "lxml")
        for div in soup.find_all("div", class_="recipe-details"):
            def prop(name):
                el = div.find(attrs={"itemprop": name})
                if not el: return None
                return el.get("content") if el.name == "meta" else el.get_text(" ", strip=True)
            def num(x):
                if x is None: return None
                m = re.search(r'-?\d+\.?\d*', x.replace(",", "")); return float(m.group()) if m else None
            ing_div = div.find(class_="recipe-ingredients")
            ings = [pp.get_text(" ", strip=True) for pp in ing_div.find_all("p")] if ing_div else []
            out.append({"id": prop("recipeId"), "name": prop("name"), "yield": prop("recipeYield"),
                        "satfat": num(prop("recipeNutSaturatedFat")), "cal": num(prop("recipeNutCalories")),
                        "ings": ings})
    # de-dupe by name (first wins)
    seen, uniq = set(), []
    for r in out:
        if r["name"] in seen: continue
        seen.add(r["name"]); uniq.append(r)
    return uniq

# ------------------------------------------------------------------- backtest / calibrate
def within(true, est, tol):
    if true in (0, None): return abs(est) <= 0.5
    return abs(est - true) / true <= tol

def calibrate(recipes, fdc, tol, target, min_samples, max_bt):
    known = [r for r in recipes if r["satfat"] is not None and r["cal"] not in (None, 0) and r["ings"]]
    import random; random.seed(7)
    if len(known) > max_bt: known = random.sample(known, max_bt)
    print(f"[backtest] estimating {len(known)} recipes that already have real numbers…")
    rows = []
    for i, r in enumerate(known):
        e = estimate(r, fdc)
        rows.append((e["confidence"], r["satfat"], e["satfat"], r["cal"], e["cal"]))
        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(known)}  (api calls so far: {fdc.calls})"); fdc.save()
    fdc.save()
    print(f"\n[calibration]  tolerance ±{int(tol*100)}%   target hit-rate {int(target*100)}%")
    print(f"  {'conf≥':>6} {'n':>6} {'satfat±tol':>11} {'cal±tol':>9}")
    chosen = None
    for thr in [x/100 for x in range(50, 100, 2)]:
        sub = [x for x in rows if x[0] >= thr]
        if len(sub) < min_samples: continue
        sf_hit = sum(1 for _, ts, es, _, _ in sub if within(ts, es, tol)) / len(sub)
        cal_hit = sum(1 for _, _, _, tc, ec in sub if within(tc, ec, tol)) / len(sub)
        flag = ""
        if sf_hit >= target and chosen is None:
            chosen = thr; flag = "  <== meets target"
        print(f"  {thr:>6.2f} {len(sub):>6} {sf_hit*100:>10.1f}% {cal_hit*100:>8.1f}%{flag}")
    return chosen

# ------------------------------------------------------------------- main
def main():
    # Windows consoles default to cp1252, which can't encode ≥ / ± in our tables.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="glob to RecipeKeeper recipes.html file(s)")
    ap.add_argument("--out", default="data/recipes_enriched.json")
    ap.add_argument("--cache", default=".fdc_cache.json")
    ap.add_argument("--mode", choices=["backtest", "enrich", "both"], default="both")
    ap.add_argument("--tolerance", type=float, default=0.10)   # ±10%  == "90% accurate"
    ap.add_argument("--target", type=float, default=0.90)      # want ≥90% of estimates within tol
    ap.add_argument("--min-samples", type=int, default=40)
    ap.add_argument("--max-backtest", type=int, default=1200)
    ap.add_argument("--threshold", type=float, default=None,
                    help="skip calibration and use this confidence threshold directly")
    ap.add_argument("--max-per-hour", type=int, default=950,
                    help="proactive USDA API rate cap (free key allows ~1000/hour)")
    args = ap.parse_args()

    key = os.environ.get("USDA_API_KEY")
    if not key:
        sys.exit("Set USDA_API_KEY (free: https://fdc.nal.usda.gov/api-key-signup.html)")

    paths = [p for pat in args.input.split(",") for p in glob.glob(pat, recursive=True)]
    if not paths: sys.exit(f"No files matched: {args.input}")
    print(f"Reading {len(paths)} export(s)…")
    recipes = parse_recipes(paths)
    missing = [r for r in recipes if (r["satfat"] is None or r["cal"] is None) and r["ings"]]
    print(f"{len(recipes)} unique recipes | {len(recipes)-len(missing)} with nutrition | {len(missing)} missing")

    fdc = FDC(key, args.cache, max_per_hour=args.max_per_hour)

    threshold = args.threshold
    if args.mode in ("backtest", "both") and threshold is None:
        threshold = calibrate(recipes, fdc, args.tolerance, args.target, args.min_samples, args.max_backtest)
        if threshold is None:
            print("\nNo confidence threshold reached the target hit-rate. "
                  "Per the accuracy rule, nothing will be written. "
                  "Grow the verified pool via cookbook imports instead.")
            fdc.save()
            return
        print(f"\nCalibrated confidence threshold: {threshold:.2f} "
              f"(estimates at/above this are ≥{int(args.target*100)}% likely within ±{int(args.tolerance*100)}%).")

    if args.mode == "backtest":
        fdc.save(); return

    # ---- enrich the missing recipes at/above the calibrated threshold ----
    print(f"\n[enrich] scoring {len(missing)} missing recipes…")
    enriched = []
    for i, r in enumerate(missing):
        e = estimate(r, fdc)
        if e["confidence"] >= threshold:
            enriched.append({
                "id": r["id"], "name": r["name"],
                **{k: e[k] for k in MACRO_KEYS},   # cal, protein, fat, carbs, sugar, fiber, sodium, satfat
                "source": "estimated", "method": "usda-fdc",
                "confidence": e["confidence"], "match_frac": e["match_frac"],
                "servings": e["servings"], "estimated_at": time.strftime("%Y-%m-%d")})
        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(missing)}  kept {len(enriched)}  (api calls: {fdc.calls})"); fdc.save()
    fdc.save()

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    payload = {"generated": time.strftime("%Y-%m-%d"), "method": "usda-fdc",
               "tolerance": args.tolerance, "target_hitrate": args.target,
               "confidence_threshold": threshold, "count": len(enriched),
               "note": "Estimated per-serving values. Use conservatively; prefer source-verified. "
                       "satfat is an estimate — Chef Claude plans with an upper-bound margin.",
               "recipes": enriched}
    json.dump(payload, open(args.out, "w"), indent=2)
    print(f"\nWrote {len(enriched)} estimated recipes → {args.out}")
    print(f"(of {len(missing)} missing; the rest stay unfilled by design.)  USDA API calls: {fdc.calls}")

if __name__ == "__main__":
    main()
