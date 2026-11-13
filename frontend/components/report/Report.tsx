"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { HistogramChart, MultiLineChart } from "@/components/charts/Charts";
import { ModelCardView } from "@/components/models/Models";
import ResearchPlots from "@/components/research/ResearchPlots";
import { Legend, StatsView } from "@/components/study/StudyPage";
import {
  API,
  bboxKm2,
  fetchAreaSeries,
  fetchManifest,
  fetchStats,
  layerPreviewUrl,
  longDate,
  vertexUrl,
  type Bbox,
  type GeoPolygon,
  type LayerInfo,
  type LayerStats,
  type Manifest,
  type Timeseries,
} from "@/lib/api";
import { addDays, locator, modisTrueColor } from "@/lib/gibs";
import { KIND_LABEL, LENSES, defaultLayer, fmt, groupNotes } from "@/lib/style";
import MapFrame from "./MapFrame";

const VAR_LABEL: Record<string, string> = { hv_db: "Vegetation scattering (HV)", hh_db: "Surface scattering (HH)", cum_disp_cm: "Ground motion since the first Pass (line of sight)" };
const VAR_COLOR: Record<string, string> = { hv_db: "#b45309", hh_db: "#2563eb", cum_disp_cm: "#7c3aed" };

const METHODS: Record<string, string[]> = {
  GCOV: [
    "Product: NISAR Level-2 GCOV (geocoded, terrain-corrected backscatter, gamma-nought), L-band, HH and HV polarisations.",
    "Read directly from NASA Earthdata over HTTP, chunk by chunk, and resampled to the study grid by block averaging (which also reduces speckle; no other filter).",
    "Layers: HH and HV in dB, HV/HH ratio, change since the previous Pass, season mean, spread and coefficient of variation, colour composite (R = HH, G = HV, B = HH/HV).",
    "Change detection: a drop or rise counts when it exceeds 3 dB and persists into the next Pass (single-Pass flickers are treated as noise).",
  ],
  GUNW: [
    "Product: NISAR Level-2 GUNW (geocoded unwrapped interferograms) between consecutive Passes of one Stack, 80 m.",
    "Corrections: the ionosphere phase screen supplied with each product is subtracted; only the largest connected component of the unwrapped phase is kept; pixels with coherence below 0.3 are masked.",
    "Displacement d = -phase x wavelength / 4 pi, in cm along the radar line of sight (positive toward the satellite). Pairs are chained into a cumulative series referenced to a stable area (or the scene median when that area is not coherent).",
    "Not yet applied: the tropospheric and solid-earth-tide corrections supplied as lookup tables; they explain part of the remaining centimetre-level noise.",
  ],
};

const GLOSSARY: [string, string][] = [
  ["Backscatter (dB)", "How much radar energy returns to the satellite. Decibels: +3 dB is about double, -3 dB about half."],
  ["HH / HV", "Polarisations. HH: sent and received horizontally (surfaces, buildings). HV: sent horizontally, received vertically (scattering inside vegetation)."],
  ["Coherence", "From 0 to 1: how similar the ground looked to the radar between two Passes. It drops where the surface was disturbed."],
  ["Line of sight", "The direction from the ground to the satellite. Motion is measured along it, so it mixes vertical and east-west motion."],
  ["Pass, Stack", "A Pass is one overflight (every 12 days). A Stack is all Passes on the same orbit track and frame, so they can be compared."],
  ["Baseline", "A simple published rule the AI Model must beat. Both are scored on ground the Model did not train on."],
  ["Proxy labels", "Training labels made from another satellite (such as Sentinel-2) rather than field surveys."],
];

function boxPolygon([w, s, e, n]: number[]): GeoPolygon {
  return { type: "Polygon", coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] };
}

