import { useEffect, useState } from "react";
import type { DemoOverlay } from "./demo/demoTypes";

export type Script = {
  platform: string;
  hook: string;
  beats: string[];
  voiceover: string[];
  caption: string;
  cta: string;
};

export type RiskReview = {
  flagged: boolean;
  keywords: string[];
  conclusion: string;
};

export type Contribution = { dim: string; value: number };

export type Vision = {
  sportTypes: string[];
  perspective: string;
  pace: string;
  stabilization: number; // 0-1
  extremity: number; // 0-1
  gear: number; // 0-1
  evidence: string;
};

export type VelocityPoint = {
  date: string;
  relative: number | null;
  seasonAdjusted: number | null;
};

export type Creator = {
  id: string;
  title: string;
  url: string;
  subs: number;
  market: string;
  sport: string;
  thumb: string | null;
  P: number; // Potential — about to break out?
  R: number; // Resonance — fits the product?
  C: number; // Combined
  product: string;
  reason: string;
  price: { min: number | null; max: number | null; basis: string };
  hasScript: boolean;
  scripts: Script[];
  risk: RiskReview;
  contributions: Contribution[];
  vision: Vision | null;
  velocity: VelocityPoint[];
  thumbnails: string[];
  localTest?: {
    kind?: "camera_local" | "keyword_demo";
    method: "metadata_proxy_local_test";
    potentialMethod: "heuristic_local_test";
    productionComparable: false;
    selectedProductId: "x5" | "demo";
  };
};

export type Dataset = {
  meta: {
    name: string;
    channel_count: number;
    analyzed_count: number;
    finding: { k: number; model_pct: number; baseline_pct: number; lift: number };
    products: Record<string, string>;
  };
  creators: Creator[];
};

type LocalTestOverlay = {
  selectedProductId: "x5";
  creator: Creator;
};

async function loadLocalOverlay(): Promise<LocalTestOverlay | null> {
  if (!import.meta.env.DEV) return null;
  try {
    const response = await fetch(`${import.meta.env.BASE_URL}__local-test-overlay.json`, {
      cache: "no-store",
    });
    if (!response.ok) return null;
    return (await response.json()) as LocalTestOverlay;
  } catch {
    return null;
  }
}

async function loadKeywordDemo(): Promise<DemoOverlay | null> {
  if (!import.meta.env.DEV) return null;
  try {
    const response = await fetch(`${import.meta.env.BASE_URL}__keyword-demo-overlay.json`, { cache: "no-store" });
    return response.ok ? await response.json() as DemoOverlay : null;
  } catch { return null; }
}

export function useData() {
  const [data, setData] = useState<Dataset | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [keywordDemo, setKeywordDemo] = useState<DemoOverlay | null>(null);

  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}linkverse.json`)
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status}`);
        return r.json();
      })
      .then(async (dataset: Dataset) => {
        const [overlay, demo] = await Promise.all([loadLocalOverlay(), loadKeywordDemo()]);
        setKeywordDemo(demo);
        if (!overlay) return dataset;
        return {
          ...dataset,
          creators: [
            ...dataset.creators.filter((creator) => creator.id !== overlay.creator.id),
            overlay.creator,
          ],
        };
      })
      .then(setData)
      .catch((e) => setError(String(e)));
  }, []);

  return { data, error, keywordDemo };
}
