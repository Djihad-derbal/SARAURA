"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import SiteNav from "@/components/SiteNav";
import { fetchShowcaseRequests, fetchSites, layerPreviewUrl, longDate, postShowcaseRequest, shortDate, type Lens, type RequestedPlace, type SiteSummary } from "@/lib/api";
import { LENSES } from "@/lib/style";
import Ambience from "./Ambience";
import type { GlobeFocus, GlobeMarker } from "./Globe3D";

const Globe3D = dynamic(() => import("./Globe3D"), { ssr: false });

const EASE = [0.2, 0.8, 0.2, 1] as const;
const TEAL = "#2dd4bf";
const placeName = (s: SiteSummary) => s.name.split(",")[0].split("(")[0].trim();
const centre = (s: SiteSummary) => ({ lon: (s.bbox[0] + s.bbox[2]) / 2, lat: (s.bbox[1] + s.bbox[3]) / 2 });
const fmtPoint = (lat: number, lon: number) => `${Math.abs(lat).toFixed(2)}° ${lat >= 0 ? "N" : "S"}, ${Math.abs(lon).toFixed(2)}° ${lon >= 0 ? "E" : "W"}`;

/** What a requested study could watch for, in plain words. */
const REQUEST_LENSES: { id: Lens | "other"; label: string }[] = [
  { id: "wildfire", label: "Fire" }, { id: "subsidence", label: "Sinking ground" }, { id: "earthquake", label: "Earthquake" },
  { id: "volcano", label: "Volcano" }, { id: "wetland", label: "Floods" }, { id: "farming", label: "Crops" }, { id: "other", label: "Something else" },
];

type Persona = { id: string; label: string };

/** The decisions view of a place, opened for a persona on its first question there. */
function placeHref(s: SiteSummary, persona: string | null) {
  if (!s.decide) return `/study/${s.id}`;
  const r = persona ? s.decide.roles.find((x) => x.id === persona) : null;
  return `/place/${s.id}${r ? `?role=${r.id}&q=${r.first}` : ""}`;
}

// ---------------------------------------------------------------- the picked place, in the middle of the screen

