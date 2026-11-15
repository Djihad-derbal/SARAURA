/** Base URL of the SARAURA API.
 *  - NEXT_PUBLIC_API_URL set to a full URL: used as is.
 *  - Opened on this machine (localhost / 127.0.0.1): the API directly on port 8000, as in development.
 *  - Opened from any other address (a public tunnel, another laptop): "/api" on that same address, which
 *    next.config.ts forwards to the API, so one public link serves both the website and the API. */
function resolveApi(): string {
  const env = (process.env.NEXT_PUBLIC_API_URL ?? "").trim();
  if (env && !env.startsWith("/")) return env;
  if (typeof window !== "undefined") {
    const host = window.location.hostname;
    if (env || (host !== "localhost" && host !== "127.0.0.1")) return window.location.origin + (env || "/api");
  }
  return "http://127.0.0.1:8000";
}
export const API = resolveApi();

export type Bbox = [number, number, number, number];

// ---------------------------------------------------------------- shared fetch helpers

async function fail(r: Response): Promise<never> {
  let detail = "";
  try {
    const d = (await r.json()).detail;
    detail = typeof d === "string" ? d : Array.isArray(d) ? d.map((x) => x.msg ?? "").join("; ") : "";
  } catch {}
  throw new Error(detail || `Request failed (${r.status})`);
}

export async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(API + path, { signal });
  if (!r.ok) await fail(r);
  return r.json();
}

export async function postJson<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const r = await fetch(API + path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal });
  if (!r.ok) await fail(r);
  return r.json();
}

// ---------------------------------------------------------------- dates

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function shortDate(iso: string) {
  const [, m, d] = iso.split("-").map(Number);
  return `${d} ${MONTHS[m - 1]}`;
}

export function longDate(iso: string) {
  const [y, m, d] = iso.split("-").map(Number);
  return `${d} ${MONTHS[m - 1]} ${y}`;
}

