import type { LayerInfo, Lens } from "./api";

/** Colour stops of the colormaps the tile server uses (rio-tiler), sampled at 0, 25, 50, 75 and 100%. */
export const COLORMAPS: Record<string, string[]> = {
  viridis: ["#440154", "#3a528b", "#20908c", "#5ec961", "#fde724"],
  magma: ["#000003", "#50127b", "#b63679", "#fb8861", "#fbfcbf"],
  greys_r: ["#000000", "#525252", "#969696", "#d9d9d9", "#ffffff"],
  rdbu: ["#67001f", "#e58368", "#f6f6f6", "#68aacf", "#053061"],
  ylorrd: ["#ffffcc", "#fed875", "#fc8c3b", "#e2191c", "#800026"],
  ylgnbu: ["#ffffd9", "#c6e8b4", "#40b5c3", "#215ea8", "#081d58"],
  cividis: ["#00224d", "#434e6b", "#7c7b78", "#baac6c", "#fde737"],
};

export const gradient = (name: string, dir = "to right") => `linear-gradient(${dir}, ${(COLORMAPS[name] ?? COLORMAPS.viridis).join(", ")})`;

/** Colour of a value on a layer's colormap (for 3D vertex colours and chart dots). */
export function colorAt(name: string, t: number): [number, number, number] {
  const stops = (COLORMAPS[name] ?? COLORMAPS.viridis).map((h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)));
  const x = Math.min(1, Math.max(0, t)) * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(x));
  const f = x - i;
  return [0, 1, 2].map((k) => (stops[i][k] + (stops[i + 1][k] - stops[i][k]) * f) / 255) as [number, number, number];
}

/** Lens names, one accent colour each (distinct in hue and lightness on the dark background), and a one-line pitch. */
export const LENSES: Record<Lens, { label: string; color: string; pitch: string }> = {
  wildfire: { label: "Wildfire", color: "#f97316", pitch: "Burned land, mapped through smoke and cloud" },
  earthquake: { label: "Earthquake", color: "#e11d48", pitch: "Ground shift and likely building damage" },
  volcano: { label: "Volcano", color: "#dc2626", pitch: "New lava and swelling ground" },
  subsidence: { label: "Subsidence", color: "#a78bfa", pitch: "Where the ground is sinking, and how fast" },
  wetland: { label: "Wetland", color: "#22d3ee", pitch: "Open water through the flood season" },
  farming: { label: "Farming", color: "#84cc16", pitch: "Crop types told apart before harvest" },
};

export const KIND_LABEL: Record<LayerInfo["kind"], string> = {
  answer: "Answers to questions",
  prediction: "AI Model",
  baseline: "Baseline",
  physics: "Radar measurement",
  context: "Context",
};

export function fmt(v: number | null | undefined, unit = "") {
  if (v === null || v === undefined || Number.isNaN(v)) return "n/a";
  const a = Math.abs(v);
  const s = a >= 1000 ? v.toLocaleString("en-GB", { maximumFractionDigits: 0 }) : a >= 10 ? v.toFixed(1) : a >= 1 ? v.toFixed(2) : v.toFixed(3);
  return unit ? `${s} ${unit}` : s;
}

export const ha = (v: number) => (v >= 100 ? `${Math.round(v).toLocaleString("en-GB")} ha` : `${v.toFixed(1)} ha`);

/** Which layer a Study page opens on: the AI Model on a Showcase Site, else the most telling physics layer. */
export function defaultLayer(layers: LayerInfo[], kind: "showcase" | "analysis"): LayerInfo {
  const order = kind === "showcase" ? ["prediction", "baseline"] : ["baseline"];
  for (const k of order) {
    // A forecast (a quantity, not classes) is not the headline: the measured layer is (the subsidence
    // forecast does not beat its straight-line Baseline; see its Model card).
    const l = layers.find((x) => x.kind === k && (k !== "prediction" || x.colormap === "categorical"));
    if (l) return l;
  }
  for (const id of ["cum_disp_cm", "coherence_loss", "rgb", "hv_db", "coherence"]) {
    const l = layers.find((x) => x.id === id);
    if (l) return l;
  }
  return layers[0];
}

/** The series a Study page charts first. */
export function defaultSeries(variables: string[], lens: Lens | null) {
  const pref = lens === "earthquake" || lens === "subsidence" || lens === "volcano" ? ["cum_disp_cm", "hv_db"] : ["hv_db", "cum_disp_cm"];
  return pref.find((v) => variables.includes(v)) ?? variables[0];
}

/** Pipeline notes often repeat per Pass ("pair A>B: ..."); keep one example of each kind, with a count. */
export function groupNotes(notes: string[] = []): string[] {
  const groups = new Map<string, string[]>();
  for (const n of notes) {
    const key = n.replace(/\d{4}-\d{2}-\d{2}/g, "#").replace(/\d+(\.\d+)?/g, "0");
    groups.set(key, [...(groups.get(key) ?? []), n]);
  }
  return [...groups.values()].map((g) => (g.length > 1 ? `${g[0]} (and ${g.length - 1} more Pass${g.length > 2 ? "es" : ""} like this)` : g[0]));
}
