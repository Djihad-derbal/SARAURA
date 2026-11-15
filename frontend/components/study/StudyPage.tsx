"use client";

import { motion, useReducedMotion } from "motion/react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import LineChart from "@/components/charts/LineChart";
import {
  askAssistant,
  downloadReport,
  fetchAreaSeries,
  fetchAssistantStatus,
  fetchFeatures,
  fetchManifest,
  fetchPointSeries,
  fetchStats,
  getJson,
  layerPreviewUrl,
  longDate,
  shortDate,
  vertexUrl,
  type AssistantAnswer,
  type AssistantStatus,
  type GeoPolygon,
  type LayerInfo,
  type LayerStats,
  type AnswerFeatures,
  type Manifest,
  type Question,
  type TerrainMeta,
  type Timeseries,
} from "@/lib/api";
import { KIND_LABEL, LENSES, defaultLayer, defaultSeries, fmt, gradient, groupNotes, ha } from "@/lib/style";
import ResearchPlots from "@/components/research/ResearchPlots";
import { addDays, modisTrueColor } from "@/lib/gibs";
import AskPanel, { PlaceSearch, SpotBubble, useAnswers } from "./AskPanel";
import StudyMap from "./StudyMap";

const Terrain3D = dynamic(() => import("./Terrain3D"), { ssr: false, loading: () => <div className="h-full w-full bg-bg" aria-busy /> });

const KIND_ORDER: LayerInfo["kind"][] = ["answer", "prediction", "baseline", "physics", "context"];
const SERIES_LABEL: Record<string, string> = { hv_db: "Vegetation scattering (HV)", hh_db: "Surface scattering (HH)", cum_disp_cm: "Ground motion since the first Pass (line of sight)" };

function nearest(dates: string[], d: string) {
  if (dates.includes(d)) return d;
  const t = Date.parse(d);
  return dates.reduce((a, b) => (Math.abs(Date.parse(b) - t) < Math.abs(Date.parse(a) - t) ? b : a), dates[dates.length - 1]);
}

function boxPolygon([w, s, e, n]: number[]): GeoPolygon {
  return { type: "Polygon", coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] };
}

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`rounded px-1.5 py-0.5 text-[11px] ${status === "operational" ? "bg-emerald-400/15 text-emerald-300" : "bg-amber-400/15 text-amber-200"}`}>
      {status}
    </span>
  );
}

