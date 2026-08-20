// POST /api/requests  — capture a "next week" request from the app.
// No AI, no per-use cost: it just appends the request to data/requests.json in your repo.
// Chef Claude reads that file's raw URL each planning session, so you never paste.

const { readJson, writeJson } = require("./_github");

module.exports = async (req, res) => {
  if (req.method !== "POST") return res.status(405).json({ error: "POST only" });

  // Simple shared-secret gate so only you (not random visitors to a public site) can write.
  if ((req.headers["x-publish-secret"] || "") !== process.env.PUBLISH_SECRET) {
    return res.status(401).json({ error: "unauthorized" });
  }

  let body = req.body;
  if (typeof body === "string") {
    try { body = JSON.parse(body); } catch (e) { return res.status(400).json({ error: "bad json" }); }
  }

  const entry = {
    receivedAt: new Date().toISOString(),
    target: body.target === "week2" ? "update Week 2" : "next new week",
    veg: Array.isArray(body.veg) ? body.veg : [],
    protein: Array.isArray(body.protein) ? body.protein : [],
    notes: (body.notes || "").toString().slice(0, 1000),
  };

  try {
    const cur = await readJson("data/requests.json");
    const list = Array.isArray(cur.json) ? cur.json : [];
    list.unshift(entry);                       // newest first
    await writeJson("data/requests.json", list.slice(0, 50), cur.sha, "Add meal request");
    return res.status(200).json({ ok: true });
  } catch (e) {
    return res.status(500).json({ error: String(e && e.message || e) });
  }
};
