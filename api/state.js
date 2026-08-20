// /api/state — cross-device sync for eaten checkmarks, meal ratings, and swap flags.
//   GET  /api/state  -> { eaten:{key:true}, week:0, ratings:{name:{rating,at}}, swaps:{key:{name,at}} }
//   POST /api/state  -> merges a change into data/state.json and returns the new state. Fields:
//        { set:{key:true}, unset:[key] }   eaten checkmarks (key = "week|day|slot")
//        { week:0 }                          selected week
//        { rate:{ name, rating } }           rating: "up" | "down" | null/"" to clear (keyed by recipe name)
//        { swap:{ key, name, on } }          flag a menu slot to be swapped out (key = "weekLabel||day||slot")
//        { carry:{ key, name, on } }         flag a meal to carry into the upcoming week (same key shape)
//        { clearFlags:true }                 wipe all swap + carry flags (done when a new menu is published)
// Reads/writes go straight to GitHub, so a change on one device shows on another within seconds
// (the app reads through this route, not the redeployed static file). PIN-gated like the others.
// Chef Claude reads ratings + swaps from the raw state.json URL at planning time.

const { readJson, writeJson } = require("./_github");

const PATH = "data/state.json";

function normalize(j) {
  const s = j && typeof j === "object" ? j : {};
  return {
    eaten: (s.eaten && typeof s.eaten === "object") ? s.eaten : {},
    week: Number.isInteger(s.week) ? s.week : 0,
    ratings: (s.ratings && typeof s.ratings === "object") ? s.ratings : {},
    swaps: (s.swaps && typeof s.swaps === "object") ? s.swaps : {},
    carry: (s.carry && typeof s.carry === "object") ? s.carry : {},
  };
}

module.exports = async (req, res) => {
  if ((req.headers["x-publish-secret"] || "") !== process.env.PUBLISH_SECRET) {
    return res.status(401).json({ error: "unauthorized" });
  }

  try {
    if (req.method === "GET") {
      const cur = await readJson(PATH);
      return res.status(200).json(normalize(cur.json));
    }

    if (req.method === "POST") {
      let body = req.body;
      if (typeof body === "string") { try { body = JSON.parse(body); } catch (e) { return res.status(400).json({ error: "bad json" }); } }
      const set = (body && body.set && typeof body.set === "object") ? body.set : {};
      const unset = Array.isArray(body && body.unset) ? body.unset : [];
      const week = Number.isInteger(body && body.week) ? body.week : null;
      const rate = (body && body.rate && typeof body.rate === "object") ? body.rate : null;
      const swap = (body && body.swap && typeof body.swap === "object") ? body.swap : null;
      const carry = (body && body.carry && typeof body.carry === "object") ? body.carry : null;
      const clearFlags = !!(body && body.clearFlags);

      // Read-modify-write with one retry if another device committed in between (sha conflict).
      for (let attempt = 0; attempt < 2; attempt++) {
        const cur = await readJson(PATH);
        const state = normalize(cur.json);
        for (const k of Object.keys(set)) { if (set[k]) state.eaten[k] = true; else delete state.eaten[k]; }
        for (const k of unset) delete state.eaten[k];
        if (week !== null) state.week = week;
        if (rate && typeof rate.name === "string" && rate.name) {
          if (rate.rating === "up" || rate.rating === "down") state.ratings[rate.name] = { rating: rate.rating, at: new Date().toISOString() };
          else delete state.ratings[rate.name];
        }
        if (swap && typeof swap.key === "string" && swap.key) {
          if (swap.on) state.swaps[swap.key] = { name: String(swap.name || ""), at: new Date().toISOString() };
          else delete state.swaps[swap.key];
        }
        if (carry && typeof carry.key === "string" && carry.key) {
          if (carry.on) state.carry[carry.key] = { name: String(carry.name || ""), at: new Date().toISOString() };
          else delete state.carry[carry.key];
        }
        if (clearFlags) { state.swaps = {}; state.carry = {}; } // a new menu was published — flags no longer apply
        try {
          await writeJson(PATH, state, cur.sha, "Sync meal state");
          return res.status(200).json(state);
        } catch (e) {
          if (attempt === 0 && /\b409\b/.test(String(e && e.message))) continue; // conflict: re-read and retry
          throw e;
        }
      }
    }

    return res.status(405).json({ error: "GET or POST only" });
  } catch (e) {
    return res.status(500).json({ error: String((e && e.message) || e) });
  }
};