function PlaceCard({ s, persona, ok, onClose, onStep }: { s: SiteSummary; persona: string | null; ok: boolean; onClose: () => void; onStep: (d: 1 | -1) => void }) {
  const firstId = persona && ok ? s.decide?.roles.find((r) => r.id === persona)?.first : s.decide?.questions.find((q) => q.layer)?.id;
  const q = s.decide?.questions.find((x) => x.id === firstId) ?? null;
  const layer = q?.layer ?? s.decide?.cover_layer ?? null;
  const lens = LENSES[s.lens];
  return (
    <motion.section key={s.id} aria-label={`${placeName(s)}: details`}
      initial={{ opacity: 0, y: 24, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 16 }} transition={{ duration: 0.45, ease: EASE }}
      className="absolute inset-x-3 bottom-3 z-30 overflow-hidden rounded-2xl border bg-panel-solid/90 shadow-[0_30px_80px_-20px_rgba(0,0,0,0.8)] backdrop-blur-md md:bottom-5 md:left-1/2 md:right-auto md:w-[460px] md:-translate-x-1/2"
      style={{ borderColor: `color-mix(in srgb, ${lens.color} 45%, transparent)` }}>
      <div className="h-1" style={{ background: `linear-gradient(90deg, ${lens.color}, transparent)` }} aria-hidden />
      <div className="p-4">
        <div className="flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <p className="font-space text-[10.5px] font-bold uppercase tracking-[0.22em]" style={{ color: lens.color }}>{lens.label} · Showcase area</p>
            <h2 className="mt-1 font-display text-[22px] font-semibold leading-tight tracking-tight text-ink">{placeName(s)}</h2>
            {s.hook && <p className="mt-0.5 text-[13px] text-ink-2">{s.hook}</p>}
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <button type="button" onClick={() => onStep(-1)} aria-label="Previous showcase" className="grid h-8 w-8 cursor-pointer place-items-center rounded-lg border border-line text-ink-2 hover:text-ink">‹</button>
            <button type="button" onClick={() => onStep(1)} aria-label="Next showcase" className="grid h-8 w-8 cursor-pointer place-items-center rounded-lg border border-line text-ink-2 hover:text-ink">›</button>
            <button type="button" onClick={onClose} aria-label="Close" className="grid h-8 w-8 cursor-pointer place-items-center rounded-lg text-ink-3 hover:text-ink">✕</button>
          </div>
        </div>

        {layer && s.decide && (
          <figure className="relative mt-3 overflow-hidden rounded-xl border border-line bg-black/60">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={layerPreviewUrl(s.id, layer, s.decide.date, 720)} alt={`Answer map: ${q?.title ?? "first question"}`} className="h-36 w-full object-cover sm:h-44" />
            <figcaption className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent px-3 pb-2 pt-6 text-[11px] text-white/85">
              Answer map · radar of {longDate(s.decide.date)}
            </figcaption>
          </figure>
        )}

        {q ? (
          <div className="mt-3">
            <p className="text-[13px] font-medium text-ink">{q.title}</p>
            <p className="mt-1 line-clamp-3 text-[13px] leading-snug text-ink-2">{q.headline}</p>
          </div>
        ) : s.headline && <p className="mt-3 text-[13px] leading-snug text-ink-2">{s.headline}</p>}

        <dl className="mt-3 grid grid-cols-3 gap-px overflow-hidden rounded-xl border border-line bg-line text-center">
          {[[String(s.passes), "radar passes"], [`${shortDate(s.first)} – ${shortDate(s.last)}`, "watched"], [String(s.decide?.questions.length ?? 0), "questions"]].map(([v, l]) => (
            <div key={l} className="bg-panel-solid px-2 py-2">
              <dd className="font-space text-[13px] font-bold text-ink">{v}</dd>
              <dt className="text-[10.5px] text-ink-3">{l}</dt>
            </div>
          ))}
        </dl>

        <div className="mt-3 flex flex-wrap gap-2">
          {s.decide && (
            <Link href={placeHref(s, ok ? persona : null)} className="flex h-10 flex-1 items-center justify-center gap-1.5 rounded-xl px-4 text-[13.5px] font-semibold text-[#04111a] transition-all duration-200 hover:brightness-110"
              style={{ background: lens.color }}>
              {persona && ok ? "See my questions" : "Open the decisions"} <span aria-hidden>→</span>
            </Link>
          )}
          <Link href={`/study/${s.id}`} className="flex h-10 items-center rounded-xl border border-line px-4 text-[13.5px] text-ink-2 transition-colors duration-200 hover:text-ink">Research view</Link>
        </div>
        {persona && !ok && <p className="mt-2 text-[12px] text-ink-3">This place has no questions for your persona yet. It still answers others.</p>}
      </div>
    </motion.section>
  );
}

// ---------------------------------------------------------------- asking for a new showcase area