export default function Report({ id }: { id: string }) {
  const [m, setM] = useState<Manifest | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [stats, setStats] = useState<Record<string, LayerStats | null>>({});
  const [series, setSeries] = useState<Record<string, Timeseries | null>>({});
  const [loadedImgs, setLoadedImgs] = useState<Set<string>>(new Set());
  const [researchDone, setResearchDone] = useState(false);

  useEffect(() => {
    fetchManifest(id).then(setM).catch((e) => setErr(e.message));
  }, [id]);

  const main = useMemo(() => (m ? defaultLayer(m.layers, m.kind) : null), [m]);
  const baseline = useMemo(() => m?.layers.find((l) => l.kind === "baseline") ?? null, [m]);
  const rgb = useMemo(() => m?.layers.find((l) => l.id === "rgb") ?? null, [m]);
  const atlas = useMemo(() => {
    if (!m) return [] as LayerInfo[];
    const shown = new Set([main?.id, baseline?.id, "rgb", "hvhh_db"]);
    return m.layers.filter((l) => !shown.has(l.id));
  }, [m, main, baseline]);

  // Optical context dates: around the event, else the first and last Pass.
  const optical = useMemo(() => {
    if (!m) return null;
    const last = m.passes[m.passes.length - 1].date;
    const before = m.event_date ? addDays(m.event_date, -2) : m.passes[0].date;
    const after = m.event_date ? m.passes.find((p) => p.date >= m.event_date!)?.date ?? last : last;
    return { before, after };
  }, [m]);

  // Every picture registers itself; the PDF waits until all have loaded (or failed).
  const imageKeys = useMemo(() => {
    if (!m || !main) return [] as string[];
    const k = ["locator", "opt_before", "opt_after", "main"];
    if (rgb) k.push("rgb");
    if (baseline && baseline.id !== main.id) k.push("baseline");
    for (const l of atlas) k.push(`atlas_${l.id}`);
    return k;
  }, [m, rgb, main, baseline, atlas]);
  const done = useCallback((k: string) => () => setLoadedImgs((s) => (s.has(k) ? s : new Set(s).add(k))), []);

  useEffect(() => {
    if (!m) return;
    const want = [main, baseline, ...atlas].filter((l): l is LayerInfo => !!l && l.colormap !== "rgb");
    for (const l of want) {
      const d = l.dates[l.dates.length - 1];
      fetchStats(id, l.id, d).then((x) => setStats((s) => ({ ...s, [l.id]: x }))).catch(() => setStats((s) => ({ ...s, [l.id]: null })));
    }
    for (const v of m.series)
      fetchAreaSeries(id, v.variable, boxPolygon(m.bbox)).then((x) => setSeries((s) => ({ ...s, [v.variable]: x }))).catch(() => setSeries((s) => ({ ...s, [v.variable]: null })));
  }, [id, m, main, baseline, atlas]);

  const onResearch = useCallback(() => setResearchDone(true), []);
  const wantStats = [main, baseline, ...atlas].filter((l): l is LayerInfo => !!l && l.colormap !== "rgb");
  const ready =
    !!m && imageKeys.length > 0 && imageKeys.every((k) => loadedImgs.has(k)) && researchDone && wantStats.every((l) => l.id in stats) && m.series.every((v) => v.variable in series);
  useEffect(() => {
    if (ready) document.body.setAttribute("data-report-ready", "true");
    return () => document.body.removeAttribute("data-report-ready");
  }, [ready]);

  if (err) return <p className="p-8">{err}</p>;
  if (!m || !main || !optical) return <p className="p-8">Loading…</p>;

  const lens = m.lens ? LENSES[m.lens] : null;
  const b = m.bbox as Bbox;
  const loc = locator(b);
  const collections = [...new Set(m.passes.map((p) => p.collection))];
  const stacks = [...new Set(m.passes.map((p) => p.stack))];
  const products = [m.layers.some((l) => l.id === "hv_db") && "GCOV", m.layers.some((l) => l.id === "coherence") && "GUNW"].filter(Boolean) as string[];
  const center = [(b[1] + b[3]) / 2, (b[0] + b[2]) / 2];
  const cite = `SARAURA (2026). ${m.name}: NISAR radar ${m.kind === "showcase" ? "Showcase Site" : "Analysis"} report. Data: NASA-ISRO NISAR Level-2 ${products.join(" and ")} (${collections.join(", ")}), distributed by the Alaska Satellite Facility DAAC. Generated ${m.generated_at.slice(0, 10)}.`;
  const last = (l: LayerInfo) => l.dates[l.dates.length - 1];
  const twoUp = !!baseline && baseline.id !== main.id;

  const layerCard = (l: LayerInfo, key: string, big = false) => (
    <article key={key} className="report-card min-w-0">
      <p className="text-[10px] uppercase tracking-widest text-neutral-500">{KIND_LABEL[l.kind]} · {l.status}</p>
      <h3 className="text-[15px] font-semibold leading-snug">{l.label}</h3>
      {l.what_this_shows && <p className="mt-0.5 text-[11.5px] leading-snug text-neutral-700">{l.what_this_shows}</p>}
      <div className="mt-2">
        <MapFrame src={layerPreviewUrl(id, l.id, last(l), big ? 1400 : 900)} bbox={b} alt={`${l.label}, ${longDate(last(l))}`} onDone={done(key)}
          caption={`${longDate(last(l))}${l.dates.length > 1 ? ` (latest of ${l.dates.length} dates since ${longDate(l.dates[0])})` : ""}`} />
      </div>
      <div className="mt-1.5"><Legend layer={l} /></div>
      {stats[l.id] && (
        <div className="mt-2 min-w-0">
          <StatsView stats={stats[l.id]!} />
          {stats[l.id]!.histogram && (
            <div className="mt-2">
              <p className="text-[10px] text-neutral-500">Distribution over the area (standard deviation {fmt(stats[l.id]!.histogram!.std)} {l.unit})</p>
              <HistogramChart hist={stats[l.id]!.histogram!} unit={l.unit} color={VAR_COLOR[l.id] ?? "#475569"} />
            </div>
          )}
        </div>
      )}
    </article>
  );

  return (
    <div className="report" data-progress={`images ${imageKeys.filter((k) => loadedImgs.has(k)).length}/${imageKeys.length}; research ${researchDone}`}>
      {/* 1. Summary */}
      <section className="page">
        <div className="flex items-start justify-between gap-6">
          <div className="min-w-0">
            <p className="text-[10px] uppercase tracking-[0.2em] text-neutral-500">SARAURA · NISAR radar report · {m.kind === "showcase" ? "Showcase Site" : "Analysis"}</p>
            <h1 className="mt-2 font-display text-[34px] leading-[1.05]">{m.name}</h1>
            {lens && <p className="mt-1 text-sm" style={{ color: lens.color }}>{lens.label} Lens · {lens.pitch}</p>}
          </div>
          <div className="w-[36%] shrink-0">
            <MapFrame src={loc.url} bbox={loc.box} projection="plate" overlay={b} alt="Where the study area is" onDone={done("locator")} maxRatio={1} tickCount={3} />
          </div>
        </div>

        <table className="report-facts mt-3 w-full table-fixed text-[11.5px]">
          <colgroup><col className="w-[12%]" /><col className="w-[38%]" /><col className="w-[12%]" /><col className="w-[38%]" /></colgroup>
          <tbody>
            <tr><th>Centre</th><td>{center[0].toFixed(3)}°, {center[1].toFixed(3)}° (lat, lon)</td><th>Area</th><td>{Math.round(bboxKm2(b)).toLocaleString("en-GB")} km² · {b.map((v) => v.toFixed(2)).join(", ")} (W, S, E, N)</td></tr>
            <tr><th>Period</th><td>{longDate(m.passes[0].date)} to {longDate(m.passes[m.passes.length - 1].date)}</td><th>Event</th><td>{m.event_date ? longDate(m.event_date) : "none set"}</td></tr>
            <tr><th>Passes</th><td>{m.passes.length}, every 12 days{m.quality?.gaps?.length ? ` (gap: ${m.quality.gaps.join("; ")})` : ""}</td><th>Data</th><td>NISAR L2 {products.join(" + ")} · {collections.join(" + ")} · Stack {stacks.join(", ")}</td></tr>
          </tbody>
        </table>

        {!!m.insights?.length && (
          <div className="mt-4">
            <h2 className="report-h2">Key findings</h2>
            <ul className="mt-2 space-y-1.5 text-[12.5px] leading-snug">
              {m.insights.map((s) => <li key={s} className="border-l-[3px] border-amber-600 pl-3">{s}</li>)}
            </ul>
            <p className="mt-2 text-[10.5px] text-neutral-500">Computed by the SARAURA pipeline from the radar measurements, not written by AI. Radar shows that something changed; causes are hypotheses to confirm with optical images, field reports or official maps.</p>
          </div>
        )}

        {rgb && (
          <div className="mt-4">
            <h2 className="report-h2">The area as NISAR sees it</h2>
            <MapFrame src={layerPreviewUrl(id, "rgb", last(rgb), 1400)} bbox={b} alt="Radar colour composite" onDone={done("rgb")} maxRatio={0.5}
              caption={<>Radar colour composite, {longDate(last(rgb))}. {rgb.what_this_shows}</>} />
          </div>
        )}
      </section>

      {/* 2. Optical context from NASA GIBS */}
      <section className="page-part">
        <h2 className="report-h2">What an optical satellite saw</h2>
        <p className="report-p">NASA MODIS (Terra) true-colour images from NASA GIBS, {m.event_date ? "just before and just after the event" : "at the start and end of the period"}. Clouds, smoke and night hide the ground from optical sensors; NISAR&rsquo;s L-band radar sees through them, so every radar Pass in this report is usable.</p>
        <div className="mt-3 grid grid-cols-2 gap-5">
          <MapFrame src={modisTrueColor(b, optical.before, 900)} bbox={b} projection="plate" alt={`MODIS true colour, ${longDate(optical.before)}`} onDone={done("opt_before")} caption={`MODIS Terra, ${longDate(optical.before)}`} />
          <MapFrame src={modisTrueColor(b, optical.after, 900)} bbox={b} projection="plate" alt={`MODIS true colour, ${longDate(optical.after)}`} onDone={done("opt_after")} caption={`MODIS Terra, ${longDate(optical.after)}`} />
        </div>
      </section>

      {/* 3. Results */}
      <section className="page-part">
        <h2 className="report-h2">Results</h2>
        <div className={`mt-2 grid gap-5 ${twoUp ? "grid-cols-2" : "grid-cols-1"}`}>
          {layerCard(main, "main", !twoUp)}
          {twoUp && layerCard(baseline!, "baseline")}
        </div>
      </section>

      {/* 4. Analysis plots */}
      <section className="page-part">
        <h2 className="report-h2">Analysis</h2>
        <div className="mt-3"><ResearchPlots m={m} print onReady={onResearch} /></div>
        {m.series.some((v) => series[v.variable]) && (
          <div className="mt-7 break-inside-avoid">
            <h3 className="text-base font-semibold">Whole-area averages</h3>
            <p className="report-p">Mean of all cells with data on each Pass; shading is the middle half of values.</p>
            <div className="mt-2 grid grid-cols-2 gap-5">
              {m.series.map((v) => series[v.variable] && (
                <div key={v.variable} className="min-w-0">
                  <p className="text-xs font-medium">{VAR_LABEL[v.variable] ?? v.variable}</p>
                  <MultiLineChart still width={360} height={200} unit={v.unit} eventDate={m.event_date} lines={[{ label: "area mean", color: VAR_COLOR[v.variable] ?? "#475569", points: series[v.variable]!.series }]} />
                </div>
              ))}
            </div>
          </div>
        )}
      </section>

      {/* 5. Layer atlas */}
      {atlas.length > 0 && (
        <section className="page-part">
          <h2 className="report-h2">Layer atlas</h2>
          <p className="report-p">Every other layer of this study on its latest date, with its distribution. The interactive Study page has every date.</p>
          <div className="mt-3 grid grid-cols-2 gap-x-5 gap-y-6">{atlas.map((l) => layerCard(l, `atlas_${l.id}`))}</div>
        </section>
      )}

      {/* 6. Model card */}
      {m.kind === "showcase" && m.model_card && (
        <section className="page-part">
          <h2 className="report-h2">AI Model vs Baseline</h2>
          <ModelCardView lens={m.model_card} print />
        </section>
      )}

      {/* 7. Methods, glossary, reuse */}
      <section className="page-part">
        <h2 className="report-h2">Methods</h2>
        {products.map((p) => (
          <div key={p} className="mt-2 break-inside-avoid">
            <h3 className="text-sm font-semibold">{p === "GCOV" ? "Backscatter (GCOV)" : "Ground motion (GUNW)"}</h3>
            <ul className="mt-1 list-disc space-y-0.5 pl-5 text-[11.5px] leading-snug text-neutral-800">{METHODS[p].map((t) => <li key={t}>{t}</li>)}</ul>
          </div>
        ))}
        <div className="mt-2 break-inside-avoid">
          <h3 className="text-sm font-semibold">Calibration, quality and data choices</h3>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-[11.5px] leading-snug text-neutral-800">
            <li>Only calibrated collections are used (PROVISIONAL and VALIDATED); the uncalibrated BETA collection never is. One series may mix the two, since both are calibrated.</li>
            <li>Terrain: Copernicus GLO-30 elevation model (30 m), for slope and the 3D view.</li>
            {groupNotes(m.quality?.notes).map((n) => <li key={n}>{n}</li>)}
            {m.quality && m.quality.masked_share > 0 && <li>{(m.quality.masked_share * 100).toFixed(1)}% of pixel values have no data (outside the swath, water or masked).</li>}
          </ul>
        </div>

        <div className="mt-5 grid grid-cols-2 gap-6">
          <div className="min-w-0 break-inside-avoid">
            <h2 className="report-h2">Glossary</h2>
            <dl className="mt-2 space-y-1.5 text-[11px] leading-snug">
              {GLOSSARY.map(([t, d]) => <div key={t}><dt className="inline font-semibold">{t}: </dt><dd className="inline text-neutral-700">{d}</dd></div>)}
            </dl>
          </div>
          <div className="min-w-0 break-inside-avoid">
            <h2 className="report-h2">Reuse and cite</h2>
            <p className="mt-2 text-[11px] leading-snug text-neutral-800">{cite}</p>
            <ul className="mt-2 space-y-1 text-[11px] leading-snug text-neutral-800">
              <li>Interactive Study page: <span className="font-mono">/study/{m.id}</span></li>
              <li>Layers as Cloud-Optimized GeoTIFFs and per-cell time series as Parquet through the SARAURA API: <span className="break-all font-mono">{API}/sites/{m.id}</span></li>
              <li>The source Granules in ASF Vertex: <a className="text-amber-800 underline" href={vertexUrl(m.passes.flatMap((p) => p.granules).join(","))}>open the list</a> (full IDs in the appendix).</li>
              <li>SAR basics: earthdata.nasa.gov/learn/earth-observation-data-basics/sar</li>
            </ul>
          </div>
        </div>
      </section>

      {/* Appendix */}
      <section className="page-part">
        <h2 className="report-h2">Appendix: source Granules</h2>
        <p className="report-p">Generated {m.generated_at.replace("T", " ").replace("Z", " UTC")}. Every Pass and the NISAR products it was built from.</p>
        <table className="mt-2 w-full table-fixed text-[8.5px] leading-tight">
          <colgroup><col className="w-[12%]" /><col className="w-[15%]" /><col className="w-[10%]" /><col /></colgroup>
          <thead><tr className="text-left text-neutral-500"><th className="pb-1">Date</th><th className="pb-1">Collection</th><th className="pb-1">Stack</th><th className="pb-1">Granule IDs</th></tr></thead>
          <tbody>
            {m.passes.map((p) => (
              <tr key={p.date} className="border-t border-neutral-200 align-top">
                <td className="py-0.5">{p.date}</td>
                <td className="py-0.5">{p.collection}</td>
                <td className="py-0.5">{p.stack}</td>
                <td className="break-all py-0.5 font-mono">{p.granules.join(" ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
