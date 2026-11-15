"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { fetchAnswers, fetchAnswersAt, fetchPlaces, type AnswerCard, type Answers, type AnswersAt, type Measure, type NearPlace, type Place, type Question, type Solution, type Verdict } from "@/lib/api";
import { ha } from "@/lib/style";

type Spot = { lon: number; lat: number };

const VERDICT_TEXT: Record<Verdict, string> = { good: "Fine", caution: "Take care", bad: "Act first", unknown: "Not sure" };
const COST_STYLE: Record<Solution["cost"], string> = {
  low: "bg-emerald-400/15 text-emerald-200",
  medium: "bg-amber-400/15 text-amber-200",
  high: "bg-rose-400/15 text-rose-200",
};

// ---------------------------------------------------------------- data: the study's answers and the answers at one spot

export function useAnswers(studyId: string, probe: Spot | null) {
  // Results are keyed by what they answer, so a stale one is never shown and no state is reset inside an effect.
  const [loaded, setLoaded] = useState<{ id: string; doc: Answers | null } | null>(null);
  const [spotRes, setSpotRes] = useState<{ key: string; spot: AnswersAt | null; err: string | null } | null>(null);

  useEffect(() => {
    const ctl = new AbortController();
    fetchAnswers(studyId, ctl.signal)
      .then((doc) => setLoaded({ id: studyId, doc }))
      .catch((e) => e.name !== "AbortError" && setLoaded({ id: studyId, doc: null }));
    return () => ctl.abort();
  }, [studyId]);
  const doc = loaded?.id === studyId ? loaded.doc : null;
  const settled = loaded?.id === studyId;

  const spotKey = probe && doc ? `${studyId}|${probe.lon.toFixed(5)}|${probe.lat.toFixed(5)}` : null;
  useEffect(() => {
    if (!spotKey || !probe) return;
    const ctl = new AbortController();
    fetchAnswersAt(studyId, probe.lon, probe.lat, ctl.signal)
      .then((spot) => setSpotRes({ key: spotKey, spot, err: null }))
      .catch((e) => e.name !== "AbortError" && setSpotRes({ key: spotKey, spot: null, err: e.message }));
    return () => ctl.abort();
  }, [studyId, probe, spotKey]);
  const current = spotKey && spotRes?.key === spotKey ? spotRes : null;
  return { doc, settled, spot: current?.spot ?? null, spotErr: current?.err ?? null, spotBusy: !!spotKey && !current };
}

// ---------------------------------------------------------------- small pieces

function Swatch({ color, size = "h-3 w-3" }: { color: string | null; size?: string }) {
  return <span className={`inline-block ${size} shrink-0 rounded-sm border border-white/20`} style={{ background: color ?? "transparent" }} aria-hidden />;
}

const SEVERITY: Record<Verdict, number> = { bad: 0, caution: 1, unknown: 2, good: 3 };
const COST_ORDER: Record<Solution["cost"], number> = { low: 0, medium: 1, high: 2 };
const severity = (c: AnswerCard) => (c.verdict ? SEVERITY[c.verdict] : 4);
const topicOf = (c: { topic?: string | null; title: string }) => c.topic ?? c.title;
const flagged = (c: AnswerCard) => c.class !== null && !!c.label && c.label !== "Nothing to flag here";

/** "Khoula", or "2.7 km north of Beni Ftah" when the spot is away from any named place. */
function placeTitle(p: NearPlace | null | undefined) {
  if (!p) return "Your spot";
  return p.km < 0.6 ? p.name : `${p.km.toFixed(1)} km ${p.direction} of ${p.name}`;
}

const num = (v: number) => v.toLocaleString("en-GB", { maximumFractionDigits: v < 10 ? 1 : 0 });

/** The measured number against the Question's own thresholds: why this spot got its colour. */
function Gauge({ m, color }: { m: Measure; color: string | null }) {
  const pct = (v: number) => `${Math.min(100, Math.max(0, (v / m.max) * 100))}%`;
  return (
    <div className="rounded-lg bg-white/[0.04] px-3 py-2.5">
      <div className="flex items-baseline justify-between gap-2">
        <span className="min-w-0 truncate text-[12px] text-ink-2">{m.label}</span>
        <span className="shrink-0 font-mono text-[13px] font-semibold text-ink">{num(m.value)}{m.unit === "%" ? "%" : ` ${m.unit}`}</span>
      </div>
      <div className="relative mt-2 h-2 rounded-full bg-white/10">
        <span className="absolute inset-y-0 left-0 rounded-full" style={{ width: pct(m.value), background: color ?? "var(--accent)" }} />
        {m.marks.map((k) => <span key={k.at} className="absolute -top-1 -bottom-1 w-0.5 bg-ink/80" style={{ left: pct(k.at) }} aria-hidden />)}
      </div>
      <div className="relative mt-1 h-4 text-[10.5px] text-ink-3">
        {m.marks.map((k) => (
          <span key={k.at} className="absolute -translate-x-1/2 whitespace-nowrap" style={{ left: pct(k.at) }}>{num(k.at)}{m.unit === "%" ? "%" : ""} {k.label}</span>
        ))}
      </div>
      <p className="sr-only">{m.label}: {num(m.value)} {m.unit}. Thresholds: {m.marks.map((k) => `${k.label} at ${num(k.at)}`).join(", ")}.</p>
    </div>
  );
}

