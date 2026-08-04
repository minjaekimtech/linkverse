import { readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { Plugin } from "vite";

const ENDPOINT = "/glimmer-scout/__local-test-overlay.json";
const SELECTED_PRODUCT_ID = "x5";
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const outputDir = path.join(repoRoot, "local_test_output");

type JsonRecord = Record<string, any>;

async function latestFile(prefix: string): Promise<string> {
  const names = (await readdir(outputDir)).filter(
    (name) => name.startsWith(prefix) && name.endsWith(".json"),
  );
  if (names.length === 0) throw new Error(`No ${prefix}*.json local test output found`);

  const entries = await Promise.all(
    names.map(async (name) => ({ name, mtimeMs: (await stat(path.join(outputDir, name))).mtimeMs })),
  );
  entries.sort((a, b) => b.mtimeMs - a.mtimeMs);
  return path.join(outputDir, entries[0].name);
}

async function readJson(filePath: string): Promise<JsonRecord> {
  return JSON.parse(await readFile(filePath, "utf8")) as JsonRecord;
}

function requireString(value: unknown, label: string): string {
  if (typeof value !== "string" || value.length === 0) throw new Error(`${label} is missing`);
  return value;
}

function marketForCountry(country: unknown): string {
  const code = typeof country === "string" ? country.toUpperCase() : "";
  if (code === "KR") return "korea";
  if (code === "JP") return "japan";
  if (["CN", "HK", "MO", "TW"].includes(code)) return "greater_china";
  if (["US", "CA", "GB", "DE", "FR", "IT", "ES", "NL", "AU", "NZ"].includes(code)) {
    return "north_america_europe";
  }
  return code ? "other" : "unknown";
}

function localCreator(channelData: JsonRecord, potentialData: JsonRecord, resonanceData: JsonRecord) {
  const channels = channelData.channels;
  if (!Array.isArray(channels) || channels.length !== 1) {
    throw new Error("Channel output must contain exactly one channel");
  }
  const channel = channels[0] as JsonRecord;
  const channelId = requireString(channel.channel_id, "channel channel_id");
  const potentialChannelId = requireString(potentialData.channel_id, "potential channel_id");
  const resonanceChannelId = requireString(resonanceData.channel_id, "resonance channel_id");
  if (channelId !== potentialChannelId || channelId !== resonanceChannelId) {
    throw new Error("Local test channel IDs do not match");
  }
  if (potentialData.method !== "heuristic_local_test" || potentialData.production_comparable !== false) {
    throw new Error("Potential output is not an isolated local test");
  }
  if (resonanceData.method !== "metadata_proxy_local_test" || resonanceData.production_comparable !== false) {
    throw new Error("Resonance output is not an isolated local test");
  }

  const product = resonanceData.products?.[SELECTED_PRODUCT_ID] as JsonRecord | undefined;
  if (!product || typeof product.test_resonance_r !== "number") {
    throw new Error(`Resonance output has no ${SELECTED_PRODUCT_ID} score`);
  }
  if (typeof potentialData.potential_p !== "number") throw new Error("Potential score is missing");

  const videos = Array.isArray(channel.videos) ? (channel.videos as JsonRecord[]) : [];
  const recentVideos = videos
    .slice()
    .sort((a, b) => String(b.published_at).localeCompare(String(a.published_at)));
  const thumbnails = recentVideos
    .map((video) => video.thumbnail_url)
    .filter((url): url is string => typeof url === "string" && url.length > 0)
    .slice(0, 5);

  const P = Math.round(potentialData.potential_p * 10) / 10;
  const R = Math.round(product.test_resonance_r * 10) / 10;
  const C = Math.round(Math.sqrt(Math.max(P, 0) * Math.max(R, 0)) * 10) / 10;
  const contributions = Array.isArray(product.dimension_contributions)
    ? product.dimension_contributions.map((entry: JsonRecord) => ({
        dim: String(entry.dimension),
        value: typeof entry.value === "number" ? entry.value : 0,
      }))
    : [];

  return {
    id: channelId,
    title: requireString(channel.title, "channel title"),
    url: `https://www.youtube.com/channel/${channelId}`,
    subs: typeof channel.subscriber_count === "number" ? channel.subscriber_count : 0,
    market: marketForCountry(channel.country),
    sport: "Local metadata test",
    thumb: thumbnails[0] ?? null,
    P,
    R,
    C,
    product: typeof product.product_name === "string" ? product.product_name : "Insta360 X5",
    reason: "Local heuristic Potential and metadata-proxy Resonance preview. Not production comparable.",
    price: { min: null, max: null, basis: "Local test only — no production pricing estimate." },
    hasScript: false,
    scripts: [],
    risk: {
      flagged: false,
      keywords: [],
      conclusion: "Local test only — production risk review was not run.",
    },
    contributions,
    vision: null,
    velocity: [],
    thumbnails,
    localTest: {
      method: "metadata_proxy_local_test",
      potentialMethod: "heuristic_local_test",
      productionComparable: false,
      selectedProductId: SELECTED_PRODUCT_ID,
    },
  };
}

async function buildOverlay() {
  const [channelPath, potentialPath, resonancePath] = await Promise.all([
    latestFile("channel_"),
    latestFile("potential_"),
    latestFile("resonance_"),
  ]);
  const [channel, potential, resonance] = await Promise.all([
    readJson(channelPath),
    readJson(potentialPath),
    readJson(resonancePath),
  ]);
  return {
    selectedProductId: SELECTED_PRODUCT_ID,
    creator: localCreator(channel, potential, resonance),
  };
}

export function localTestOverlay(): Plugin {
  return {
    name: "local-test-overlay",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        if (req.method !== "GET" || req.url !== ENDPOINT) {
          next();
          return;
        }
        try {
          const overlay = await buildOverlay();
          res.statusCode = 200;
          res.setHeader("Content-Type", "application/json; charset=utf-8");
          res.setHeader("Cache-Control", "no-store");
          res.end(JSON.stringify(overlay));
        } catch (error) {
          res.statusCode = 404;
          res.setHeader("Content-Type", "application/json; charset=utf-8");
          res.end(JSON.stringify({ error: error instanceof Error ? error.message : "Overlay unavailable" }));
        }
      });
    },
  };
}