function RequestPanel({ point, persona, onDone, onCancel, onSent }: {
  point: { lat: number; lon: number } | null; persona: string | null;
  onDone: () => void; onCancel: () => void; onSent: (r: RequestedPlace) => void;
}) {
  const [name, setName] = useState("");
  const [lens, setLens] = useState<Lens | "other" | null>(null);
  const [why, setWhy] = useState("");
  const [contact, setContact] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [sent, setSent] = useState<RequestedPlace | null>(null);
  const missing = !point ? "Click the Earth to choose the spot." : !lens ? "Choose what the study should watch for." : name.trim().length < 2 ? "Name the place." : null;
  const send = () => {
    if (missing || !point || !lens) { setErr(missing); return; }
    setBusy(true);
    setErr(null);
    postShowcaseRequest({ name: name.trim(), lon: point.lon, lat: point.lat, lens, role: persona, why: why.trim(), contact: contact.trim() })
      .then((r) => { setSent(r); onSent(r); }).catch((e) => setErr(e.message)).finally(() => setBusy(false));
  };
  if (sent) {
    return (
      <div aria-live="polite">
        <p className="font-space text-[11px] font-bold uppercase tracking-[0.22em] text-accent">Requested</p>
        <p className="mt-2 font-display text-xl font-semibold text-ink">{sent.name} is on the list</p>
        <p className="mt-1 text-[13px] leading-snug text-ink-2">It now shows on the globe as a requested place. The team reviews requests and builds the ones the radar covers well into Showcase areas.</p>
        <div className="mt-4 flex gap-2">
          <button type="button" onClick={onDone} className="h-10 flex-1 cursor-pointer rounded-xl bg-accent text-[13.5px] font-semibold text-[#04111a]">Back to the showcases</button>
        </div>
      </div>
    );
  }
  return (
    <div>
      <button type="button" onClick={onCancel} className="cursor-pointer text-xs text-ink-3 hover:text-ink">← Showcase areas</button>
      <p className="mt-3 font-space text-[11px] font-bold uppercase tracking-[0.22em] text-accent">Request a showcase area</p>
      <p className="mt-1 text-[13px] leading-snug text-ink-2">Tell us where the radar should be studied next.</p>

      <ol className="mt-4 flex flex-col gap-4">
        <li>
          <p className="text-[13px] font-medium text-ink">1. Click the Earth where you want it</p>
          <p className={`mt-1 rounded-lg border px-3 py-2 text-[12.5px] ${point ? "border-accent/50 bg-accent/10 text-ink" : "border-dashed border-line text-ink-3"}`}>
            {point ? fmtPoint(point.lat, point.lon) : "No spot yet: drag to turn the Earth, then click."}
          </p>
        </li>
        <li>
          <p className="text-[13px] font-medium text-ink">2. What should it watch for?</p>
          <div className="mt-1.5 flex flex-wrap gap-1.5" role="radiogroup" aria-label="What to watch for">
            {REQUEST_LENSES.map((l) => (
              <button key={l.id} type="button" role="radio" aria-checked={lens === l.id} onClick={() => setLens(l.id)}
                className={`h-8 cursor-pointer rounded-full border px-3 text-[12.5px] transition-colors duration-200 ${lens === l.id ? "border-accent bg-accent/15 text-ink" : "border-line text-ink-2 hover:text-ink"}`}>
                {l.id !== "other" && <span className="mr-1.5 inline-block h-2 w-2 rounded-full align-middle" style={{ background: LENSES[l.id].color }} aria-hidden />}
                {l.label}
              </button>
            ))}
          </div>
        </li>
        <li>
          <label htmlFor="req-name" className="text-[13px] font-medium text-ink">3. Name the place</label>
          <input id="req-name" value={name} maxLength={80} onChange={(e) => setName(e.target.value)} placeholder="The hills above Béjaïa"
            className="mt-1.5 h-10 w-full rounded-xl border border-line bg-bg/60 px-3 text-sm text-ink placeholder:text-ink-3 focus:border-accent/60 focus:outline-none" />
        </li>
        <li>
          <label htmlFor="req-why" className="text-[13px] font-medium text-ink">Why? <span className="font-normal text-ink-3">(optional)</span></label>
          <input id="req-why" value={why} maxLength={400} onChange={(e) => setWhy(e.target.value)} placeholder="Which roads to close this winter"
            className="mt-1.5 h-10 w-full rounded-xl border border-line bg-bg/60 px-3 text-sm text-ink placeholder:text-ink-3 focus:border-accent/60 focus:outline-none" />
        </li>
        <li>
          <label htmlFor="req-contact" className="text-[13px] font-medium text-ink">How can we reach you? <span className="font-normal text-ink-3">(optional, kept private)</span></label>
          <input id="req-contact" value={contact} maxLength={200} onChange={(e) => setContact(e.target.value)} placeholder="Name and organisation"
            className="mt-1.5 h-10 w-full rounded-xl border border-line bg-bg/60 px-3 text-sm text-ink placeholder:text-ink-3 focus:border-accent/60 focus:outline-none" />
        </li>
      </ol>
      <button type="button" onClick={send} disabled={busy}
        className="mt-5 h-11 w-full cursor-pointer rounded-xl bg-accent text-[14px] font-semibold text-[#04111a] shadow-[0_0_30px_-8px_var(--glow)] transition-all duration-200 hover:brightness-110 disabled:opacity-50">
        {busy ? "Sending…" : "Request this showcase"}
      </button>
      {(err || missing) && <p className={`mt-2 text-[12px] ${err ? "text-drop" : "text-ink-3"}`} role={err ? "alert" : undefined}>{err ?? missing}</p>}
      <p className="mt-3 text-[11px] text-ink-3">Saved for the SARAURA team. Nothing is emailed or shared.</p>
    </div>
  );
}