/** One action list for a spot: every flagged answer's options, worst answers first, cheapest first, no repeats. */
function mergedActions(cards: AnswerCard[], catalogue: Record<string, Solution>) {
  const out = new Map<string, { id: string; s: Solution; topics: string[]; rank: number }>();
  for (const c of [...cards].sort((a, b) => severity(a) - severity(b))) {
    if (!c.verdict) continue;
    for (const id of c.solutions) {
      const s = catalogue[id];
      if (!s) continue;
      const e = out.get(id);
      if (e) { if (!e.topics.includes(topicOf(c))) e.topics.push(topicOf(c)); continue; }
      out.set(id, { id, s, topics: [topicOf(c)], rank: severity(c) * 10 + COST_ORDER[s.cost] });
    }
  }
  return [...out.values()].sort((a, b) => a.rank - b.rank);
}

/** The answer across the whole area as one stacked bar: readable before a question is even opened. */
function ShareBar({ q }: { q: Question }) {
  if (!q.classes.length) return null;
  return (
    <div className="mt-2 flex h-1.5 overflow-hidden rounded-full bg-white/10" role="img"
      aria-label={q.classes.map((c) => `${c.label} ${(c.share * 100).toFixed(0)}%`).join(", ")}>
      {q.classes.filter((c) => c.share > 0).map((c) => <span key={c.value} style={{ width: `${c.share * 100}%`, background: c.color }} />)}
    </div>
  );
}

function Option({ n, s }: { n: number; s: Solution }) {
  return (
    <li>
      <details className="group rounded-lg border border-line bg-black/20 px-2.5 py-2">
        <summary className="flex cursor-pointer list-none items-center gap-2">
          <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-white/10 font-mono text-[11px] text-ink-2">{n}</span>
          <span className="min-w-0 flex-1 text-sm leading-snug text-ink">{s.title}</span>
          <span className={`shrink-0 rounded px-1.5 py-0.5 text-[11px] ${COST_STYLE[s.cost]}`}>{s.cost}</span>
          <span className="shrink-0 text-xs text-ink-3 transition-transform duration-200 group-open:rotate-90" aria-hidden>›</span>
        </summary>
        <p className="mt-2 text-[13px] leading-relaxed text-ink-2">{s.what}</p>
        <p className="mt-1.5 text-xs text-ink-3"><span className="text-ink-2">Check first:</span> {s.check}</p>
        <p className="mt-0.5 text-[11px] text-ink-3">Source: {s.source}</p>
      </details>
    </li>
  );
}

