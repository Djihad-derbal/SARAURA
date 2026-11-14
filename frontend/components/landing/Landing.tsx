"use client";

import { animate, motion, useInView, useMotionValueEvent, useReducedMotion, useScroll, type MotionValue } from "motion/react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState, type ComponentType, type RefObject } from "react";
import SiteNav from "@/components/SiteNav";
import { fetchSites, type SiteSummary } from "@/lib/api";
import { LENSES } from "@/lib/style";
import Ambience, { type Theme } from "./Ambience";
import type { GlobeFocus, GlobeMarker } from "./Globe3D";
import AfterFire from "./scenes/AfterFire";
import SinkingCity from "./scenes/SinkingCity";

const Globe3D = dynamic(() => import("./Globe3D"), { ssr: false });

const EASE = [0.2, 0.8, 0.2, 1] as const;
// the Earth's atmosphere takes each chapter's colour too
const TINT: Record<Theme, string> = { space: "#2dd4bf", city: "#f6a04d", fire: "#ff6a2b", forest: "#5ee08a" };
const placeName = (s: SiteSummary) => s.name.split(",")[0];
const centre = (s: SiteSummary) => ({ lon: (s.bbox[0] + s.bbox[2]) / 2, lat: (s.bbox[1] + s.bbox[3]) / 2 });

// ---------------------------------------------------------------- small pieces

function Reveal({ children, delay = 0, className = "" }: { children: React.ReactNode; delay?: number; className?: string }) {
  const reduced = useReducedMotion() ?? false;
  return (
    <motion.div className={className} initial={reduced ? false : { opacity: 0, y: 28 }} whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }} transition={{ duration: 0.7, delay, ease: EASE }}>
      {children}
    </motion.div>
  );
}

