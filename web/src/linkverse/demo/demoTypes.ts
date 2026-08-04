export type DemoDomain = "sunscreen" | "soccer_equipment";
export type DemoMarket = "KR" | "US" | "JP" | "GLOBAL";
export type DemoView = "product" | "audience" | "market" | "scope";
export type DemoState = { view: DemoView; domain?: DemoDomain; productInput: string; audienceInput: string; market?: DemoMarket };
export type DemoVideo = { title?: string; description?: string; tags?: string[] };
export type DemoCandidate = { channel_id: string; title: string; description?: string; country?: string; contentLanguage?: string;
  subscriber_count?: number; P: number; productRelevance: number; matchedKeywords?: string[]; videos?: DemoVideo[] };
export type DemoCache = { domain: DemoDomain; creators: DemoCandidate[] };
export type DemoOverlay = { categories: Partial<Record<DemoDomain, DemoCache | null>> };