// ---------------------------------------------------------------- the page

/**
 * The home page: a giant EARTH behind the planet's horizon and one call to action. It opens the explorer on the same
 * Earth: drag it, zoom it, click a pinned Showcase area to fly there. Personas on the left pick whose questions to
 * show; Showcase areas are listed on the right, where anyone can also request a new one by clicking the globe.
 */
export default function Landing() {
  const reduced = useReducedMotion() ?? false;
  const [sites, setSites] = useState<SiteSummary[] | null>(null);
  const [requested, setRequested] = useState<RequestedPlace[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [exploring, setExploring] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [persona, setPersona] = useState<string | null>(null);
  const [requesting, setRequesting] = useState(false);
  const [point, setPoint] = useState<{ lat: number; lon: number } | null>(null);

  useEffect(() => {
    fetchSites().then(setSites).catch((e) => setErr(e.message));
    fetchShowcaseRequests().then(setRequested).catch(() => {});
  }, []);
  // #explore keeps the explorer open on reload, and the browser's Back button returns to the hero.
  useEffect(() => {
    const sync = () => setExploring(window.location.hash === "#explore");
    sync();
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);
  const open = () => { window.location.hash = "explore"; setExploring(true); };
  const stopRequest = () => { setRequesting(false); setPoint(null); };
  const close = useCallback(() => {
    setSelected(null);
    setRequesting(false);
    setPoint(null);
    if (window.location.hash === "#explore") history.back(); else setExploring(false);
  }, []);
  useEffect(() => {
    if (!exploring) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (requesting) stopRequest(); else if (selected) setSelected(null); else close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [exploring, selected, requesting, close]);

  const all = useMemo(() => sites ?? [], [sites]);
  // Every persona some Showcase area answers (questions/roles.yaml, through each site's answers).
  const personas = useMemo(() => {
    const by = new Map<string, Persona>();
    for (const s of all) for (const r of s.decide?.roles ?? []) if (!by.has(r.id)) by.set(r.id, { id: r.id, label: r.label });
    return [...by.values()];
  }, [all]);
  const answers = (s: SiteSummary) => !persona || !!s.decide?.roles.some((r) => r.id === persona);
  const ordered = [...all].sort((a, b) => Number(answers(b)) - Number(answers(a))); // places that answer the persona first
  const sel = requesting ? null : all.find((s) => s.id === selected) ?? null;
  const step = (d: 1 | -1) => {
    if (!ordered.length) return;
    const i = Math.max(0, ordered.findIndex((s) => s.id === selected));
    setSelected(ordered[(i + d + ordered.length) % ordered.length].id);
  };

  const markers: GlobeMarker[] = [
    ...all.map((s) => ({ id: s.id, ...centre(s), color: LENSES[s.lens].color, label: placeName(s), dim: requesting || !answers(s) || (!!sel && sel.id !== s.id), kind: "site" as const })),
    ...(exploring ? requested.map((r) => ({ id: r.id, lat: r.lat, lon: r.lon, color: "#cbd5e1", label: `Requested · ${r.name}`, kind: "requested" as const })) : []),
    ...(requesting && point ? [{ id: "draft", lat: point.lat, lon: point.lon, color: TEAL, label: "Your spot", kind: "draft" as const }] : []),
  ];
  const focus: GlobeFocus = !exploring ? { mode: "hero" }
    : sel ? { mode: "explore", ...centre(sel), marker: sel.id, zoom: 2 }
    : requesting && point ? { mode: "explore", lat: point.lat, lon: point.lon, marker: "draft", zoom: 1.5 }
    : { mode: "explore", marker: null, zoom: 1 };
  const tint = sel ? LENSES[sel.lens].color : TEAL;

  return (
    <main className="story relative h-dvh overflow-hidden" data-theme="space">
      <Ambience theme="space" />

      {/* the giant word, behind the planet: its foot sinks under the horizon */}
      <AnimatePresence>
        {!exploring && (
          <motion.div key="earth-word" aria-hidden className="pointer-events-none fixed inset-x-0 top-[17dvh] z-0 flex justify-center sm:top-[15dvh]"
            initial={reduced ? false : { opacity: 0, y: 30, scale: 0.96 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -60, transition: { duration: 0.6, ease: EASE } }}
            transition={{ duration: 1.4, ease: EASE }}>
            <span className="earth-word select-none font-space text-[27vw] font-black leading-none tracking-[-0.02em] sm:text-[21vw] lg:text-[19vw]">EARTH</span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* the Earth: a horizon over the word, then the explorer's globe */}
      <div className={`fixed inset-0 ${exploring ? "z-10" : "pointer-events-none z-[1]"}`} aria-hidden={!exploring}>
        <Globe3D focus={focus} markers={markers} reduced={reduced} tint={tint}
          onPick={(id) => setSelected((cur) => (cur === id ? null : id))}
          onPickPoint={requesting ? (lat, lon) => setPoint({ lat, lon }) : undefined} />
      </div>

      <div className="absolute inset-x-0 top-0 z-40 border-b border-white/5 backdrop-blur-md" style={{ background: "color-mix(in srgb, var(--page) 55%, transparent)" }}>
        <div className="mx-auto max-w-7xl px-4 py-2.5 sm:px-6"><SiteNav active="places" floating /></div>
      </div>

      {/* hero */}
      <AnimatePresence>
        {!exploring && (
          <motion.section key="hero" className="relative z-20 flex h-dvh flex-col items-center px-4 text-center"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, transition: { duration: 0.4 } }}>
            <motion.p className="mt-[10.5dvh] flex items-center gap-2 font-space text-[11px] font-bold uppercase tracking-[0.32em] text-accent sm:text-xs"
              initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, ease: EASE }}>
              <span className="relative flex h-2 w-2"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-60 motion-reduce:hidden" /><span className="relative inline-flex h-2 w-2 rounded-full bg-accent" /></span>
              NASA-ISRO NISAR · L-band radar · 2026
            </motion.p>
            <h1 className="sr-only">Earth, through NISAR&rsquo;s eye</h1>
            <div className="mt-auto mb-[9dvh] flex flex-col items-center">
              <motion.p className="font-space text-[5.2vw] font-extrabold uppercase leading-none tracking-[0.18em] text-ink drop-shadow-[0_2px_18px_rgba(0,0,0,0.85)] sm:text-[3.2vw] lg:text-[40px]"
                initial={{ opacity: 0, y: 16, filter: "blur(6px)" }} animate={{ opacity: 1, y: 0, filter: "blur(0px)" }} transition={{ duration: 1, delay: 0.5, ease: EASE }}>
                through <span className="glow-text">NISAR&rsquo;s eye</span>
              </motion.p>
              <motion.p className="mt-4 max-w-lg text-[15px] leading-relaxed text-ink-2 drop-shadow-[0_1px_10px_rgba(0,0,0,0.9)] sm:text-base"
                initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 1, delay: 0.75 }}>
                A radar that sees through cloud, smoke and night, every 12 days. Explore the places it watches, and the decisions it helps people make.
              </motion.p>
              <motion.button type="button" onClick={open} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, delay: 0.95, ease: EASE }}
                className="mt-7 flex h-12 cursor-pointer items-center gap-2 rounded-xl bg-accent px-7 font-space text-[13px] font-bold uppercase tracking-[0.16em] text-[#04111a] shadow-[0_0_40px_-6px_var(--glow)] transition-all duration-200 hover:brightness-110">
                Explore the Earth <span aria-hidden>→</span>
              </motion.button>
              {err && <p className="mt-4 text-sm text-drop" role="alert">Could not reach the SARAURA API ({err}). Is it running?</p>}
            </div>
          </motion.section>
        )}
      </AnimatePresence>

      {/* the explorer */}
      <AnimatePresence>
        {exploring && (
          <>
            <motion.aside key="personas" aria-label="Who are you?"
              initial={reduced ? false : { opacity: 0, x: -24 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -24 }} transition={{ duration: 0.5, delay: 0.25, ease: EASE }}
              className="absolute inset-x-3 top-[62px] z-20 rounded-2xl border border-line bg-panel/80 p-3 backdrop-blur-md md:inset-x-auto md:bottom-4 md:left-4 md:top-[72px] md:w-[260px] md:overflow-y-auto md:p-4">
              <button type="button" onClick={close} className="hidden cursor-pointer text-xs text-ink-3 hover:text-ink md:block">← Back</button>
              <p className="font-space text-[11px] font-bold uppercase tracking-[0.22em] text-accent md:mt-3">Who are you?</p>
              <p className="mt-1 hidden text-[13px] leading-snug text-ink-2 md:block">Pick who you are to see the places that answer your questions.</p>
              <div className="mt-2 flex gap-1.5 overflow-x-auto pb-1 md:mt-3 md:flex-col md:overflow-visible md:pb-0" role="radiogroup" aria-label="Personas">
                <button type="button" role="radio" aria-checked={!persona} onClick={() => setPersona(null)}
                  className={`shrink-0 cursor-pointer rounded-xl border px-3 py-2 text-left text-[13px] transition-colors duration-200 ${!persona ? "border-accent bg-accent/15 text-ink" : "border-line text-ink-2 hover:text-ink"}`}>
                  Everyone
                </button>
                {personas.map((p) => (
                  <button key={p.id} type="button" role="radio" aria-checked={persona === p.id} onClick={() => setPersona(persona === p.id ? null : p.id)}
                    className={`shrink-0 cursor-pointer whitespace-nowrap rounded-xl border px-3 py-2 text-left text-[13px] transition-colors duration-200 md:whitespace-normal ${persona === p.id ? "border-accent bg-accent/15 text-ink" : "border-line text-ink-2 hover:text-ink"}`}>
                    {p.label}
                  </button>
                ))}
              </div>
            </motion.aside>

            <motion.aside key="sites" aria-label={requesting ? "Request a showcase area" : "Showcase areas"}
              initial={reduced ? false : { opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 24 }} transition={{ duration: 0.5, delay: 0.25, ease: EASE }}
              className={`absolute inset-x-3 bottom-3 z-20 max-h-[42dvh] overflow-y-auto rounded-2xl border border-line bg-panel/80 p-3 backdrop-blur-md md:inset-x-auto md:bottom-4 md:right-4 md:top-[72px] md:block md:max-h-none md:w-[340px] md:p-4 ${sel ? "hidden" : ""}`}>
              {requesting ? (
                <RequestPanel point={point} persona={persona} onCancel={stopRequest} onDone={stopRequest}
                  onSent={(r) => { setRequested((cur) => [r, ...cur]); setPoint(null); }} />
              ) : (
                <>
                  <div className="flex items-baseline justify-between">
                    <p className="font-space text-[11px] font-bold uppercase tracking-[0.22em] text-accent">Showcase areas</p>
                    <span className="text-xs text-ink-3">{all.length} places</span>
                  </div>
                  <ul className="mt-3 flex flex-col gap-2">
                    {ordered.map((s) => {
                      const on = s.id === selected;
                      const ok = answers(s);
                      return (
                        <li key={s.id}>
                          <button type="button" onClick={() => setSelected(on ? null : s.id)} aria-pressed={on}
                            className={`group block w-full cursor-pointer rounded-xl border p-3 text-left transition-all duration-200 ${on ? "border-accent/60 bg-accent/10" : "border-line bg-bg/40 hover:-translate-y-0.5 hover:border-accent/40"} ${ok ? "" : "opacity-50"}`}>
                            <span className="flex items-center gap-2">
                              <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: LENSES[s.lens].color, boxShadow: `0 0 10px ${LENSES[s.lens].color}` }} aria-hidden />
                              <span className="min-w-0 flex-1 truncate font-display text-[15px] font-medium text-ink">{placeName(s)}</span>
                              <span className="shrink-0 text-[10.5px] font-semibold uppercase tracking-wide" style={{ color: LENSES[s.lens].color }}>{LENSES[s.lens].label}</span>
                            </span>
                            {s.hook && <span className="mt-1 block text-[12.5px] leading-snug text-ink-2">{s.hook}</span>}
                            <span className="mt-1.5 block text-[11px] text-ink-3">{ok ? `${s.passes} radar passes · fly there →` : "No questions for this persona here yet"}</span>
                          </button>
                        </li>
                      );
                    })}
                    {sites === null && !err && <li><div className="busy-bar h-0.5" /></li>}
                    {err && <li className="text-sm text-drop" role="alert">Could not reach the SARAURA API ({err}).</li>}
                  </ul>
                  <div className="mt-4 rounded-xl border border-dashed border-line p-3">
                    <p className="text-[13px] font-medium text-ink">Don&rsquo;t see your area?</p>
                    <p className="mt-0.5 text-[12px] leading-snug text-ink-2">Pick a spot on the Earth and ask for it to become a showcase.{requested.length ? ` ${requested.length} place${requested.length > 1 ? "s" : ""} requested so far.` : ""}</p>
                    <button type="button" onClick={() => { setSelected(null); setRequesting(true); }}
                      className="mt-2.5 h-9 w-full cursor-pointer rounded-lg border border-accent/50 text-[13px] text-ink transition-colors duration-200 hover:bg-accent/10">
                      Request a showcase area
                    </button>
                  </div>
                </>
              )}
            </motion.aside>

            <AnimatePresence mode="wait">
              {sel && <PlaceCard key={sel.id} s={sel} persona={persona} ok={answers(sel)} onClose={() => setSelected(null)} onStep={step} />}
            </AnimatePresence>

            {!sel && (
              <motion.p key={requesting ? "hint-req" : "hint"} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ delay: 0.6 }}
                className={`pointer-events-none absolute bottom-5 left-1/2 z-20 hidden -translate-x-1/2 rounded-full border px-3 py-1.5 text-xs backdrop-blur md:block ${requesting ? "border-accent/50 bg-accent/15 text-ink" : "border-line bg-panel/70 text-ink-3"}`}>
                {requesting ? (point ? "Click again to move your spot · drag to turn" : "Click the Earth to choose the spot · drag to turn") : "Drag to turn the Earth · scroll to zoom · click a pin"}
              </motion.p>
            )}
          </>
        )}
      </AnimatePresence>
    </main>
  );
}
