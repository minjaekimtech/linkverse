import type { DemoDomain, DemoMarket, DemoState, DemoView } from "./demoTypes";

const views = new Set<DemoView>(["product", "audience", "market", "scope"]);
const markets = new Set<DemoMarket>(["KR", "US", "JP", "GLOBAL"]);
const sunscreen = ["sun cream", "sunscreen", "sunblock", "spf", "선크림", "썬크림", "자외선 차단제"];
const soccer = ["soccer equipment", "soccer gear", "football boots", "축구 용품", "축구화", "풋살화", "축구공", "축구 유니폼", "골키퍼 장갑"];

export function inferDomain(input: string): DemoDomain | null {
  const value = input.trim().toLocaleLowerCase();
  if (sunscreen.some((term) => value.includes(term))) return "sunscreen";
  if (soccer.some((term) => value.includes(term))) return "soccer_equipment";
  return null;
}

export function parseDemoState(search: string): DemoState {
  const q = new URLSearchParams(search);
  const domain = q.get("domain"); const market = q.get("market"); const view = q.get("view");
  return { view: views.has(view as DemoView) ? view as DemoView : "product",
    domain: domain === "sunscreen" || domain === "soccer_equipment" ? domain : undefined,
    productInput: (q.get("product") || "").slice(0, 120), audienceInput: (q.get("audience") || "").slice(0, 120),
    market: markets.has(market as DemoMarket) ? market as DemoMarket : undefined };
}

export function demoUrl(state: DemoState): string {
  const q = new URLSearchParams({ demo: "keyword", view: state.view });
  if (state.domain) q.set("domain", state.domain); if (state.productInput) q.set("product", state.productInput);
  if (state.audienceInput) q.set("audience", state.audienceInput); if (state.market) q.set("market", state.market);
  return `?${q}`;
}
