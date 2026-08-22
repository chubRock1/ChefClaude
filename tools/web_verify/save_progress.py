#!/usr/bin/env python3
"""
Chef Claude -- web nutrition verification: progress saver.

Merges a batch of new results into the two persistent tracking files,
de-duplicating by recipe id (confirmed) / name (checked-no-match), and
writes them back out. Never overwrites existing entries -- new results with
the same id/name are ignored (first result wins; fix by hand if a correction
is genuinely needed).

Usage: import and call from a small driver script, or adapt inline --
this file intentionally does not hardcode Claude's search results, since
those come from Claude Code's own reasoning during the session, not from
this script.

Example:
    from save_progress import merge_confirmed, merge_checked

    new_confirmed = [
        {"id": "...", "name": "...", "cal": 230, "satfat": 3.5,
         "totalfat": 6.6, "source": "web-verified", "method": "web-search",
         "source_url": "https://...", "match_confidence": "...",
         "verified_at": "2026-08-22"},
        ...
    ]
    merge_confirmed(new_confirmed, "data/nutrition_web_verified.json")

    new_checked = [
        {"name": "...", "reason": "..."},
        ...
    ]
    merge_checked(new_checked, "data/nutrition_web_checked_no_match.json")
"""
import json
import os
from datetime import date


def _load(path):
    if os.path.exists(path):
        return json.load(open(path))
    return None


def merge_confirmed(new_entries, path):
    existing = _load(path)
    if existing is None:
        existing = {
            "generated": str(date.today()),
            "method": "web-search verification against published nutrition labels",
            "note": ("Each entry's ingredient list was compared verbatim against "
                      "the source recipe before accepting its published nutrition. "
                      "Only exact matches included."),
            "count": 0,
            "recipes": [],
        }
    seen_ids = {r["id"] for r in existing["recipes"]}
    added = 0
    for entry in new_entries:
        if entry["id"] in seen_ids:
            continue
        existing["recipes"].append(entry)
        seen_ids.add(entry["id"])
        added += 1
    existing["count"] = len(existing["recipes"])
    existing["last_updated"] = str(date.today())
    json.dump(existing, open(path, "w"), indent=2)
    print(f"[confirmed] added {added} new, {existing['count']} total -> {path}")


def merge_checked(new_entries, path):
    existing = _load(path)
    if existing is None:
        existing = {
            "generated": str(date.today()),
            "note": ("Recipes already searched and rejected -- skip re-searching "
                      "these in future batches unless new info becomes available."),
            "count": 0,
            "recipes": [],
        }
    seen_names = {r["name"] for r in existing["recipes"]}
    added = 0
    for entry in new_entries:
        if entry["name"] in seen_names:
            continue
        existing["recipes"].append(entry)
        seen_names.add(entry["name"])
        added += 1
    existing["count"] = len(existing["recipes"])
    existing["last_updated"] = str(date.today())
    json.dump(existing, open(path, "w"), indent=2)
    print(f"[checked-no-match] added {added} new, {existing['count']} total -> {path}")


if __name__ == "__main__":
    print(__doc__)