function Options({ ids, catalogue, first = 2 }: { ids: string[]; catalogue: Record<string, Solution>; first?: number }) {
  const [all, setAll] = useState(false);
  const list = ids.filter((id) => catalogue[id]);
  if (!list.length) return null;
  const shown = all ? list : list.slice(0, first);
  return (
    <div>
      <ol className="flex flex-col gap-1.5">{shown.map((id, i) => <Option key={id} n={i + 1} s={catalogue[id]} />)}</ol>
      {list.length > first && (
        <button type="button" onClick={() => setAll((v) => !v)} className="mt-1.5 cursor-pointer text-xs text-accent hover:underline">
          {all ? "Show fewer" : `Show ${list.length - first} more option${list.length - first > 1 ? "s" : ""}`}
        </button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- the bubble on the map

export function SpotBubble({ spot, busy, err, openId, onDetails, onClose }: {
  spot: AnswersAt | null; busy: boolean; err: string | null; openId: string | null; onDetails: () => void; onClose: () => void;
}) {
  if (err) return <p className="text-sm text-drop">{err}</p>;
  if (busy || !spot) return <div className="w-48 py-1"><div className="busy-bar h-0.5" /><p className="mt-2 text-xs text-ink-3">Reading the radar here…</p></div>;
  const main = spot.cards.find((c) => c.question === openId) ?? [...spot.cards].sort((a, b) => severity(a) - severity(b))[0];
  const others = spot.cards.filter((c) => c !== main);
  const raised = others.filter(flagged).sort((a, b) => severity(a) - severity(b));
  const quiet = others.length - raised.length;
  return (
    <div className="w-60 sm:w-64">
      <div className="flex items-start gap-2">
        <p className="min-w-0 flex-1 text-[13px] font-semibold leading-snug text-ink">{placeTitle(spot.place)}</p>
        <button type="button" onClick={onClose} aria-label="Close" className="-mr-1 -mt-1 cursor-pointer px-1 text-ink-3 hover:text-ink">×</button>
      </div>
      <p className="mt-1 text-[11px] uppercase tracking-wide text-ink-3">{topicOf(main)}</p>
      <div className="mt-0.5 flex items-center gap-2 rounded-lg px-2 py-1.5" style={{ background: `${main.color ?? "#9ca3af"}26` }}>
        <Swatch color={main.color} size="h-3.5 w-3.5" />
        <span className="text-[14px] font-semibold leading-tight text-ink">{main.label ?? "No answer here"}</span>
      </div>
      {(raised.length > 0 || quiet > 0) && (
        <ul className="mt-2 hidden flex-col gap-1 border-t border-line pt-1.5 sm:flex">
          {raised.slice(0, 3).map((c) => (
            <li key={c.question} className="flex items-start gap-1.5 text-[11.5px] leading-snug" title={c.title}>
              <Swatch color={c.color} size="mt-0.5 h-2.5 w-2.5" />
              <span className="min-w-0 flex-1"><span className="text-ink-3">{topicOf(c)}:</span> <span className="text-ink-2">{c.label}</span></span>
            </li>
          ))}
          {quiet > 0 && <li className="text-[11.5px] text-ink-3">{quiet === others.length ? "Other questions" : `${quiet} other question${quiet > 1 ? "s" : ""}`}: nothing to flag</li>}
        </ul>
      )}
      <button type="button" onClick={onDetails} className="mt-2 w-full cursor-pointer rounded-lg bg-accent px-2 py-1.5 text-xs font-medium text-[#04111a] transition-opacity duration-200 hover:opacity-90">
        Everything here, and what to do →
      </button>
    </div>
  );
}

// ---------------------------------------------------------------- place search (over the map)

export function PlaceSearch({ studyId, onPick, placeholder }: { studyId: string; onPick: (p: Place) => void; placeholder: string }) {
  const [q, setQ] = useState("");
  const [res, setRes] = useState<{ q: string; hits: Place[] } | null>(null);
  const [active, setActive] = useState(0);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (q.trim().length < 2) return;
    const ctl = new AbortController();
    const t = setTimeout(() => fetchPlaces(studyId, q, ctl.signal).then((hits) => setRes({ q, hits })).catch(() => {}), 180);
    return () => { clearTimeout(t); ctl.abort(); };
  }, [studyId, q]);
  const hits = res && res.q === q && q.trim().length >= 2 ? res.hits : [];
  const choose = (p: Place) => { onPick(p); setQ(p.name); setOpen(false); };
  return (
    <div className="relative w-full">
      <label htmlFor="place-search" className="sr-only">Find a place in this study</label>
      <div className="panel flex h-11 items-center gap-2 px-3">
        <svg viewBox="0 0 20 20" className="h-4 w-4 shrink-0 text-ink-3" aria-hidden><circle cx="9" cy="9" r="6" fill="none" stroke="currentColor" strokeWidth="2" /><path d="M14 14l4 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>
        <input id="place-search" value={q} autoComplete="off" placeholder={placeholder} role="combobox" aria-expanded={open && hits.length > 0} aria-controls="place-results"
          onChange={(e) => { setQ(e.target.value); setOpen(true); setActive(0); }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, hits.length - 1)); }
            if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
            if (e.key === "Enter" && hits[active]) choose(hits[active]);
            if (e.key === "Escape") setOpen(false);
          }}
          className="h-full min-w-0 flex-1 bg-transparent text-sm text-ink placeholder:text-ink-3 focus:outline-none" />
      </div>
      {open && hits.length > 0 && (
        <ul id="place-results" role="listbox" className="panel absolute inset-x-0 top-12 z-20 max-h-72 overflow-y-auto p-1">
          {hits.map((p, i) => (
            <li key={`${p.name}${p.lon}`} role="option" aria-selected={i === active}>
              <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => choose(p)} onMouseEnter={() => setActive(i)}
                className={`flex w-full cursor-pointer items-baseline gap-2 rounded-lg px-2.5 py-2 text-left text-sm ${i === active ? "bg-white/10" : ""}`}>
                <span className="min-w-0 flex-1 truncate text-ink">{p.name}</span>
                {p.local && p.local !== p.name && <span className="shrink-0 text-xs text-ink-3" dir="auto">{p.local}</span>}
                <span className="shrink-0 text-[11px] text-ink-3">{p.kind}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- the answer at the clicked spot (sidebar)

function SpotCard({ card, onGo }: { card: AnswerCard; onGo: (s: Spot) => void }) {
  return (
    <div className="overflow-hidden rounded-xl border border-line" id="spot-card">
      <div className="flex items-center gap-2 px-3 py-2.5" style={{ background: `${card.color ?? "#9ca3af"}2e` }}>
        <Swatch color={card.color} size="h-4 w-4" />
        <div className="min-w-0 flex-1">
          <p className="text-[11px] uppercase tracking-wide text-ink-3">At your spot</p>
          <p className="text-base font-semibold leading-tight text-ink">{card.label ?? "No answer here"}</p>
        </div>
        {card.verdict && <span className="shrink-0 rounded-full bg-black/30 px-2 py-0.5 text-[11px] text-ink-2">{VERDICT_TEXT[card.verdict]}</span>}
      </div>
      <div className="flex flex-col gap-3 p-3">
        {card.measure && <Gauge m={card.measure} color={card.color} />}
        {!!card.reasons.length && (
          <div>
            <p className="mb-1 text-[11px] uppercase tracking-wide text-ink-3">Why</p>
            <ul className="flex flex-col gap-1 text-[13px] leading-relaxed text-ink-2">
              {card.reasons.map((r) => <li key={r} className="flex gap-2"><span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-ink-3" aria-hidden />{r}</li>)}
            </ul>
          </div>
        )}
        {!!card.alternatives?.length && (
          <div>
            <p className="mb-1 text-[11px] uppercase tracking-wide text-ink-3">Steadier ground nearby</p>
            <ol className="flex flex-col gap-1.5">
              {card.alternatives.map((a, i) => (
                <li key={`${a.lon},${a.lat}`}>
                  <button type="button" onClick={() => onGo({ lon: a.lon, lat: a.lat })}
                    className="flex w-full cursor-pointer items-center gap-2 rounded-lg bg-white/5 px-2.5 py-2 text-left text-sm transition-colors duration-200 hover:bg-white/10">
                    <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-white/10 font-mono text-[11px]">{i + 1}</span>
                    <span className="min-w-0 flex-1">
                      <span className="text-ink">{(a.distance_m / 1000).toFixed(1)} km {a.direction}</span>
                      <span className="block text-xs text-ink-3">{a.label} · sinks {a.sinking_cm_yr.toFixed(1)} cm/yr</span>
                    </span>
                    <span className="text-xs text-accent">Go →</span>
                  </button>
                </li>
              ))}
            </ol>
          </div>
        )}
        {!!card.solutions.length && <p className="text-[12px] text-ink-3">What to do here is listed in the card above, with every question&rsquo;s options together.</p>}
      </div>
    </div>
  );
}

/** "Ranked by …": the first number column the list is actually sorted by (checked, not assumed). */
function rankedBy(q: Question) {
  const r = q.ranked;
  if (!r || r.rows.length < 3) return null;
  for (const c of r.columns.slice(1)) {
    const v = r.rows.map((x) => x[c.key]).filter((x): x is number => typeof x === "number");
    if (v.length !== r.rows.length) continue;
    if (v.every((x, i) => i === 0 || x <= v[i - 1])) return `most ${c.label.toLowerCase()} first`;
    if (v.every((x, i) => i === 0 || x >= v[i - 1])) return `least ${c.label.toLowerCase()} first`;
  }
  return null;
}

/** One list cell in plain words: "hamlet", "81% basin burned and steep", "15.5 ha burned steep upstream". */
function cell(c: { key: string; label: string; unit?: string }, v: string | number | undefined) {
  if (v === undefined || v === null || v === "") return null;
  if (c.key === "kind" || c.key === "type") return String(v);
  const n = typeof v === "number" ? num(v) : v;
  return c.unit === "%" ? `${n}% ${c.label.toLowerCase()}` : `${n}${c.unit ? ` ${c.unit}` : ""} ${c.label.toLowerCase()}`;
}

function QuestionBody({ q, doc, spot, spotBusy, onGo }: { q: Question; doc: Answers; spot: AnswersAt | null; spotBusy: boolean; onGo: (s: Spot) => void }) {
  const card = spot?.cards.find((c) => c.question === q.id) ?? null;
  const [rows, setRows] = useState(5);
  return (
    <div className="mt-3 flex flex-col gap-4">
      {spotBusy ? <div className="busy-bar h-0.5" aria-hidden /> : card ? (
        <AnimatePresence mode="wait">
          <motion.div key={`${card.question}|${card.label}|${card.reasons.join("|").length}`} initial={{ opacity: 0, y: 10, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0 }} transition={{ duration: 0.35, ease: [0.2, 0.8, 0.2, 1] }}>
            <SpotCard card={card} onGo={onGo} />
          </motion.div>
        </AnimatePresence>
      ) : (
        <div className="flex items-center gap-2.5 rounded-xl border border-dashed border-accent/40 bg-accent/5 px-3 py-2.5 text-[13px] text-ink-2">
          <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-accent/15 text-accent" aria-hidden>↖</span>
          {q.point_only ? "Click a spot on the map, or search a place, to rank the steadier ground around it." : "Click the map or search a place for the answer at that spot, why, and what you can do."}
        </div>
      )}

      <div>
        <p className="mb-1.5 text-[11px] uppercase tracking-wide text-ink-3">Across the whole area</p>
        <p className="text-[13px] leading-relaxed text-ink-2">{q.headline}</p>
        {!!q.classes.length && <p className="mt-2 text-[11px] text-ink-3">Ground this question marks, by answer (bar: share of the marked ground)</p>}
        {!!q.classes.length && (
          <ul className="mt-2 flex flex-col gap-1">
            {q.classes.map((c) => (
              <li key={c.value}>
                <details className="group rounded-lg px-1 py-1 hover:bg-white/[0.03]">
                  <summary className="flex cursor-pointer list-none items-center gap-2 text-[13px]">
                    <Swatch color={c.color} />
                    <span className="min-w-0 flex-1 leading-snug text-ink-2 group-open:text-ink">{c.label}</span>
                    <span className="w-24 shrink-0">
                      <span className="block h-1.5 overflow-hidden rounded-full bg-white/10"><span className="block h-full" style={{ width: `${Math.max(2, c.share * 100)}%`, background: c.color }} /></span>
                    </span>
                    <span className="w-[72px] shrink-0 text-right font-mono text-xs text-ink-3" title={`${(c.share * 100).toFixed(0)}% of the marked ground`}>{ha(c.area_ha)}</span>
                  </summary>
                  <div className="mt-2 pl-5">
                    <p className="text-[13px] text-ink-2">{c.meaning} <span className="text-ink-3">({ha(c.area_ha)})</span></p>
                    <div className="mt-2"><Options ids={c.solutions} catalogue={doc.solutions} /></div>
                  </div>
                </details>
              </li>
            ))}
          </ul>
        )}
      </div>

      {q.ranked && q.ranked.rows.length > 0 && (
        <div>
          <p className="text-[11px] uppercase tracking-wide text-ink-3">{q.ranked.title}</p>
          {rankedBy(q) && <p className="mb-1 text-[11px] text-ink-3">Ranked {rankedBy(q)}</p>}
          <ol className="flex flex-col">
            {q.ranked.rows.slice(0, rows).map((r, i) => {
              const [first, ...rest] = q.ranked!.columns;
              return (
                <li key={`${r.lon},${r.lat},${i}`}>
                  <button type="button" onClick={() => onGo({ lon: r.lon, lat: r.lat })} title="Show on the map"
                    className="flex w-full cursor-pointer items-center gap-2.5 border-t border-line px-1 py-2 text-left transition-colors duration-200 first:border-0 hover:bg-white/5">
                    <span className="w-5 shrink-0 text-right font-mono text-xs text-ink-3">{i + 1}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm text-ink">{String(r[first.key] ?? "")}</span>
                      <span className="line-clamp-2 block text-xs leading-snug text-ink-3">
                        {rest.map((c) => cell(c, r[c.key])).filter(Boolean).join(" · ")}
                      </span>
                    </span>
                    <span className="shrink-0 text-xs text-ink-3" aria-hidden>→</span>
                  </button>
                </li>
              );
            })}
          </ol>
          <div className="mt-1 flex items-center justify-between text-xs text-ink-3">
            <span>{q.ranked.total.toLocaleString("en-GB")} found · tap one to see it</span>
            {q.ranked.rows.length > rows && (
              <button type="button" onClick={() => setRows(q.ranked!.rows.length)} className="cursor-pointer text-accent hover:underline">Show top {q.ranked.rows.length}</button>
            )}
          </div>
        </div>
      )}

      <details className="text-xs text-ink-3">
        <summary className="cursor-pointer text-ink-2">How this is worked out</summary>
        <p className="mt-1.5 text-ink-2">Sources</p>
        <ul className="list-disc pl-4">{q.sources.map((s) => <li key={s}>{s}</li>)}</ul>
        <p className="mt-1.5 text-ink-2">Limits</p>
        <ul className="list-disc pl-4">{q.limits.map((s) => <li key={s}>{s}</li>)}</ul>
      </details>
    </div>
  );
}

// ---------------------------------------------------------------- one card for the picked spot: every answer, one action list

function VillageCard({ spot, busy, doc, shown, openId, onOpen, onGo, onClear }: {
  spot: AnswersAt | null; busy: boolean; doc: Answers; shown: Question[]; openId: string | null;
  onOpen: (q: Question | null) => void; onGo: (s: Spot) => void; onClear: () => void;
}) {
  const [allActions, setAllActions] = useState(false);
  if (busy || !spot) {
    return (
      <div className="rounded-2xl border border-accent/40 bg-accent/[0.05] p-4" aria-busy="true">
        <div className="busy-bar h-0.5" />
        <p className="mt-2 text-xs text-ink-3">Reading the radar at this spot…</p>
      </div>
    );
  }
  const byQ = new Map(spot.cards.map((c) => [c.question, c]));
  const rows = shown.map((q) => ({ q, c: byQ.get(q.id) })).filter((r): r is { q: Question; c: AnswerCard } => !!r.c);
  const worst = [...rows].sort((a, b) => severity(a.c) - severity(b.c))[0];
  // the gauge explains the open question here, else the most serious flagged one that has a measured number
  const gaugeRow = rows.find((r) => r.q.id === openId && r.c.measure) ?? [...rows].filter((r) => r.c.measure && flagged(r.c)).sort((a, b) => severity(a.c) - severity(b.c))[0];
  const actions = mergedActions(rows.map((r) => r.c), doc.solutions);
  const shownActions = allActions ? actions : actions.slice(0, 3);
  // step through the open question's ranked list (villages, roads, segments) from here
  const openQ = shown.find((q) => q.id === openId) ?? null;
  const ranked = openQ?.ranked?.rows ?? [];
  const at = ranked.length ? ranked.reduce((best, r, i) => {
    const d = Math.hypot((r.lon - spot.lon) * Math.cos((spot.lat * Math.PI) / 180), r.lat - spot.lat);
    return d < best.d ? { i, d } : best;
  }, { i: -1, d: 0.004 }).i : -1; // within about 400 m counts as "this item"
  const step = (d: 1 | -1) => {
    if (!ranked.length) return;
    const i = at < 0 ? (d === 1 ? 0 : ranked.length - 1) : (at + d + ranked.length) % ranked.length;
    onGo({ lon: ranked[i].lon, lat: ranked[i].lat });
  };
  return (
    <section id="village-card" aria-label={`Everything about ${placeTitle(spot.place)}`}
      className="overflow-hidden rounded-2xl border bg-white/[0.03]" style={{ borderColor: `${worst?.c.color ?? "#94a3b8"}66` }}>
      <div className="h-1" style={{ background: worst?.c.color ?? "transparent" }} aria-hidden />
      <div className="p-4">
        <div className="flex items-start gap-2">
          <div className="min-w-0 flex-1">
            <p className="text-[11px] uppercase tracking-wide text-ink-3">{spot.place && spot.place.km < 0.6 ? spot.place.kind || "Place" : "Your spot"}</p>
            <h3 className="font-display text-xl font-semibold leading-tight text-ink">{placeTitle(spot.place)}</h3>
            {spot.place?.local && spot.place.local !== spot.place.name && spot.place.km < 0.6 && <p className="text-xs text-ink-3" dir="auto">{spot.place.local}</p>}
          </div>
          {ranked.length > 0 && (
            <div className="flex shrink-0 items-center gap-1 text-xs text-ink-3">
              <button type="button" onClick={() => step(-1)} aria-label="Previous in the list" className="grid h-7 w-7 cursor-pointer place-items-center rounded-lg border border-line hover:text-ink">‹</button>
              <span className="min-w-[48px] text-center font-mono" title={openQ?.ranked?.title}>{at >= 0 ? `${at + 1} of ${ranked.length}` : `– of ${ranked.length}`}</span>
              <button type="button" onClick={() => step(1)} aria-label="Next in the list" className="grid h-7 w-7 cursor-pointer place-items-center rounded-lg border border-line hover:text-ink">›</button>
            </div>
          )}
          <button type="button" onClick={onClear} aria-label="Clear this spot" className="grid h-7 w-7 shrink-0 cursor-pointer place-items-center rounded-lg text-ink-3 hover:text-ink">✕</button>
        </div>

        <ul className="mt-3 flex flex-col">
          {rows.map(({ q, c }) => (
            <li key={q.id}>
              <button type="button" onClick={() => onOpen(q)} aria-current={q.id === openId}
                className={`flex w-full cursor-pointer items-center gap-2.5 border-t border-line py-2 text-left transition-colors duration-150 first:border-0 hover:bg-white/[0.04] ${q.id === openId ? "text-ink" : ""}`}>
                <Swatch color={c.color ?? (flagged(c) ? null : "#334155")} size="h-3 w-3" />
                <span className="min-w-0 flex-1">
                  <span className="block text-[12px] text-ink-3">{topicOf(q)}</span>
                  <span className={`block text-[13.5px] leading-snug ${flagged(c) ? "text-ink" : "text-ink-3"}`}>{c.label ?? "No answer here"}</span>
                </span>
                {c.verdict && <span className="shrink-0 rounded-full bg-black/30 px-2 py-0.5 text-[11px] text-ink-2">{VERDICT_TEXT[c.verdict]}</span>}
              </button>
            </li>
          ))}
        </ul>

        {gaugeRow?.c.measure && (
          <div className="mt-3">
            <p className="mb-1.5 text-[11px] uppercase tracking-wide text-ink-3">Why: {topicOf(gaugeRow.q).toLowerCase()}</p>
            <Gauge m={gaugeRow.c.measure} color={gaugeRow.c.color} />
          </div>
        )}

        <div className="mt-4">
          <p className="mb-1.5 text-[11px] uppercase tracking-wide text-ink-3">What to do here, in order</p>
          {actions.length ? (
            <>
              <ol className="flex flex-col gap-1.5">
                {shownActions.map((a, i) => (
                  <li key={a.id}>
                    <details className="group rounded-lg border border-line bg-black/20 px-2.5 py-2">
                      <summary className="flex cursor-pointer list-none items-center gap-2">
                        <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-white/10 font-mono text-[11px] text-ink-2">{i + 1}</span>
                        <span className="min-w-0 flex-1">
                          <span className="block text-sm leading-snug text-ink">{a.s.title}</span>
                          <span className="block text-[11px] text-ink-3">for {a.topics.join(" and ").toLowerCase()}</span>
                        </span>
                        <span className={`shrink-0 rounded px-1.5 py-0.5 text-[11px] ${COST_STYLE[a.s.cost]}`}>{a.s.cost}</span>
                        <span className="shrink-0 text-xs text-ink-3 transition-transform duration-200 group-open:rotate-90" aria-hidden>›</span>
                      </summary>
                      <p className="mt-2 text-[13px] leading-relaxed text-ink-2">{a.s.what}</p>
                      <p className="mt-1.5 text-xs text-ink-3"><span className="text-ink-2">Check first:</span> {a.s.check}</p>
                      <p className="mt-0.5 text-[11px] text-ink-3">Source: {a.s.source}</p>
                    </details>
                  </li>
                ))}
              </ol>
              {actions.length > 3 && (
                <button type="button" onClick={() => setAllActions((v) => !v)} className="mt-1.5 cursor-pointer text-xs text-accent hover:underline">
                  {allActions ? "Show fewer" : `Show ${actions.length - 3} more`}
                </button>
              )}
            </>
          ) : <p className="text-[13px] text-ink-3">Nothing to act on here for these questions.</p>}
        </div>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- the panel

export default function AskPanel({ doc, spot, spotBusy, spotErr, role, onRole, openId, onOpen, onGo, onClear, scrollKey }: {
  doc: Answers;
  spot: AnswersAt | null;
  spotBusy: boolean;
  spotErr: string | null;
  /** null: not chosen yet, so the panel first asks who you are. */
  role: string | null;
  onRole: (r: string | null) => void;
  openId: string | null;
  onOpen: (q: Question | null) => void;
  onGo: (s: Spot) => void;
  /** Forget the picked spot (closes its card and the map bubble). */
  onClear: () => void;
  /** Changes when the spot card should be scrolled into view (e.g. "Why, and what to do" in the bubble). */
  scrollKey: number;
}) {
  const known = role === null || role === "all" || doc.roles.some((r) => r.id === role);
  const shown = useMemo(() => {
    const r = doc.roles.find((x) => x.id === role);
    if (!r) return doc.questions;
    const byId = new Map(doc.questions.map((q) => [q.id, q]));
    return r.questions.map((id) => byId.get(id)).filter((q): q is Question => !!q);
  }, [doc, role]);
  const openRef = useRef<HTMLLIElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion() ?? false;
  useEffect(() => {
    if (scrollKey) (cardRef.current ?? openRef.current)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [scrollKey]);

  if (role === null) {
    const count = (r: { questions: string[] }) => r.questions.filter((q) => doc.questions.some((x) => x.id === q)).length;
    return (
      <div>
        <h2 className="font-display text-2xl font-medium leading-tight tracking-tight text-ink">Who are you?</h2>
        <p className="mt-1 text-sm text-ink-2">We will show the questions that matter to you first.</p>
        <ul className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2">
          {doc.roles.map((r) => (
            <li key={r.id}>
              <button type="button" onClick={() => { onRole(r.id); const first = doc.questions.find((q) => q.id === r.questions[0]); if (first) onOpen(first); }}
                className="flex h-full w-full cursor-pointer flex-col items-start rounded-xl border border-line px-3.5 py-3 text-left transition-colors duration-200 hover:border-accent/60 hover:bg-accent/5">
                <span className="text-[15px] font-medium text-ink">{r.label}</span>
                <span className="mt-0.5 text-xs text-ink-3">{count(r)} question{count(r) > 1 ? "s" : ""}, starting with &ldquo;{doc.questions.find((q) => q.id === r.questions[0])?.title}&rdquo;</span>
              </button>
            </li>
          ))}
        </ul>
        <button type="button" onClick={() => onRole("all")} className="mt-3 cursor-pointer text-sm text-accent hover:underline">Just show me every question →</button>
      </div>
    );
  }
  const current = doc.roles.find((r) => r.id === role);

  return (
    <div>
      <div className="flex items-center gap-2 rounded-xl bg-white/[0.04] px-3 py-2 text-sm">
        <span className="text-ink-3">Showing questions for</span>
        <span className="font-medium text-ink">{current?.label ?? "everyone"}</span>
        <button type="button" onClick={() => onRole(null)} className="ml-auto cursor-pointer text-xs text-accent hover:underline">change</button>
      </div>
      {!known && <p className="mt-2 text-xs text-ink-3">That role is not used for this place, so every question is shown.</p>}
      {spot || spotBusy ? (
        <div ref={cardRef} className="mt-3 scroll-mt-3">
          <VillageCard spot={spot} busy={spotBusy} doc={doc} shown={shown} openId={openId} onOpen={onOpen} onGo={onGo} onClear={onClear} />
        </div>
      ) : <p className="mt-3 text-xs text-ink-3">Tap a village, a road or any spot on the map, or search a place, to see every answer there and what to do.</p>}
      {spotErr && <p className="mt-2 text-sm text-drop" role="alert">{spotErr}</p>}
      <ul className="mt-3 flex flex-col gap-2">
        {shown.map((q, i) => {
          const isOpen = openId === q.id;
          const card = spot?.cards.find((c) => c.question === q.id);
          return (
            <motion.li key={q.id} ref={isOpen ? openRef : undefined} initial={reduced ? false : { opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: i * 0.06, ease: [0.2, 0.8, 0.2, 1] }}
              className={`scroll-mt-3 rounded-xl border transition-colors duration-200 ${isOpen ? "border-accent/50 bg-accent/[0.04] shadow-[0_0_30px_-14px_var(--glow)]" : "border-line hover:border-accent/30"} px-3 py-2.5`}>
              <button type="button" onClick={() => onOpen(isOpen ? null : q)} aria-expanded={isOpen} className="flex w-full cursor-pointer items-start gap-2.5 text-left">
                <span className={`mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full font-mono text-xs ${isOpen ? "bg-accent text-[#04111a]" : "bg-white/10 text-ink-2"}`}>{i + 1}</span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[14.5px] font-medium leading-snug text-ink">{q.title}</span>
                  {!isOpen && card?.label && (
                    <span className="mt-1 flex items-center gap-1.5 text-xs text-ink-2"><Swatch color={card.color} size="h-2.5 w-2.5" />At your spot: {card.label}</span>
                  )}
                  {!isOpen && !card?.label && <span className="block text-xs leading-snug text-ink-3">{q.short}</span>}
                  {!isOpen && <ShareBar q={q} />}
                </span>
                <span className={`mt-1 shrink-0 text-ink-3 transition-transform duration-200 ${isOpen ? "rotate-90" : ""}`} aria-hidden>›</span>
              </button>
              {isOpen && <QuestionBody q={q} doc={doc} spot={spot} spotBusy={spotBusy} onGo={onGo} />}
            </motion.li>
          );
        })}
      </ul>
      <p className="mt-3 text-[11px] leading-relaxed text-ink-3">{doc.model_evidence
          ? `Worked out with stated rules over ${doc.model_evidence} (its card, in the research view, gives its score against a simple Baseline). `
          : "Worked out from the radar measurements with stated rules, not AI. "}Use it to decide where to look first and what to check, not as an engineering report. {doc.attribution}</p>
    </div>
  );
}
