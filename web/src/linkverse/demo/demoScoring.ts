import type { Creator } from "../useData";
import { audienceKeywords } from "./audienceRules.ts";
import type { DemoCandidate, DemoMarket } from "./demoTypes.ts";

export const DEMO_WEIGHTS = { product: 0.55, audience: 0.30, market: 0.15 } as const;
export const clampScore = (n: number) => Math.max(0, Math.min(100, n));
const text = (c: DemoCandidate) => [c.title, c.description, ...(c.videos || []).flatMap(v => [v.title, v.description, ...(v.tags || [])])].filter(Boolean).join(" ").toLocaleLowerCase();

export function audienceFit(candidate: DemoCandidate, audience: string): number {
  const words = audienceKeywords[audience] || audience.toLocaleLowerCase().split(/\s+/).filter(word => word.length > 2);
  if (!words.length) return 0;
  const all = text(candidate); const matched = words.filter(word => all.includes(word.toLocaleLowerCase())).length / words.length;
  const videos = candidate.videos || []; const videoRatio = videos.length ? videos.filter(v => words.some(word => [v.title, v.description, ...(v.tags || [])].join(" ").toLocaleLowerCase().includes(word.toLocaleLowerCase()))).length / videos.length : 0;
  return clampScore(100 * (0.6 * matched + 0.4 * videoRatio));
}
export function marketFit(candidate: DemoCandidate, market: DemoMarket): number {
  if (market === "GLOBAL") return 100;
  const country = candidate.country?.toUpperCase(); const lang = candidate.contentLanguage?.toLowerCase() || "";
  if (country === market) return 100;
  const languageMatch = (market === "KR" && lang.startsWith("ko")) || (market === "JP" && lang.startsWith("ja")) || (market === "US" && lang.startsWith("en"));
  if (!country && languageMatch) return 65; if (country && languageMatch) return 50; if (!country && !lang) return 25; return 0;
}
export function demoR(productRelevance: number, audience: number, market: number): number {
  return clampScore(DEMO_WEIGHTS.product * productRelevance + DEMO_WEIGHTS.audience * audience + DEMO_WEIGHTS.market * market);
}
export function toCreators(candidates: DemoCandidate[], audience: string, market: DemoMarket): Creator[] {
  return candidates.map(c => { const a = audienceFit(c, audience), m = marketFit(c, market), r = demoR(c.productRelevance, a, m);
    const P = clampScore(c.P); return { id: c.channel_id, title: c.title, url: `https://www.youtube.com/channel/${c.channel_id}`, subs: c.subscriber_count || 0,
      market: c.country || "unknown", sport: "Keyword demo", thumb: null, P: +P.toFixed(1), R: +r.toFixed(1), C: +Math.sqrt(P*r).toFixed(1), product: "Demo keyword match",
      reason: `Product ${c.productRelevance.toFixed(1)} · Audience ${a.toFixed(1)} · Market ${m.toFixed(1)}. Matched: ${(c.matchedKeywords || []).join(", ") || "metadata terms"}.`,
      price: {min:null,max:null,basis:"Demo only"}, hasScript:false, scripts:[], risk:{flagged:false,keywords:[],conclusion:"Demo only"}, contributions:[{dim:"productRelevance",value:+c.productRelevance.toFixed(1)},{dim:"audienceFit",value:+a.toFixed(1)},{dim:"marketFit",value:+m.toFixed(1)}], vision:null, velocity:[], thumbnails:[],
      localTest:{kind:"keyword_demo" as const,method:"metadata_proxy_local_test" as const,potentialMethod:"heuristic_local_test" as const,productionComparable:false as const,selectedProductId:"demo" as const} } }).sort((a,b)=>b.R-a.R || b.P-a.P || b.subs-a.subs);
}
