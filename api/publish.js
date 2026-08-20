// POST /api/publish  — publish a new meals.json (the week Chef Claude planned with you).
// Writes data/meals.json to the repo, which makes Vercel auto-redeploy. No manual commit.
// Validates the core rule automatically: every day's three meals must total <= 10 g sat fat.

const { readJson, writeText } = require("./_github");

function validate(d) {
  if (!d || !Array.isArray(d.weeks) || !d.weeks.length) return "no weeks in data";
  for (const w of d.weeks) {
    if (!Array.isArray(w.days) || w.days.length !== 7) return `${w.label || "a week"} must have 7 days`;
    for (const day of w.days) {
      const m = day.meals || {};
      for (const slot of ["breakfast", "lunch", "dinner"]) {
        const meal = m[slot];
        if (!meal || typeof meal.satfat !== "number" || typeof meal.cal !== "number")
          return `missing ${slot} nutrition on ${w.label} ${day.day}`;
      }
      const sf = m.breakfast.satfat + m.lunch.satfat + m.dinner.satfat;
      if (sf > 10.001) return `${w.label} ${day.day} = ${sf.toFixed(1)} g sat fat (over the 10 g/day limit)`;
    }
  }
  return null;
}

module.exports = async (req, res) => {
  if (req.method !== "POST") return res.status(405).json({ error: "POST only" });
  if ((req.headers["x-publish-secret"] || "") !== process.env.PUBLISH_SECRET) {
    return res.status(401).json({ error: "unauthorized" });
  }

  let data = req.body;
  if (typeof data === "string") {
    try { data = JSON.parse(data); } catch (e) { return res.status(400).json({ error: "bad json" }); }
  }

  const err = validate(data);
  if (err) return res.status(400).json({ error: err });

  try {
    const cur = await readJson("data/meals.json");
    await writeText("data/meals.json", JSON.stringify(data, null, 2), cur.sha, "Publish new week(s) via app");
    return res.status(200).json({ ok: true });
  } catch (e) {
    return res.status(500).json({ error: String(e && e.message || e) });
  }
};
