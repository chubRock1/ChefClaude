#!/usr/bin/env python3
"""
Chef Claude -- web nutrition verification: batch picker.

Loads the recipe database + the two progress-tracking files, excludes
recipes already confirmed or already checked-and-rejected, ranks the rest by
"distinctiveness" (site-attributed / unusual titles first, since those have a
much higher search hit rate), and prints the next N as JSON for Claude Code
to work through.

Usage:
    python get_next_batch.py \
        --database chef_claude_recipe_database.json \
        --verified data/nutrition_web_verified.json \
        --checked  data/nutrition_web_checked_no_match.json \
        --n 20
"""
import argparse
import json


def distinctiveness(name: str) -> int:
    """Higher score = more likely to have a findable, verifiable exact source."""
    score = 0
    if any(m in name for m in ("—", " - ", "|", "'", '"')):
        score += 3
    words = name.split()
    score += len(words)
    generic = {"salad", "soup", "sauce", "chicken", "beans", "rice", "stew",
               "bowl", "muffins", "bread", "cake", "pie"}
    if any(w[0].isupper() and w.lower() not in generic and len(w) > 3
           for w in words[1:]):
        score += 1
    return score


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--database", required=True,
                     help="path to chef_claude_recipe_database.json")
    ap.add_argument("--verified", required=True,
                     help="path to data/nutrition_web_verified.json")
    ap.add_argument("--checked", required=True,
                     help="path to data/nutrition_web_checked_no_match.json")
    ap.add_argument("--n", type=int, default=20, help="batch size")
    args = ap.parse_args()

    db = json.load(open(args.database))["recipes"]
    missing = [r for r in db if r.get("satfat") is None and r.get("ings")]

    def load_names(path, key="name"):
        try:
            data = json.load(open(path))
            return {r[key] for r in data.get("recipes", [])}
        except FileNotFoundError:
            return set()

    done = load_names(args.verified) | load_names(args.checked)
    candidates = [r for r in missing if r["name"] not in done]

    ranked = sorted(candidates, key=lambda r: -distinctiveness(r["name"]))
    batch = ranked[: args.n]

    print(json.dumps({
        "total_missing": len(missing),
        "already_processed": len(done),
        "remaining_after_done": len(candidates),
        "batch_size": len(batch),
        "batch": [
            {"id": r["id"], "name": r["name"], "yield": r.get("yield"),
             "ings": r["ings"]}
            for r in batch
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
