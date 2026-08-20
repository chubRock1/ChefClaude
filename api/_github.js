// Shared GitHub helper (CommonJS, no dependencies).
// Uses the repo itself as a tiny datastore via the GitHub Contents API.
// Requires env vars: GITHUB_TOKEN, GITHUB_REPO ("owner/repo"), optional GITHUB_BRANCH (default "main").
// `fetch` and `Buffer` are built into the Vercel Node runtime (Node 18+), so there is nothing to install.

const REPO = process.env.GITHUB_REPO;                 // e.g. "yourname/chef-claude-meal-app"
const BRANCH = process.env.GITHUB_BRANCH || "main";
const TOKEN = process.env.GITHUB_TOKEN;
const API = "https://api.github.com";

function headers() {
  return {
    Authorization: `Bearer ${TOKEN}`,
    Accept: "application/vnd.github+json",
    "User-Agent": "chef-claude-meal-app",
    "Content-Type": "application/json",
  };
}

// Read a JSON file from the repo. Returns { sha, json } (sha is null if the file doesn't exist yet).
async function readJson(path) {
  const r = await fetch(`${API}/repos/${REPO}/contents/${encodeURIComponent(path)}?ref=${BRANCH}`, { headers: headers() });
  if (r.status === 404) return { sha: null, json: null };
  if (!r.ok) throw new Error(`GitHub read ${r.status}: ${await r.text()}`);
  const d = await r.json();
  const text = Buffer.from(d.content, "base64").toString("utf8");
  return { sha: d.sha, json: JSON.parse(text) };
}

// Create or update a text file in the repo (a commit → Vercel auto-redeploys).
async function writeText(path, text, sha, message) {
  const body = { message, content: Buffer.from(text, "utf8").toString("base64"), branch: BRANCH };
  if (sha) body.sha = sha; // required when updating an existing file
  const r = await fetch(`${API}/repos/${REPO}/contents/${encodeURIComponent(path)}`, {
    method: "PUT", headers: headers(), body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`GitHub write ${r.status}: ${await r.text()}`);
  return r.json();
}

async function writeJson(path, obj, sha, message) {
  return writeText(path, JSON.stringify(obj, null, 2), sha, message);
}

module.exports = { readJson, writeText, writeJson };