export function bboxOf(ring: [number, number][]): Bbox {
  const xs = ring.map((p) => p[0]);
  const ys = ring.map((p) => p[1]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

// ---------------------------------------------------------------- Study pages (Showcase Sites and Analyses)

export type Lens = "wildfire" | "earthquake" | "volcano" | "subsidence" | "wetland" | "farming";
export type Status = "operational" | "prototype";

export type SiteSummary = {
  id: string;
  name: string;
  lens: Lens;
  view: "2d" | "3d";
  bbox: Bbox;
  center: [number, number];
  event_date: string | null;
  passes: number;
  first: string;
  last: string;
  headline: string | null;
  has_model: boolean;
  hook: string | null;
  /** Questions answered for this place (null where none are built yet). */
  decide: {
    date: string;
    questions: { id: string; title: string; headline: string; layer: string | null }[];
    roles: { id: string; label: string; first: string }[];
    cover_layer: string | null;
  } | null;
};

export type LayerClass = { value: number; label: string; color: string };

export type LayerInfo = {
  id: string;
  label: string;
  kind: "physics" | "baseline" | "prediction" | "context" | "answer";
  unit: string;
  colormap: string;
  range: [number, number];
  dates: string[];
  status: Status;
  classes?: LayerClass[];
  what_this_shows?: string;
};

export type PassInfo = { date: string; collection: string; stack: string; granules: string[] };

export type Manifest = {
  kind: "showcase" | "analysis";
  id: string;
  lens: Lens | null;
  name: string;
  bbox: Bbox;
  event_date: string | null;
  view: "2d" | "3d";
  passes: PassInfo[];
  layers: LayerInfo[];
  series: { variable: string; path: string; unit: string; grid_m?: number }[];
  insights?: string[];
  quality?: { passes: number; gaps: string[]; masked_share: number; notes: string[] };
  terrain?: { meta: string; dem: string; displacement?: string[] } | Record<string, unknown>;
  model_card: string | null;
  generated_at: string;
};

export type LayerStats = {
  layer: string;
  date: string;
  unit: string;
  cells: number;
  area_ha: number;
  classes?: { value: number; label: string; area_ha: number; share: number }[];
  mean?: number;
  p5?: number;
  p25?: number;
  median?: number;
  p75?: number;
  p95?: number;
  histogram?: Histogram;
};

export type TsPoint = { date: string; value: number; p25?: number; p75?: number; n?: number };
export type Timeseries = { variable: string; unit: string; series: TsPoint[]; cells?: number; lon?: number; lat?: number };

export type GeoPolygon = { type: "Polygon"; coordinates: [number, number][][] };

export const fetchSites = (signal?: AbortSignal) => getJson<SiteSummary[]>("/sites", signal);

/** A request for a new Showcase Site at a point (api/showcase_requests.py). Stored for the team; nothing is sent. */
export type ShowcaseRequestBody = { name: string; lon: number; lat: number; lens: Lens | "other"; role: string | null; why: string; contact: string };
export type RequestedPlace = { id: string; name: string; lon: number; lat: number; lens: Lens | "other"; role: string | null; why: string; status: string; created: string };
export const postShowcaseRequest = (body: ShowcaseRequestBody) => postJson<RequestedPlace>("/showcase-requests", body);
export const fetchShowcaseRequests = (signal?: AbortSignal) => getJson<RequestedPlace[]>("/showcase-requests", signal);

// ---------------------------------------------------------------- Questions and answers (ADR-0008)

export type Verdict = "good" | "caution" | "bad" | "unknown";
export type Solution = { title: string; what: string; cost: "low" | "medium" | "high"; source: string; check: string };
export type AnswerClass = { value: number; label: string; color: string; verdict: Verdict; meaning: string; solutions: string[]; area_ha: number; share: number };
export type RankedColumn = { key: string; label: string; unit?: string };
export type RankedRow = Record<string, string | number> & { lon: number; lat: number };
export type Question = {
  id: string;
  title: string;
  /** A two-to-four word name for lists and map bubbles (questions/*.yaml). */
  topic?: string | null;
  short: string;
  order: number;
  status: Status;
  point_only: boolean;
  headline: string;
  layer: string | null;
  classes: AnswerClass[];
  solutions: string[];
  ranked?: { title: string; columns: RankedColumn[]; rows: RankedRow[]; total: number };
  features?: "lines" | "points" | null;
  sources: string[];
  limits: string[];
};
export type Role = { id: string; label: string; questions: string[] };
export type Answers = {
  site: string;
  lens: Lens;
  name: string;
  date: string;
  grid_m: number;
  roles: Role[];
  questions: Question[];
  solutions: Record<string, Solution>;
  evidence: Record<string, unknown>;
  /** The AI Model map the rules read on this site ("the AI water Model's maps of every Pass"), or null for rules on radar alone. */
  model_evidence?: string | null;
  attribution: string;
};
export type Alternative = { lon: number; lat: number; distance_m: number; direction: string; sinking_cm_yr: number; years_500: number; label: string };
/** The number behind an answer, with the Question's thresholds as marks (worse: which direction is worse). */
export type Measure = { label: string; value: number; unit: string; max: number; worse: "higher" | "lower"; marks: { at: number; label: string }[] };
export type AnswerCard = {
  question: string;
  title: string;
  topic?: string | null;
  measure?: Measure;
  class: number | null;
  label: string | null;
  verdict: Verdict | null;
  color: string | null;
  reasons: string[];
  solutions: string[];
  alternatives?: Alternative[];
};
export type NearPlace = { name: string; local: string; kind: string; km: number; direction: string };
export type AnswersAt = { lon: number; lat: number; date: string; place?: NearPlace | null; cards: AnswerCard[]; values: Record<string, number | null> };

export const fetchAnswers = (id: string, signal?: AbortSignal) => getJson<Answers>(`/answers/${id}`, signal);
export type Place = { name: string; local: string; kind: string; lon: number; lat: number };
/** Minimal GeoJSON for the map's drawn answers (lines and points). */
export type AnswerFeature = { type: "Feature"; properties: Record<string, string | number>; geometry: { type: "LineString"; coordinates: [number, number][] } | { type: "Point"; coordinates: [number, number] } };
export type AnswerFeatures = { type: "FeatureCollection"; features: AnswerFeature[] };
export const fetchPlaces = (id: string, q: string, signal?: AbortSignal) => getJson<Place[]>(`/answers/${id}/places?q=${encodeURIComponent(q)}`, signal);
export const fetchFeatures = (id: string, question: string, signal?: AbortSignal) => getJson<AnswerFeatures>(`/answers/${id}/features/${question}`, signal);
export const fetchAnswersAt = (id: string, lon: number, lat: number, signal?: AbortSignal) =>
  getJson<AnswersAt>(`/answers/${id}/at?lon=${lon.toFixed(5)}&lat=${lat.toFixed(5)}`, signal);
export const fetchManifest = (id: string, signal?: AbortSignal) => getJson<Manifest>(`/sites/${id}`, signal);
export const fetchStats = (id: string, layer: string, date: string, signal?: AbortSignal) => getJson<LayerStats>(`/stats/${id}?layer=${layer}&date=${date}`, signal);
export const fetchStatsIn = (id: string, layer: string, date: string, polygon: GeoPolygon, signal?: AbortSignal) =>
  postJson<LayerStats>(`/stats/${id}?layer=${layer}&date=${date}`, polygon, signal);
export const fetchPointSeries = (id: string, variable: string, lon: number, lat: number, signal?: AbortSignal) =>
  getJson<Timeseries>(`/timeseries/${id}?variable=${variable}&lon=${lon.toFixed(5)}&lat=${lat.toFixed(5)}`, signal);
export const fetchAreaSeries = (id: string, variable: string, polygon: GeoPolygon, signal?: AbortSignal) =>
  postJson<Timeseries>(`/timeseries/${id}?variable=${variable}`, polygon, signal);

export const layerTileUrl = (id: string, layer: string, date: string) => `${API}/tiles/${id}/${layer}/${date}/{z}/{x}/{y}.png`;
export const layerPreviewUrl = (id: string, layer: string, date: string, size = 1024) => `${API}/preview/${id}/${layer}/${date}.png?max_size=${size}`;
export const terrainUrl = (id: string, name: string) => `${API}/terrain/${id}/${name}`;

export type TerrainMeta = {
  shape: [number, number];
  bbox: Bbox;
  cell_m: number;
  height_m: [number, number];
  displacement_unit: string;
  dates: string[];
};

// ---------------------------------------------------------------- Models

export type ModelRow = {
  lens: Lens;
  name: string;
  status: Status;
  metric: string;
  model_score: number;
  baseline_score: number;
  baseline: string;
  sites: string[];
  labels: "real" | "proxy" | "self_supervised";
};

export type Score = { name: string; metric: string; score: number | null };

export type ModelCard = {
  lens: Lens;
  name: string;
  job: string;
  user: string;
  sites: string[];
  inputs: string[];
  outputs?: { value: number; label: string; reliable?: boolean }[];
  prediction?: { unit: string; colormap: string; range: [number, number]; label?: string };
  labels: { kind: "real" | "proxy" | "self_supervised"; source: string; notes?: string };
  baseline: Score;
  model: Score & { framework?: string; parameters?: number };
  extra_scores?: Score[];
  split: string;
  limits: string[];
  status: Status;
  updated: string;
};

export const fetchModels = (signal?: AbortSignal) => getJson<ModelRow[]>("/models", signal);
export const fetchModelCard = (lens: string, signal?: AbortSignal) => getJson<ModelCard>(`/models/${lens}`, signal);

/** True when a lower score is better (errors such as RMSE). */
export const lowerIsBetter = (metric: string) => /rmse|error|mae/i.test(metric);

// ---------------------------------------------------------------- Explore: coverage and Analyses

export type CoverageFeature = {
  type: "Feature";
  geometry: GeoPolygon;
  properties: { id: string; date: string; secondary_date: string | null; stack: string; track: number; direction: string; maturity: string; product: string };
};
export type Coverage = { type: "FeatureCollection"; features: CoverageFeature[] };

export const fetchCoverage = (bbox: Bbox, product: "GCOV" | "GUNW", signal?: AbortSignal) =>
  getJson<Coverage>(`/coverage?bbox=${bbox.map((v) => v.toFixed(3)).join(",")}&product=${product}`, signal);

export type JobRequest = {
  bbox: Bbox;
  product: "GCOV" | "GUNW";
  start: string;
  end: string;
  lens?: Lens | null;
  event_date?: string | null;
  event_end_date?: string | null;
  name?: string | null;
};

export type Job = {
  id: string;
  status: "queued" | "running" | "done" | "error";
  message?: string;
  place?: number | null;
  request?: JobRequest;
  area_km2?: number;
  granules?: number;
  updated?: string;
};

export const startJob = (req: JobRequest) => postJson<Job>("/jobs", req);
export const fetchJob = (id: string, signal?: AbortSignal) => getJson<Job>(`/jobs/${id}`, signal);
export const fetchJobs = (signal?: AbortSignal) => getJson<Job[]>("/jobs?limit=8", signal);

/** Area limits per product, km² (saraura/config.py AREA_LIMIT_KM2). */
export const AREA_LIMIT_KM2 = { GCOV: 900, GUNW: 500 } as const;

export const LENS_PRODUCT: Record<Lens, ("GCOV" | "GUNW")[]> = {
  wildfire: ["GCOV"],
  farming: ["GCOV"],
  wetland: ["GCOV", "GUNW"],
  volcano: ["GCOV", "GUNW"],
  earthquake: ["GUNW"],
  subsidence: ["GUNW"],
};

/** Geodesic-enough area of a lon/lat box in km² (spherical Earth). */
export function bboxKm2([w, s, e, n]: Bbox) {
  const R = 6371.0088;
  const rad = Math.PI / 180;
  return Math.abs(R * R * (e - w) * rad * (Math.sin(n * rad) - Math.sin(s * rad)));
}

// ---------------------------------------------------------------- Assistant and Report

export type AssistantStatus = { configured: boolean; model: string; status: Status };
export type AssistantAnswer = { text: string; generated_by: "AI"; model: string; grounded_on: string[] };

export const fetchAssistantStatus = (signal?: AbortSignal) => getJson<AssistantStatus>("/assistant", signal);
export const askAssistant = (body: { study_id: string; question: string; layer?: string | null; date?: string | null; language?: string }, signal?: AbortSignal) =>
  postJson<AssistantAnswer>("/assistant", body, signal);

export async function downloadReport(id: string, name: string) {
  const r = await fetch(`${API}/report/${id}`, { method: "POST" });
  if (!r.ok) await fail(r);
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `SARAURA_${name.replace(/[^A-Za-z0-9_-]+/g, "_").slice(0, 60)}.pdf`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

// ---------------------------------------------------------------- raw Granule browser (/browse)

export type Pol = "HV" | "HH" | "RGB";

export type Pass = { id: string; date: string; start: string; maturity: string; ready: boolean };

export type Stack = {
  stack: string;
  track: number;
  direction: "ascending" | "descending" | string;
  bandwidth_mhz: string;
  polarizations: string[];
  footprint: [number, number][];
  passes: Pass[];
};

export type SeriesPoint = { date: string; id: string; HH?: number | null; HV?: number | null; error?: string };

export type Series = { lon: number; lat: number; stack: string; radius_m: number; units: string; series: SeriesPoint[] };

/** Kept for the Inspector's optional finding line; the old analysis panel is gone. */
export type Finding = { class: string | null; label?: string; changed_on?: string | null; hv_change_db?: number; hh_change_db?: number; confidence_t?: number };

export function fetchStacks(bbox: Bbox, signal?: AbortSignal) {
  return getJson<{ count: number; stacks: Stack[] }>(`/granules?bbox=${bbox.join(",")}`, signal);
}

export function fetchSeries(lon: number, lat: number, stack: string, signal?: AbortSignal) {
  return getJson<Series>(`/browse/timeseries?lon=${lon.toFixed(5)}&lat=${lat.toFixed(5)}&stack=${stack}&radius_m=100`, signal);
}

export const tileUrl = (id: string, pol: Pol) => `${API}/browse/${id}/tiles/${pol}/{z}/{x}/{y}.png`;

export const changeUrl = (before: string, after: string, pol: "HV" | "HH") => `${API}/change/${before}/${after}/${pol}/{z}/{x}/{y}.png`;

export const analysisTileUrl = (id: string, layer: "class" | "when") => `${API}/analysis/${id}/${layer}/{z}/{x}/{y}.png`;

export const vertexUrl = (granuleId: string) => `https://search.asf.alaska.edu/#/?searchType=List%20Search&searchList=${encodeURIComponent(granuleId)}`;

// ---------------------------------------------------------------- research plots (api/research.py)

export type Histogram = { edges: number[]; counts: number[]; std: number };
export type ClassSeries = { value: number; label: string; color: string | null; cells: number; series: TsPoint[] };
export type SeriesByClass = { variable: string; unit: string; layer: string; date: string; layer_label: string; classes: ClassSeries[] };
export type ChangeByDate = { layer: string; label: string; unit: string; threshold: number; rows: { date: string; drop_share: number; rise_share: number; median: number }[] };
export type Agreement = {
  model_layer: string;
  model_label: string;
  model_date: string;
  baseline_layer: string;
  baseline_label: string;
  baseline_date: string;
  classes: { value: number; label: string; color: string; area_ha: number }[];
  analysed_ha: number;
  overlap_share: number | null;
};

export type ClassArea = {
  layer: string; label: string; kind: string; status: string;
  classes: { value: number; label: string; color: string }[];
  rows: { date: string; analysed_ha: number; area_ha: Record<string, number> }[];
};

export const fetchClassArea = (id: string, signal?: AbortSignal) => getJson<ClassArea>(`/research/${id}/class_area`, signal);
export const fetchSeriesByClass = (id: string, variable: string, layer: string, date: string, signal?: AbortSignal) =>
  getJson<SeriesByClass>(`/research/${id}/series_by_class?variable=${variable}&layer=${layer}&date=${date}`, signal);
export const fetchChangeByDate = (id: string, layer = "dhv", threshold = 3, signal?: AbortSignal) =>
  getJson<ChangeByDate>(`/research/${id}/change_by_date?layer=${layer}&threshold=${threshold}`, signal);
export const fetchAgreement = (id: string, signal?: AbortSignal) => getJson<Agreement>(`/research/${id}/agreement`, signal);
export const agreementPngUrl = (id: string, size = 1100) => `${API}/research/${id}/agreement.png?max_size=${size}`;

/** The class layer that splits a study's time series best: the AI Model's classes, else the Baseline's. */
export function splitLayer(m: Manifest): LayerInfo | null {
  return (
    m.layers.find((l) => l.kind === "prediction" && l.colormap === "categorical") ??
    m.layers.find((l) => l.kind === "baseline" && l.colormap === "categorical") ??
    null
  );
}