export function Legend({ layer }: { layer: LayerInfo }) {
  if (layer.colormap === "rgb")
    return (
      <div className="flex gap-3 text-xs text-ink-2">
        <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm bg-[#ff3b3b]" />HH</span>
        <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm bg-[#3bff6a]" />HV</span>
        <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm bg-[#4b6bff]" />HH/HV</span>
      </div>
    );
  if (layer.colormap === "categorical")
    return (
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
        {(layer.classes ?? []).map((c) => (
          <li key={c.value} className="flex items-center gap-1.5">
            <span className="inline-block h-3 w-3 rounded-sm" style={{ background: c.color }} />
            {c.label}
          </li>
        ))}
      </ul>
    );
  return (
    <div>
      <div className="h-2.5 rounded-sm" style={{ background: gradient(layer.colormap) }} />
      <div className="mt-1 flex justify-between font-mono text-[11px] text-ink-3">
        <span>{fmt(layer.range[0])}</span>
        <span>{layer.unit}</span>
        <span>{fmt(layer.range[1])}</span>
      </div>
    </div>
  );
}

export function StatsView({ stats }: { stats: LayerStats }) {
  if (stats.classes)
    return (
      <table className="w-full text-sm">
        <tbody>
          {stats.classes.map((c) => (
            <tr key={c.value} className="border-t border-line first:border-0">
              <td className="py-1.5 text-ink-2">{c.label}</td>
              <td className="py-1.5 text-right font-mono">{ha(c.area_ha)}</td>
              <td className="w-16 py-1.5 text-right font-mono text-ink-3">{(c.share * 100).toFixed(1)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  return (
    <dl className="grid grid-cols-3 gap-2 text-center text-sm">
      {(["p5", "median", "p95"] as const).map((k) => (
        <div key={k} className="rounded-lg bg-white/5 px-2 py-2">
          <dt className="text-[11px] uppercase tracking-wide text-ink-3">{k === "median" ? "Median" : k === "p5" ? "Lowest 5%" : "Highest 5%"}</dt>
          <dd className="mt-0.5 font-mono">{fmt(stats[k], stats.unit)}</dd>
        </div>
      ))}
    </dl>
  );
}

function Section({ title, children, aside }: { title: string; children: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <section className="border-t border-line px-4 py-4">
      <div className="mb-2 flex items-center gap-2">
        <h2 className="text-xs font-medium uppercase tracking-wide text-ink-3">{title}</h2>
        <div className="ml-auto">{aside}</div>
      </div>
      {children}
    </section>
  );
}

function Assistant({ m, layer, date }: { m: Manifest; layer: LayerInfo; date: string }) {
  const [status, setStatus] = useState<AssistantStatus | null>(null);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [answer, setAnswer] = useState<AssistantAnswer | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    fetchAssistantStatus().then(setStatus).catch(() => setStatus(null));
  }, []);
  const suggestions =
    m.kind === "showcase"
      ? ["What changed here, and when?", "How good is the AI Model compared with the Baseline?", "What does the layer on screen show?"]
      : ["What changed here, and when?", "What does the layer on screen show?", "What should I check to confirm this?"];
  const ask = (question: string) => {
    if (!question.trim()) return;
    setBusy(true);
    setErr(null);
    setAnswer(null);
    askAssistant({ study_id: m.id, question, layer: layer.id, date })
      .then(setAnswer)
      .catch((e) => setErr(e.message))
      .finally(() => setBusy(false));
  };
  if (status && !status.configured) return <p className="text-sm text-ink-2">The Assistant is not set up on this server (GEMINI_API_KEY).</p>;
  return (
    <div>
      <div className="flex flex-wrap gap-1.5">
        {suggestions.map((s) => (
          <button key={s} type="button" disabled={busy} onClick={() => { setQ(s); ask(s); }}
            className="cursor-pointer rounded-full border border-line px-3 py-1 text-xs text-ink-2 transition-colors duration-200 hover:text-ink disabled:opacity-50">
            {s}
          </button>
        ))}
      </div>
      <form className="mt-2 flex gap-2" onSubmit={(e) => { e.preventDefault(); ask(q); }}>
        <label className="sr-only" htmlFor="ask">Ask about this study</label>
        <input id="ask" value={q} onChange={(e) => setQ(e.target.value)} maxLength={600} placeholder="Ask about this study…"
          className="h-10 min-w-0 flex-1 rounded-lg border border-line bg-black/30 px-3 text-sm text-ink placeholder:text-ink-3" />
        <button type="submit" disabled={busy || q.trim().length < 2} className="h-10 cursor-pointer rounded-lg bg-white/10 px-4 text-sm transition-colors duration-200 hover:bg-white/20 disabled:opacity-40">
          Ask
        </button>
      </form>
      <div aria-live="polite">
        {busy && (
          <div className="mt-3 text-sm text-ink-2">
            <div className="busy-bar mb-2 h-0.5" aria-hidden />
            Reading this study&rsquo;s numbers and writing an answer. This can take up to a minute.
          </div>
        )}
        {err && <p className="mt-3 text-sm text-drop">{err}</p>}
        {answer && (
          <div className="mt-3 rounded-lg border border-line bg-white/[0.03] p-3">
            <p className="mb-2 text-[11px] uppercase tracking-wide text-ink-3">AI-generated · {answer.model} · from {answer.grounded_on.join(", ")}</p>
            <div className="whitespace-pre-line text-sm leading-relaxed text-ink">{answer.text.replace(/\*\*(.+?)\*\*/g, "$1").replace(/\*(.+?)\*/g, "$1")}</div>
          </div>
        )}
      </div>
    </div>
  );
}

type Tab = "ask" | "layers" | "more";

/** "place": the decision view of a place (map and questions only). "research": layers, charts and data first. */
export default function StudyPage({ id, mode = "research" }: { id: string; mode?: "place" | "research" }) {
  const place = mode === "place";
  const reduced = useReducedMotion() ?? false;
  const [m, setM] = useState<Manifest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [layerId, setLayerId] = useState<string | null>(null);
  const [dateSel, setDate] = useState<string | null>(null);
  const [opacity, setOpacity] = useState(0.85);
  const [compare, setCompare] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [probe, setProbe] = useState<{ lon: number; lat: number } | null>(null);
  const [stats, setStats] = useState<LayerStats | null>(null);
  const [variable, setVariable] = useState<string | null>(null);
  const [series, setSeries] = useState<Timeseries | null>(null);
  const [seriesErr, setSeriesErr] = useState<string | null>(null);
  const [view3d, setView3d] = useState(false);
  const [terrain, setTerrain] = useState(true);
  const [meta, setMeta] = useState<TerrainMeta | null>(null);
  const [k, setK] = useState(2);
  const [kd, setKd] = useState(2000);
  const [drape, setDrape] = useState(false); // displacement colours by default; the drape is an option
  const [reportBusy, setReportBusy] = useState(false);
  const [reportErr, setReportErr] = useState<string | null>(null);
  // Questions and answers: the panel is controlled from here so the map (bubble, drawn items) follows it.
  const answers = useAnswers(id, probe);
  const doc = answers.doc;
  const [tabSel, setTabSel] = useState<Tab | null>(null);
  // ?role=&q= make a place view shareable ("the home buyer's view of this question").
  const [initial] = useState(() => {
    const p = new URLSearchParams(typeof window === "undefined" ? "" : window.location.search);
    return { role: p.get("role"), q: p.get("q") };
  });
  const [role, setRole] = useState<string | null>(initial.role ?? (place ? null : "all")); // null: not chosen yet
  const [openSel, setOpenSel] = useState<string | null | undefined>(initial.q ?? undefined); // undefined: the first question
  const [layerTouched, setLayerTouched] = useState(false);
  const [focus, setFocus] = useState<{ lon: number; lat: number; zoom: number; key: number } | null>(null);
  const [scrollKey, setScrollKey] = useState(0);
  const [featRes, setFeatRes] = useState<{ key: string; fc: AnswerFeatures } | null>(null);
  const [legendOpen, setLegendOpen] = useState(false); // phones only; always shown from the sm breakpoint

  useEffect(() => {
    const ctl = new AbortController();
    fetchManifest(id, ctl.signal)
      .then((mm) => {
        setM(mm);
        const l = defaultLayer(mm.layers, mm.kind);
        setLayerId(l.id);
        setDate(l.dates[l.dates.length - 1]);
        setVariable(defaultSeries(mm.series.map((s) => s.variable), mm.lens));
        setView3d(false);
      })
      .catch((e) => e.name !== "AbortError" && setError(e.message));
    return () => ctl.abort();
  }, [id]);

  const openId = openSel === undefined ? (doc?.questions[0]?.id ?? null) : openSel;
  const openQ: Question | null = doc?.questions.find((q) => q.id === openId) ?? null;
  const tab: Tab = place ? "ask" : (tabSel ?? "layers");
  const asking = !!doc && (place || tab === "ask"); // the map follows the questions
  const autoLayer = asking && !layerTouched && openQ?.layer ? openQ.layer : null;
  const layer = m?.layers.find((l) => l.id === (autoLayer ?? layerId)) ?? m?.layers.find((l) => l.id === layerId) ?? null;
  // The open question's answer map has its own (single) date; show the nearest date the layer has.
  const date = layer && dateSel ? (layer.dates.includes(dateSel) ? dateSel : nearest(layer.dates, dateSel)) : dateSel;
  const hasTerrain = !!m?.terrain;

  useEffect(() => {
    if (!place) return;
    const p = new URLSearchParams();
    if (role && role !== "all") p.set("role", role);
    if (openId) p.set("q", openId);
    const qs = p.toString();
    window.history.replaceState(window.history.state, "", qs ? `?${qs}` : window.location.pathname);
  }, [place, role, openId]);

  const featKey = openQ?.features ? `${id}|${openQ.id}` : null;
  useEffect(() => {
    if (!featKey || !openQ) return;
    const ctl = new AbortController();
    fetchFeatures(id, openQ.id, ctl.signal).then((fc) => setFeatRes({ key: featKey, fc })).catch(() => {});
    return () => ctl.abort();
  }, [id, featKey, openQ]);
  const features = asking && featKey && featRes?.key === featKey && layer?.id === openQ?.layer ? featRes.fc : null;

  useEffect(() => {
    if (!hasTerrain) return;
    getJson<TerrainMeta>(`/terrain/${id}/meta.json`).then(setMeta).catch(() => setMeta(null));
  }, [id, hasTerrain]);

  useEffect(() => {
    if (!layer || !date || layer.colormap === "rgb") return;
    const ctl = new AbortController();
    fetchStats(id, layer.id, date, ctl.signal).then(setStats).catch(() => {});
    return () => ctl.abort();
  }, [id, layer, date]);

  useEffect(() => {
    if (!m || !variable) return;
    const ctl = new AbortController();
    const req = probe ? fetchPointSeries(id, variable, probe.lon, probe.lat, ctl.signal) : fetchAreaSeries(id, variable, boxPolygon(m.bbox), ctl.signal);
    req.then((s) => {
      setSeries(s);
      setSeriesErr(null);
    }).catch((e) => {
      if (e.name !== "AbortError") {
        setSeries(null);
        setSeriesErr(e.message);
      }
    });
    return () => ctl.abort();
  }, [id, m, variable, probe]);

  // Time-lapse.
  useEffect(() => {
    if (!playing || !layer) return;
    const t = setInterval(() => setDate((d) => {
      const i = layer.dates.indexOf(d ?? "");
      return layer.dates[(i + 1) % layer.dates.length];
    }), 1400);
    return () => clearInterval(t);
  }, [playing, layer]);

  const chooseLayer = useCallback((l: LayerInfo) => {
    setLayerTouched(true); // a layer picked by hand wins over the open question's map
    setLayerId(l.id);
    setDate((d) => nearest(l.dates, d ?? l.dates[l.dates.length - 1]));
    setCompare(null);
    setPlaying(false);
  }, []);

  const groups = useMemo(() => {
    if (!m) return [];
    return KIND_ORDER.map((k) => ({ kind: k, layers: m.layers.filter((l) => l.kind === k) })).filter((g) => g.layers.length);
  }, [m]);

  if (error)
    return (
      <main className="grid h-dvh place-items-center bg-bg p-6 text-center">
        <div>
          <p className="text-ink">{error}</p>
          <Link href="/" className="mt-3 inline-block text-accent underline underline-offset-2">Back to all places</Link>
        </div>
      </main>
    );
  const goTo = (s: { lon: number; lat: number }, zoom = 13) => {
    setProbe(s);
    setFocus({ ...s, zoom, key: Date.now() });
  };
  const openQuestion = (q: Question | null) => {
    setOpenSel(q ? q.id : null);
    const l = q?.layer ? m?.layers.find((x) => x.id === q.layer) : null;
    if (l) {
      chooseLayer(l);
      setLayerTouched(false);
      setView3d(false);
    }
  };

  if (!m || !layer || !date)
    return (
      <main className="grid h-dvh place-items-center bg-bg" aria-busy="true">
        <div className="w-48"><div className="busy-bar h-0.5" /></div>
      </main>
    );

  const lens = m.lens ? LENSES[m.lens] : null;
  const terrainDates = meta?.dates ?? [];
  const date3d = terrainDates.length ? nearest(terrainDates, date) : null;
  const canCompare = layer.dates.length > 1 && !view3d;
  const varUnit = m.series.find((s) => s.variable === variable)?.unit ?? "";
  const shownStats = stats && stats.layer === layer.id && stats.date === date ? stats : null;

  return (
    <main className="flex h-dvh w-full flex-col bg-bg md:flex-row">
      <div className="relative h-[52dvh] shrink-0 overflow-hidden md:h-full md:flex-1">
        {view3d && meta ? (
          <Terrain3D studyId={id} meta={meta} date={date3d} drapeUrl={drape ? layerPreviewUrl(id, layer.id, date, 1536) : null} k={k} kd={kd} onPick={(lon, lat) => setProbe({ lon, lat })} reduced={reduced} />
        ) : (
          <StudyMap studyId={id} bbox={m.bbox} layerId={layer.id} date={date} opacity={opacity} compareDate={compare} probe={probe}
            onPick={(lon, lat) => setProbe({ lon, lat })} terrain={terrain}
            features={features} hideRaster={!!features && openQ?.features === "lines"} focus={focus}
            popup={asking && probe ? (
              <SpotBubble spot={answers.spot} busy={answers.spotBusy} err={answers.spotErr} openId={openId}
                onDetails={() => { setTabSel("ask"); setScrollKey((k) => k + 1); }} onClose={() => setProbe(null)} />
            ) : null} />
        )}

        {!view3d && (
          <div className="pointer-events-none absolute inset-x-2 top-2 z-10 flex flex-col gap-2 sm:inset-x-3 sm:top-3 md:right-auto md:w-[360px]">
            <div className="pointer-events-auto flex gap-2">
              {asking && (
                <div className="min-w-0 flex-1">
                  <PlaceSearch studyId={id} placeholder={m.lens === "subsidence" ? "Find your neighbourhood…" : "Find a village or town…"} onPick={(p) => goTo(p)} />
                </div>
              )}
              <button type="button" onClick={() => setLegendOpen((v) => !v)} aria-expanded={legendOpen} aria-controls="map-legend"
                className={`panel h-11 shrink-0 cursor-pointer px-3 text-xs text-ink-2 sm:hidden ${asking ? "" : "ml-auto"}`}>
                Key {legendOpen ? "▴" : "▾"}
              </button>
            </div>
            <div id="map-legend" className={`panel pointer-events-auto px-3 py-2 sm:block sm:py-2.5 ${legendOpen ? "block" : "hidden"}`}>
              <div className="flex items-start gap-2">
                <p className="hidden min-w-0 flex-1 text-[13px] font-medium leading-snug text-ink sm:block">{layer.label}</p>
                <p className="min-w-0 flex-1 truncate text-xs font-medium text-ink sm:hidden">{layer.label}</p>
                {place ? (
                  <Link href={`/study/${id}`} className="shrink-0 text-[11px] text-ink-3 underline underline-offset-2 hover:text-ink">radar layers</Link>
                ) : (
                  <button type="button" onClick={() => setTabSel("layers")} className="shrink-0 cursor-pointer text-[11px] text-ink-3 underline underline-offset-2 hover:text-ink">change map</button>
                )}
              </div>
              <div className="mt-2"><Legend layer={layer} /></div>
              {features && <p className="mt-2 text-[11px] text-ink-3">{openQ?.features === "lines" ? "Lines are drawn by class; hover one for its name." : "Points are ranked; hover one for its name."}</p>}
            </div>
          </div>
        )}

        <div className="absolute inset-x-2 bottom-2 z-10 sm:inset-x-3 sm:bottom-3">
          <div className="panel mx-auto max-w-3xl px-3 py-2">
            {layer.dates.length > 1 && (
            <div className="flex items-center gap-2">
              {layer.dates.length > 2 && (
                <button type="button" onClick={() => { setCompare(null); setPlaying((p) => !p); }} aria-label={playing ? "Pause the time-lapse" : "Play the time-lapse"}
                  className="grid h-9 w-9 shrink-0 cursor-pointer place-items-center rounded-lg bg-white/10 transition-colors duration-200 hover:bg-white/20">
                  {playing ? "❚❚" : "▶"}
                </button>
              )}
              <div className="relative min-w-0 flex-1 overflow-x-auto">
                <ol className="flex min-w-max items-end gap-1 py-1" aria-label="Pass dates">
                  {layer.dates.map((d) => {
                    const isEvent = !!m.event_date && layer.dates.some((x) => x < m.event_date!) && layer.dates.find((x) => x >= m.event_date!) === d;
                    return (
                      <li key={d}>
                        <button type="button" onClick={() => { setPlaying(false); setDate(d); }} aria-current={d === date ? "date" : undefined}
                          className={`relative h-9 cursor-pointer rounded-md px-2 text-xs transition-colors duration-200 ${d === date ? "bg-accent text-black" : d === compare ? "bg-white/25 text-ink" : "text-ink-2 hover:bg-white/10"}`}>
                          {shortDate(d)}
                          {isEvent && <span className="absolute -top-1 left-1/2 h-1.5 w-1.5 -translate-x-1/2 rounded-full bg-drop" title={`First Pass after the event (${longDate(m.event_date!)})`} />}
                        </button>
                      </li>
                    );
                  })}
                </ol>
              </div>
            </div>
            )}
            <div className={`${layer.dates.length > 1 ? "mt-1" : ""} flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-3`}>
              {layer.dates.length <= 1 && <span className="text-ink-2">{longDate(layer.dates[0])}</span>}
              {m.event_date && <span><span className="mr-1 inline-block h-1.5 w-1.5 rounded-full bg-drop align-middle" />event {longDate(m.event_date)}</span>}
              {canCompare && !place && (
                <label className="flex cursor-pointer items-center gap-1.5">
                  <input type="checkbox" checked={!!compare} onChange={(e) => { setPlaying(false); setCompare(e.target.checked ? (layer.dates.find((d) => d < date) ?? layer.dates[0]) : null); }} />
                  Before/after swipe
                </label>
              )}
              {compare && (
                <label className="flex items-center gap-1.5">before:
                  <select value={compare} onChange={(e) => setCompare(e.target.value)} className="rounded border border-line bg-black/40 px-1 py-0.5 text-ink">
                    {layer.dates.filter((d) => d !== date).map((d) => <option key={d} value={d}>{shortDate(d)}</option>)}
                  </select>
                </label>
              )}
              {!view3d && (
                <label className="flex cursor-pointer items-center gap-1.5">
                  <input type="checkbox" checked={terrain} onChange={(e) => setTerrain(e.target.checked)} />
                  3D terrain
                </label>
              )}
              {hasTerrain && meta && !place && (
                <label className="flex cursor-pointer items-center gap-1.5" title="Terrain and line-of-sight ground motion from this study's own data, with exaggeration sliders">
                  <input type="checkbox" checked={view3d} onChange={(e) => { setView3d(e.target.checked); setCompare(null); }} />
                  Ground-motion 3D
                </label>
              )}
              {!view3d && (
                <label className="hidden items-center gap-1.5 sm:flex">opacity
                  <input type="range" min={0.1} max={1} step={0.05} value={opacity} onChange={(e) => setOpacity(Number(e.target.value))} aria-label="Layer opacity" className="w-20" />
                </label>
              )}
            </div>
            {view3d && meta && (
              <div className="mt-2 grid grid-cols-1 gap-x-4 gap-y-1 text-xs text-ink-2 sm:grid-cols-3">
                <label className="flex items-center gap-2">terrain ×{k}
                  <input type="range" min={1} max={6} step={0.5} value={k} onChange={(e) => setK(Number(e.target.value))} className="min-w-0 flex-1" aria-label={`Terrain exaggeration, k = ${k}`} />
                </label>
                <label className="flex items-center gap-2">motion ×{kd.toLocaleString("en-GB")}
                  <input type="range" min={0} max={10000} step={500} value={kd} onChange={(e) => setKd(Number(e.target.value))} className="min-w-0 flex-1" aria-label={`Ground-motion exaggeration, k = ${kd}`} />
                </label>
                <label className="flex cursor-pointer items-center gap-1.5">
                  <input type="checkbox" checked={drape} onChange={(e) => setDrape(e.target.checked)} />
                  drape the map layer {date3d && date3d !== date ? `(motion: ${shortDate(date3d)})` : ""}
                </label>
              </div>
            )}
          </div>
        </div>
      </div>

      <motion.aside initial={reduced ? false : { opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.5, ease: [0.2, 0.8, 0.2, 1] }}
        className="min-h-0 flex-1 overflow-y-auto border-line bg-panel-solid md:w-[420px] md:flex-none md:border-l" aria-label="Study details">
        {place ? (
          <header className="px-4 pb-3 pt-4">
            <Link href="/" className="text-xs text-ink-3 transition-colors duration-200 hover:text-ink">← All places</Link>
            <div className="mt-2 flex items-center gap-2 text-xs">
              {lens && <span className="font-medium uppercase tracking-wide" style={{ color: lens.color }}>{lens.label}</span>}
              <span className="text-ink-3">· radar of {shortDate(m.passes[0].date)} to {longDate(m.passes[m.passes.length - 1].date)}</span>
            </div>
            <h1 className="mt-1 font-display text-[26px] font-medium leading-[1.1] tracking-tight">{m.name}</h1>
            <div className="mt-3 flex flex-wrap gap-2">
              <button type="button" disabled={reportBusy} onClick={() => { setReportBusy(true); setReportErr(null); downloadReport(id, m.name).catch((e) => setReportErr(e.message)).finally(() => setReportBusy(false)); }}
                className="h-9 cursor-pointer rounded-lg border border-line px-3 text-sm text-ink-2 transition-colors duration-200 hover:text-ink disabled:opacity-50">
                {reportBusy ? "Making the PDF…" : "Download the report (PDF)"}
              </button>
              <Link href={`/study/${id}`} className="flex h-9 items-center rounded-lg border border-line px-3 text-sm text-ink-2 transition-colors duration-200 hover:text-ink">Research view →</Link>
            </div>
            {reportErr && <p className="mt-2 text-sm text-drop" role="alert">{reportErr}</p>}
          </header>
        ) : (
        <header className="px-4 pb-4 pt-4">
          <Link href="/explore" className="text-xs text-ink-3 transition-colors duration-200 hover:text-ink">← Research explorer</Link>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
            {lens && <span className="font-medium uppercase tracking-wide" style={{ color: lens.color }}>{lens.label}</span>}
            <span className="rounded bg-white/10 px-1.5 py-0.5 text-ink-2">{m.kind === "showcase" ? "Showcase Site" : "Analysis"}</span>
            <span className="text-ink-3">{m.passes.length} Passes · {shortDate(m.passes[0].date)} to {longDate(m.passes[m.passes.length - 1].date)}</span>
          </div>
          <h1 className="mt-1 font-display text-2xl font-medium leading-tight tracking-tight">{m.name}</h1>
          <div className="mt-3 flex flex-wrap gap-2">
            <button type="button" disabled={reportBusy} onClick={() => { setReportBusy(true); setReportErr(null); downloadReport(id, m.name).catch((e) => setReportErr(e.message)).finally(() => setReportBusy(false)); }}
              className="h-9 cursor-pointer rounded-lg bg-accent px-3 text-sm font-medium text-[#04111a] transition-opacity duration-200 hover:opacity-90 disabled:opacity-50">
              {reportBusy ? "Making the PDF…" : "PDF Report"}
            </button>
            {m.kind === "showcase" && m.model_card && (
              <Link href={`/models/${m.model_card}`} className="flex h-9 items-center rounded-lg border border-line px-3 text-sm text-ink-2 transition-colors duration-200 hover:text-ink">Model card</Link>
            )}
            <Link href={`/report/${id}`} className="flex h-9 items-center rounded-lg border border-line px-3 text-sm text-ink-2 transition-colors duration-200 hover:text-ink">Print view</Link>
            {doc && <Link href={`/place/${id}`} className="flex h-9 items-center rounded-lg border border-accent/50 px-3 text-sm text-ink transition-colors duration-200 hover:bg-accent/10">Decision view →</Link>}
          </div>
          {reportErr && <p className="mt-2 text-sm text-drop" role="alert">{reportErr}</p>}
        </header>
        )}

        {!place && (
        <div role="tablist" aria-label="Study sections" className="sticky top-0 z-10 flex gap-1 border-y border-line bg-panel-solid/95 px-3 py-2 backdrop-blur">
          {([["layers", "Map layers"], ["more", "Charts and data"], ["ask", "Questions"]] as [Tab, string][])
            .filter(([t]) => t !== "ask" || doc)
            .map(([t, label]) => (
              <button key={t} type="button" role="tab" aria-selected={tab === t} onClick={() => setTabSel(t)}
                className={`h-9 flex-1 cursor-pointer rounded-lg px-2 text-[13px] transition-colors duration-200 ${tab === t ? "bg-white/10 font-medium text-ink" : "text-ink-3 hover:text-ink"}`}>
                {label}
              </button>
            ))}
        </div>
        )}

        {tab === "ask" && (
          <section className={`px-4 ${place ? "border-t border-line py-4" : "py-4"}`} role={place ? undefined : "tabpanel"} aria-label="Ask this place">
            {doc ? (
              <AskPanel doc={doc} spot={answers.spot} spotBusy={answers.spotBusy} spotErr={answers.spotErr} role={role} onRole={setRole}
                openId={openId} onOpen={openQuestion} onGo={(s) => goTo(s)} onClear={() => setProbe(null)} scrollKey={scrollKey} />
            ) : answers.settled ? (
              <p className="text-sm text-ink-2">No questions are answered for this place yet. <Link href={`/study/${id}`} className="text-accent underline underline-offset-2">Open its research view</Link>.</p>
            ) : <div className="busy-bar h-0.5" aria-hidden />}
            {place && doc && (
              <Link href={`/study/${id}`} className="mt-6 flex items-center gap-3 rounded-xl border border-line p-3 transition-colors duration-200 hover:border-white/25">
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium text-ink">See the radar behind these answers</span>
                  <span className="block text-xs text-ink-3">Every layer and date, time series, statistics and the AI Model card: the research view of this place.</span>
                </span>
                <span className="text-ink-3" aria-hidden>→</span>
              </Link>
            )}
          </section>
        )}

        {tab === "layers" && <>
        {!!m.insights?.length && (
          <Section title="Why it changed">
            <ul className="flex flex-col gap-2 text-sm leading-relaxed text-ink">
              {m.insights.map((s) => <li key={s} className="border-l-2 border-accent/60 pl-3">{s}</li>)}
            </ul>
            <p className="mt-2 text-xs text-ink-3">Measured by the pipeline, not written by AI. Radar shows that something changed; the cause is a hypothesis to check.</p>
          </Section>
        )}

        <Section title="Layers">
          <div className="flex flex-col gap-3">
            {groups.map((g) => (
              <fieldset key={g.kind}>
                <legend className="mb-1 text-[11px] text-ink-3">{KIND_LABEL[g.kind]}</legend>
                <ul className="flex flex-col gap-0.5">
                  {g.layers.map((l) => (
                    <li key={l.id}>
                      <label className={`flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-sm transition-colors duration-200 ${l.id === layer.id ? "bg-white/10 text-ink" : "text-ink-2 hover:bg-white/5"}`}>
                        <input type="radio" name="layer" checked={l.id === layer.id} onChange={() => chooseLayer(l)} className="accent-[var(--accent)]" />
                        <span className="min-w-0 flex-1 leading-snug">{l.label}</span>
                        {(l.kind === "prediction" || l.kind === "baseline") && <span className="shrink-0"><StatusBadge status={l.status} /></span>}
                        <span className="shrink-0 text-[11px] text-ink-3">{l.dates.length > 1 ? `${l.dates.length} dates` : shortDate(l.dates[0])}</span>
                      </label>
                    </li>
                  ))}
                </ul>
              </fieldset>
            ))}
          </div>
          <div className="mt-4 rounded-lg bg-white/[0.03] p-3">
            <Legend layer={layer} />
            {layer.what_this_shows && <p className="mt-2 text-sm leading-relaxed text-ink-2">{layer.what_this_shows}</p>}
          </div>
        </Section>

        <Section title={`On ${longDate(date)}`} aside={<span className="text-xs text-ink-3">whole study area</span>}>
          {layer.colormap === "rgb" ? <p className="text-sm text-ink-2">Pick a single layer to see its numbers.</p> : shownStats ? <StatsView stats={shownStats} /> : <div className="busy-bar h-0.5" />}
        </Section>

        {variable && (
          <Section
            title={probe ? "At the clicked point" : "Across the whole area"}
            aside={
              <div className="flex items-center gap-2">
                {m.series.length > 1 && (
                  <select value={variable} onChange={(e) => setVariable(e.target.value)} aria-label="Variable to chart" className="rounded border border-line bg-black/40 px-1 py-0.5 text-xs text-ink">
                    {m.series.map((s) => <option key={s.variable} value={s.variable}>{SERIES_LABEL[s.variable] ?? s.variable}</option>)}
                  </select>
                )}
                {probe && <button type="button" onClick={() => setProbe(null)} className="cursor-pointer text-xs text-ink-3 underline underline-offset-2 hover:text-ink">whole area</button>}
              </div>
            }>
            {seriesErr ? <p className="text-sm text-ink-2">{seriesErr}</p> : series ? (
              <LineChart points={series.series} unit={varUnit} label={SERIES_LABEL[variable] ?? variable} eventDate={m.event_date} currentDate={date}
                color={variable === "hh_db" ? "var(--series-hh)" : variable === "cum_disp_cm" ? "#a78bfa" : "var(--series-hv)"}
                onPick={(d) => layer.dates.includes(d) && setDate(d)} />
            ) : <div className="busy-bar h-0.5" />}
            {!probe && <p className="mt-1 text-xs text-ink-3">Click the map to see a single spot.</p>}
          </Section>
        )}

        </>}

        {tab === "more" && <>
        <Section title="Research plots" aside={<span className="text-xs text-ink-3">also in the PDF Report</span>}>
          <ResearchPlots m={m} />
        </Section>

        <Section title="What an optical satellite saw" aside={<span className="text-xs text-ink-3">NASA MODIS via GIBS</span>}>
          {(() => {
            const before = m.event_date ? addDays(m.event_date, -2) : m.passes[0].date;
            const after = m.event_date ? m.passes.find((p) => p.date >= m.event_date!)?.date ?? m.passes[m.passes.length - 1].date : m.passes[m.passes.length - 1].date;
            return (
              <>
                <div className="grid grid-cols-2 gap-2">
                  {[before, after].map((d) => (
                    <figure key={d} className="m-0">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={modisTrueColor(m.bbox, d, 600)} alt={`MODIS true colour, ${longDate(d)}`} className="w-full rounded border border-line" loading="lazy" />
                      <figcaption className="mt-1 text-[11px] text-ink-3">{longDate(d)}</figcaption>
                    </figure>
                  ))}
                </div>
                <p className="mt-2 text-xs leading-relaxed text-ink-2">Optical images {m.event_date ? "around the event" : "at the start and end"}. Clouds, smoke and night hide the ground from optical sensors; NISAR&rsquo;s radar sees through them.</p>
              </>
            );
          })()}
        </Section>

        <Section title="Assistant" aside={<StatusBadge status="prototype" />}>
          <Assistant m={m} layer={layer} date={date} />
        </Section>

        <Section title="Data">
          <p className="text-sm text-ink-2">
            {m.passes.length} NISAR Passes, Stack {[...new Set(m.passes.map((p) => p.stack))].join(", ")}, from the{" "}
            {[...new Set(m.passes.map((p) => p.collection))].join(" and ")} collections (calibrated; BETA never used).
          </p>
          {m.quality?.notes?.length ? <ul className="mt-2 list-disc pl-5 text-xs text-ink-3">{groupNotes(m.quality.notes).map((n) => <li key={n}>{n}</li>)}</ul> : null}
          <details className="mt-2 text-xs">
            <summary className="cursor-pointer text-ink-2">Granules (open in ASF Vertex)</summary>
            <ul className="mt-2 flex flex-col gap-1">
              {m.passes.map((p) => (
                <li key={p.date}>
                  <span className="text-ink-3">{p.date} · </span>
                  {p.granules.map((g) => (
                    <a key={g} href={vertexUrl(g)} target="_blank" rel="noreferrer" className="mr-2 break-all text-ink-2 underline underline-offset-2 hover:text-ink">{g.length > 48 ? g.slice(0, 46) + "…" : g}</a>
                  ))}
                </li>
              ))}
            </ul>
          </details>
          <p className="mt-3 text-xs text-ink-3">
            New to radar? <a className="underline underline-offset-2" href="https://www.earthdata.nasa.gov/learn/earth-observation-data-basics/sar" target="_blank" rel="noreferrer">NASA&rsquo;s introduction to SAR</a>
            {" · "}<a className="underline underline-offset-2" href="https://nisar.jpl.nasa.gov/applications/societal-benefit/" target="_blank" rel="noreferrer">Who uses NISAR data</a>
          </p>
        </Section>
        </>}
      </motion.aside>
    </main>
  );
}