function CountUp({ value, suffix = "" }: { value: number; suffix?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const seen = useInView(ref, { once: true });
  const reduced = useReducedMotion() ?? false;
  useEffect(() => {
    const el = ref.current;
    if (!el || !seen) return;
    if (reduced) {
      el.textContent = value.toLocaleString("en-GB") + suffix;
      return;
    }
    const c = animate(0, value, { duration: 1.6, ease: EASE, onUpdate: (v) => (el.textContent = Math.round(v).toLocaleString("en-GB") + suffix) });
    return () => c.stop();
  }, [seen, value, suffix, reduced]);
  return <span ref={ref}>0{suffix}</span>;
}

// ---------------------------------------------------------------- the story's chapters

type Step = { until: number; title: string; text: (s: SiteSummary | undefined) => string };
type Chapter = {
  n: string;
  site: string;
  theme: Theme;
  kicker: string;
  title: string;
  lead: string;
  steps: Step[];
  Scene?: ComponentType<{ p: MotionValue<number>; className?: string }>;
  cta: { label: string; q: string };
  roles: { label: string; role: string; q: string }[];
};

const headline = (s: SiteSummary | undefined, q: string, fallback: string) => s?.decide?.questions.find((x) => x.id === q)?.headline ?? fallback;

const CHAPTERS: Chapter[] = [
  {
    n: "01",
    site: "mexico_city_subsidence",
    theme: "city",
    kicker: "Mexico City · ground subsidence",
    title: "A city sinking up to 30 cm a year",
    lead: "Mexico City draws its water from the clay of an old lake. The clay compacts and the ground sinks, unevenly, and uneven sinking is what cracks walls and bends Metro lines.",
    steps: [
      { until: 0.3, title: "NISAR measures, every 12 days", text: () => "28 radar Passes since November 2025 give every 80 m spot its own speed of sinking, through cloud and at night." },
      { until: 0.65, title: "The ground sinks unevenly", text: () => "Where neighbouring ground sinks at different speeds, buildings tilt. We count the years until walls reach the 1/500 crack limit, and find the Metro segments that will step first." },
      { until: 1.01, title: "The answer: where it is safe to build", text: (s) => headline(s, "m1_safe_to_build", "Each spot gets a traffic light, the reason, and the options that fit it.") },
    ],
    Scene: SinkingCity,
    cta: { label: "Is it safe to build here?", q: "m1_safe_to_build" },
    roles: [
      { label: "I'm buying a home", role: "buyer", q: "m1_safe_to_build" },
      { label: "I run Metro or canals", role: "infrastructure", q: "m4_lines_at_risk" },
    ],
  },
  {
    n: "02",
    site: "algeria_ne_wildfire",
    theme: "fire",
    kicker: "Jijel, Algeria · after the wildfires",
    title: "After the fire, before the rains",
    lead: "In August 2026 fires burned the forested hills around Jijel. Winter rain on bare, steep slopes sends mud down the gullies, onto villages and across roads.",
    steps: [
      { until: 0.3, title: "Mapped through the smoke", text: () => "NISAR's L-band radar sees the burned forest while smoke still hides it from optical satellites, so the burn map is ready the week of the fire." },
      { until: 0.72, title: "Rain finds the channels", text: (s) => headline(s, "a1_burned_slopes", "Flow paths on the terrain show which burned slopes drain towards villages.") },
      { until: 1.01, title: "What to do first", text: (s) => headline(s, "a2_roads_to_watch", "Barriers on the slopes, roads that close in heavy rain, and where to replant first.") },
    ],
    Scene: AfterFire,
    cta: { label: "Which villages are at risk?", q: "a1_burned_slopes" },
    roles: [
      { label: "Civil protection", role: "civil_protection", q: "a1_burned_slopes" },
      { label: "Forestry service", role: "forestry", q: "a3_replant_first" },
    ],
  },
  {
    n: "03",
    site: "washington_sinlahekin_wildfire",
    theme: "forest",
    kicker: "Washington, USA · the same questions, another fire",
    title: "One question file, any burned forest",
    lead: "The questions asked in Jijel ran on the Sinlahekin Fire with no new code: the same radar, the same rules, a different answer.",
    steps: [{ until: 1.01, title: "What it found", text: (s) => headline(s, "a1_burned_slopes", "Burned steep slopes, mud paths and the roads below them.") }],
    cta: { label: "Open the Sinlahekin Fire", q: "a1_burned_slopes" },
    roles: [{ label: "Public works (roads)", role: "roads", q: "a2_roads_to_watch" }],
  },
];

function ChapterView({ c, site, scroller }: { c: Chapter; site: SiteSummary | undefined; scroller: RefObject<HTMLElement | null> }) {
  const ref = useRef<HTMLElement>(null);
  const { scrollYProgress } = useScroll({ container: scroller, target: ref, offset: ["start start", "end end"] });
  const [step, setStep] = useState(0);
  useMotionValueEvent(scrollYProgress, "change", (v) => {
    const i = c.steps.findIndex((s) => v < s.until);
    setStep(i < 0 ? c.steps.length - 1 : i);
  });
  const href = (q: string, role?: string) => `/place/${c.site}?${role ? `role=${role}&` : ""}q=${q}`;
  const Scene = c.Scene;
  return (
    <section ref={ref} data-chapter={c.site} className={Scene ? "relative h-[340dvh]" : "relative h-[150dvh]"} aria-label={`${c.kicker}: ${c.title}`}>
      <div className="sticky top-0 flex h-dvh flex-col justify-center gap-4 px-4 pb-6 pt-20 sm:px-6 md:grid md:grid-cols-[0.85fr_1.15fr] md:items-center md:gap-10 md:pt-16 lg:px-10">
        <div className="relative z-10 order-2 md:order-1">
          <p className="eyebrow flex items-center gap-2 text-accent">
            <span className="font-display text-base font-semibold tracking-normal text-ink-3">{c.n}</span> {c.kicker}
          </p>
          <h2 className="mt-3 font-display text-[32px] font-medium leading-[1.05] tracking-tight text-ink sm:text-5xl">{c.title}</h2>
          <p className="mt-3 hidden max-w-xl text-[15px] leading-relaxed text-ink-2 sm:block">{c.lead}</p>
          <ol className="mt-5 flex flex-col gap-2.5 border-l border-line pl-4">
            {c.steps.map((s, i) => (
              <li key={s.title} className={`relative transition-all duration-500 ${i === step ? "opacity-100" : "opacity-35"} ${i !== step ? "hidden md:block" : ""}`}>
                <span className={`absolute -left-[21px] top-1.5 h-2.5 w-2.5 rounded-full border-2 ${i === step ? "border-accent bg-accent shadow-[0_0_14px_var(--glow)]" : "border-line bg-bg"}`} aria-hidden />
                <p className="text-sm font-medium text-ink">{s.title}</p>
                {i === step && <motion.p key={step} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }} className="mt-1 max-w-xl text-[13.5px] leading-relaxed text-ink-2">{s.text(site)}</motion.p>}
              </li>
            ))}
          </ol>
          <div className="mt-6 flex flex-wrap items-center gap-2">
            <Link href={href(c.cta.q)} className="flex h-11 items-center gap-2 rounded-xl bg-accent px-5 text-sm font-semibold text-[#04111a] shadow-[0_0_30px_-6px_var(--glow)] transition-all duration-200 hover:brightness-110">
              {c.cta.label} <span aria-hidden>→</span>
            </Link>
            {c.roles.map((r) => (
              <Link key={r.role} href={href(r.q, r.role)} className="flex h-11 items-center rounded-xl border border-line bg-bg/50 px-4 text-sm text-ink-2 backdrop-blur transition-colors duration-200 hover:border-accent/50 hover:text-ink">
                {r.label}
              </Link>
            ))}
          </div>
        </div>
        {Scene ? (
          <div className="relative order-1 mx-auto w-full max-w-[640px] md:order-2">
            <div className="absolute inset-[8%] rounded-full bg-accent/10 blur-3xl" aria-hidden />
            <Scene p={scrollYProgress} className="relative h-auto max-h-[46dvh] w-full md:max-h-[78dvh]" />
          </div>
        ) : <div className="order-1 hidden md:order-2 md:block" aria-hidden />}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- the page

export default function Landing() {
  const reduced = useReducedMotion() ?? false;
  const scroller = useRef<HTMLElement>(null);
  const [sites, setSites] = useState<SiteSummary[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [role, setRole] = useState<string | null>(null);
  const [focus, setFocus] = useState<GlobeFocus>({ mode: "hero" });
  const [globeOn, setGlobeOn] = useState(true);
  const [theme, setTheme] = useState<Theme>("space");
  useEffect(() => {
    fetchSites().then(setSites).catch((e) => setErr(e.message));
  }, []);
  const byId = useMemo(() => new Map((sites ?? []).map((s) => [s.id, s])), [sites]);
  const markers: GlobeMarker[] = useMemo(() => (sites ?? []).map((s) => ({ id: s.id, ...centre(s), color: LENSES[s.lens].color })), [sites]);

  // Which part of the story is on screen decides where the Earth flies.
  // The section covering most of the screen wins (by share of the screen, not of the section: chapters are
  // several screens tall, so their own visible share stays small).
  useEffect(() => {
    const root = scroller.current;
    if (!root) return;
    let raf = 0;
    let last = "";
    const pick = () => {
      raf = 0;
      const vh = root.clientHeight;
      let best: HTMLElement | null = null;
      let cover = 0;
      root.querySelectorAll<HTMLElement>("[data-globe],[data-chapter]").forEach((el) => {
        const r = el.getBoundingClientRect();
        const c = Math.max(0, Math.min(vh, r.bottom) - Math.max(0, r.top)) / vh;
        if (c > cover) { best = el; cover = c; }
      });
      const el = best as HTMLElement | null;
      if (!el) return;
      const kind = el.dataset.globe;
      const chapter = el.dataset.chapter;
      const key = `${kind}|${chapter}`;
      if (key === last) return;
      last = key;
      setGlobeOn(kind !== "off");
      setTheme(CHAPTERS.find((x) => x.site === chapter)?.theme ?? "space");
      if (kind === "hero") setFocus({ mode: "hero" });
      else if (kind === "intro") setFocus({ mode: "intro" });
      else if (chapter) {
        const s = byId.get(chapter);
        const c = CHAPTERS.find((x) => x.site === chapter);
        if (s) setFocus({ mode: c?.Scene ? "corner" : "focus", ...centre(s), marker: s.id });
        else last = ""; // sites not loaded yet: try again on the next scroll
      }
    };
    const onScroll = () => { if (!raf) raf = requestAnimationFrame(pick); };
    root.addEventListener("scroll", onScroll, { passive: true });
    pick();
    return () => { root.removeEventListener("scroll", onScroll); if (raf) cancelAnimationFrame(raf); };
  }, [byId]);

  const places = useMemo(() => (sites ?? []).filter((s) => s.decide), [sites]);
  const others = useMemo(() => (sites ?? []).filter((s) => !s.decide), [sites]);
  const roles = useMemo(() => {
    const by = new Map<string, { label: string; to: { s: SiteSummary; id: string; first: string }[] }>();
    for (const s of places) for (const r of s.decide!.roles) {
      const e = by.get(r.label) ?? { label: r.label, to: [] };
      e.to.push({ s, id: r.id, first: r.first });
      by.set(r.label, e);
    }
    return [...by.values()];
  }, [places]);
  const picked = roles.find((r) => r.label === role) ?? null;

  return (
    <main ref={scroller} data-theme={theme} className="story relative h-dvh overflow-y-auto overflow-x-hidden">
      {/* each chapter's mood (city at dusk, embers, misty pines), cross-faded behind the Earth */}
      <Ambience theme={theme} />
      {/* the Earth, behind everything, flying between framings as you scroll */}
      <div className={`pointer-events-none fixed inset-0 z-0 transition-opacity duration-700 ${globeOn ? "opacity-100" : "opacity-0"}`} aria-hidden>
        <Globe3D focus={focus} markers={markers} reduced={reduced} tint={TINT[theme]} />
      </div>

      <div className="sticky top-0 z-30 border-b border-white/5 backdrop-blur-md" style={{ background: "color-mix(in srgb, var(--page) 55%, transparent)" }}>
        <div className="mx-auto max-w-7xl px-4 py-2.5 sm:px-6"><SiteNav active="places" floating /></div>
      </div>

      {/* hero: the Earth as a horizon */}
      <section data-globe="hero" className="relative z-10 -mt-[57px] flex h-dvh flex-col items-center px-4 pt-[16dvh] text-center">
        <motion.p className="eyebrow flex items-center gap-2 text-accent" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, ease: EASE }}>
          <span className="relative flex h-2 w-2"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-60 motion-reduce:hidden" /><span className="relative inline-flex h-2 w-2 rounded-full bg-accent" /></span>
          NASA-ISRO NISAR · L-band radar · 2026
        </motion.p>
        <motion.h1 className="mt-5 font-display font-semibold uppercase leading-[0.9] tracking-[-0.02em] text-ink"
          initial={{ opacity: 0, y: 24, filter: "blur(8px)" }} animate={{ opacity: 1, y: 0, filter: "blur(0px)" }} transition={{ duration: 1.1, delay: 0.1, ease: EASE }}>
          <span className="block text-[17vw] sm:text-[12vw] lg:text-[136px]">Earth,</span>
          <span className="glow-text block text-[8.4vw] tracking-[0.04em] sm:text-[6vw] lg:text-[66px]">through NISAR&rsquo;s eye</span>
        </motion.h1>
        <motion.p className="mt-6 max-w-xl text-[15px] leading-relaxed text-ink-2 sm:text-base" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 1, delay: 0.5 }}>
          A radar that sees through cloud, smoke and night, every 12 days. Scroll to see what it reveals, and the decisions it helps people make.
        </motion.p>
        <a href="#story" className="scroll-cue absolute bottom-8 flex flex-col items-center gap-1 text-xs text-ink-3" aria-label="Scroll to the story">
          <span className="eyebrow">Scroll</span>
          <svg width="18" height="26" viewBox="0 0 18 26" aria-hidden><rect x="1" y="1" width="16" height="24" rx="8" fill="none" stroke="currentColor" /><circle cx="9" cy="8" r="2" fill="currentColor" /></svg>
        </a>
      </section>

      {/* intro: what the radar measures */}
      <section id="story" data-globe="intro" className="relative z-10 flex min-h-dvh items-center px-4 py-24 sm:px-6 lg:px-10">
        <div className="max-w-xl rounded-3xl bg-[#020a10]/40 p-1 backdrop-blur-[2px] md:bg-transparent md:backdrop-blur-none">
          <Reveal><p className="eyebrow text-accent">What it measures</p></Reveal>
          <Reveal delay={0.08}>
            <h2 className="mt-3 font-display text-[34px] font-medium leading-[1.05] tracking-tight text-ink sm:text-5xl">How the ground moves, and what covers it.</h2>
          </Reveal>
          <Reveal delay={0.16}>
            <p className="mt-4 text-[15px] leading-relaxed text-ink-2">
              NISAR&rsquo;s L-band radar passes over every place every 12 days, day or night. It measures centimetres of sinking, sees burned forest under smoke and water under reeds.
              SARAURA turns those measurements into answers to plain questions, with the reason and what you can do.
            </p>
          </Reveal>
          {sites && (
            <Reveal delay={0.24}>
              <dl className="mt-7 grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-line bg-line">
                {[
                  [sites.length, "", "places watched"],
                  [sites.reduce((n, s) => n + s.passes, 0), "", "radar Passes"],
                  [places.reduce((n, s) => n + s.decide!.questions.length, 0), "", "questions answered"],
                  [12, " days", "between two looks"],
                ].map(([v, suf, label]) => (
                  <div key={label as string} className="bg-[#04111a]/90 px-4 py-4">
                    <dd className="font-display text-3xl font-medium tracking-tight text-ink"><CountUp value={v as number} suffix={suf as string} /></dd>
                    <dt className="mt-0.5 text-xs text-ink-3">{label}</dt>
                  </div>
                ))}
              </dl>
            </Reveal>
          )}
          {err && <p className="mt-4 text-sm text-drop" role="alert">Could not reach the SARAURA API ({err}). Is it running?</p>}
        </div>
      </section>

      {/* the chapters */}
      <div className="relative z-10">
        {CHAPTERS.map((c) => <ChapterView key={c.site} c={c} site={byId.get(c.site)} scroller={scroller} />)}
      </div>

      {/* closing: everyone's way in, then research and education */}
      <div data-globe="off" className="relative z-20 bg-bg">
        <div className="bg-earth">
          <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6" aria-labelledby="who-h">
            <Reveal><p className="eyebrow text-accent">Your questions</p></Reveal>
            <Reveal delay={0.06}><h2 id="who-h" className="mt-2 font-display text-3xl font-medium tracking-tight text-ink sm:text-4xl">I am a…</h2></Reveal>
            <div className="mt-5 flex flex-wrap gap-2" role="radiogroup" aria-label="Who are you?">
              {roles.map((r) => (
                <button key={r.label} type="button" role="radio" aria-checked={role === r.label} onClick={() => setRole(role === r.label ? null : r.label)}
                  className={`h-10 cursor-pointer rounded-full border px-4 text-sm transition-all duration-200 ${role === r.label ? "border-accent bg-accent/15 text-ink shadow-[0_0_20px_-6px_var(--glow)]" : "border-line bg-bg/40 text-ink-2 hover:border-accent/50 hover:text-ink"}`}>
                  {r.label}
                </button>
              ))}
            </div>
            {picked && (
              <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mt-4 flex flex-wrap items-center gap-2 rounded-xl border border-accent/30 bg-accent/5 p-3" aria-live="polite">
                <span className="text-sm text-ink-2">Your questions are ready in:</span>
                {picked.to.map((t) => (
                  <Link key={t.s.id} href={`/place/${t.s.id}?role=${t.id}&q=${t.first}`}
                    className="flex h-9 items-center gap-2 rounded-lg bg-accent px-3 text-sm font-medium text-[#04111a] transition-all duration-200 hover:brightness-110">
                    {placeName(t.s)} <span aria-hidden>→</span>
                  </Link>
                ))}
              </motion.div>
            )}
          </section>
        </div>

        <section className="border-y border-line bg-bg-2/60">
          <ol className="mx-auto grid max-w-6xl gap-6 px-4 py-10 sm:grid-cols-3 sm:px-6">
            {[
              ["The radar measures", "NISAR's L-band radar passes every 12 days, day or night, through cloud and smoke, and records how the ground moves and what covers it."],
              ["Rules turn it into answers", "Each question is a published rule with stated thresholds, such as Bjerrum's 1/500 crack limit or burned slopes of 23° or more. Not a black box."],
              ["You decide what to check", "Every answer comes with options, their cost, their source and what to confirm on the ground. A screening, not an engineering report."],
            ].map(([t, d], i) => (
              <li key={t}>
                <Reveal delay={i * 0.12} className="flex gap-3">
                  <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-accent/40 bg-accent/10 font-mono text-sm text-accent shadow-[0_0_18px_-6px_var(--glow)]">{i + 1}</span>
                  <div>
                    <p className="text-sm font-medium text-ink">{t}</p>
                    <p className="mt-1 text-[13px] leading-relaxed text-ink-2">{d}</p>
                  </div>
                </Reveal>
              </li>
            ))}
          </ol>
        </section>

        <section className="mx-auto max-w-6xl px-4 py-14 sm:px-6" aria-labelledby="research-h">
          <p className="eyebrow text-accent-2">For researchers and educators</p>
          <h2 id="research-h" className="mt-1 font-display text-2xl font-medium tracking-tight text-ink sm:text-3xl">Go deeper into the radar itself</h2>
          <div className="mt-5 grid gap-4 md:grid-cols-3">
            {[
              ["/explore", "Research explorer", "Every NISAR Pass on a 3D globe. Draw any area and run an Analysis with physics layers and a Baseline, then export a PDF report."],
              ["/browse", "Raw Granules", "Open a single calibrated NISAR product: HH, HV and colour composites at full 10 m resolution, and change between two dates."],
              ["/models", "AI Models vs Baselines", "Six Models, each scored against a simple published rule on ground it never trained on, with labels and limits stated."],
            ].map(([href, t, d], i) => (
              <Reveal key={href} delay={i * 0.1}>
                <Link href={href} className="card-earth group block h-full rounded-2xl border border-line bg-panel-solid/60 p-5 backdrop-blur">
                  <p className="flex items-center gap-2 text-base font-medium text-ink">{t}<span className="text-ink-3 transition-transform duration-200 group-hover:translate-x-0.5" aria-hidden>→</span></p>
                  <p className="mt-1.5 text-[13px] leading-relaxed text-ink-2">{d}</p>
                </Link>
              </Reveal>
            ))}
          </div>
          {others.length > 0 && (
            <>
              <h3 className="mt-8 text-sm font-medium text-ink">More Showcase Sites (research view)</h3>
              <ul className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {others.map((s) => (
                  <li key={s.id}>
                    <Link href={`/study/${s.id}`} className="card-earth block h-full rounded-xl border border-line bg-panel-solid/50 p-3.5">
                      <span className="eyebrow" style={{ color: LENSES[s.lens].color }}>{LENSES[s.lens].label}</span>
                      <span className="mt-1 block text-sm leading-snug text-ink">{placeName(s)}</span>
                      {s.hook && <span className="mt-1 block text-xs leading-snug text-ink-3">{s.hook}</span>}
                    </Link>
                  </li>
                ))}
              </ul>
            </>
          )}
          <p className="mt-8 text-xs text-ink-3">
            New to radar? <a className="underline underline-offset-2 hover:text-ink" href="https://www.earthdata.nasa.gov/learn/earth-observation-data-basics/sar" target="_blank" rel="noreferrer">NASA&rsquo;s introduction to SAR</a>
            {" · "}<a className="underline underline-offset-2 hover:text-ink" href="https://nisar.jpl.nasa.gov/applications/societal-benefit/" target="_blank" rel="noreferrer">Who uses NISAR data</a>
          </p>
        </section>

        <footer className="border-t border-line px-4 py-5 text-[11px] text-ink-3 sm:px-6">
          <p className="mx-auto max-w-6xl">Radar: NASA-ISRO NISAR, calibrated collections, via the Alaska Satellite Facility. Earth imagery: NASA Blue Marble and Black Marble (EOSDIS GIBS). Elevation: Copernicus GLO-30. Places and roads: © OpenStreetMap contributors. Built for NASA Space Apps 2026, &ldquo;Dancing with the SARs&rdquo;.</p>
        </footer>
      </div>
    </main>
  );
}
