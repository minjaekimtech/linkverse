import { readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { Plugin } from "vite";

const endpoint = "/glimmer-scout/__keyword-demo-overlay.json";
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const cacheDir = path.join(repoRoot, "local_test_output", "demo_keyword_search");
const domains = ["sunscreen", "soccer_equipment"] as const;

async function latest(domain: string) {
  const names = (await readdir(cacheDir)).filter((name) => name.startsWith(`${domain}_`) && name.endsWith(".json"));
  const dated = await Promise.all(names.map(async (name) => ({ name, time: (await stat(path.join(cacheDir, name))).mtimeMs })));
  dated.sort((a, b) => b.time - a.time);
  if (!dated[0]) return null;
  const value = JSON.parse(await readFile(path.join(cacheDir, dated[0].name), "utf8"));
  if (value.domain !== domain || !Array.isArray(value.creators)) throw new Error("Invalid demo cache");
  return value;
}

export function keywordDemoOverlay(): Plugin {
  return {
    name: "keyword-demo-overlay",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        if (req.method !== "GET" || req.url !== endpoint) return next();
        try {
          const values = await Promise.all(domains.map((domain) => latest(domain).catch(() => null)));
          res.statusCode = 200;
          res.setHeader("Content-Type", "application/json; charset=utf-8");
          res.setHeader("Cache-Control", "no-store");
          res.end(JSON.stringify({ categories: Object.fromEntries(domains.map((domain, i) => [domain, values[i]])) }));
        } catch {
          res.statusCode = 200;
          res.end(JSON.stringify({ categories: {} }));
        }
      });
    },
  };
}
