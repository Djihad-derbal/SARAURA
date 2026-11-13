"use client";

import { useState } from "react";
import { longDate, shortDate, type Histogram, type PassInfo, type TsPoint } from "@/lib/api";
import { fmt } from "@/lib/style";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const day = (iso: string) => Date.parse(iso + "T00:00:00Z") / 86400000;

function niceTicks(lo: number, hi: number, n = 4) {
  const raw = (hi - lo) / n || 1;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((k) => k * mag).find((s) => s >= raw) ?? raw;
  const out: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(6));
  return out;
}

function monthTicks(t0: number, t1: number) {
  const out: { t: number; text: string }[] = [];
  const d = new Date(t0 * 86400000);
  d.setUTCDate(1);
  d.setUTCMonth(d.getUTCMonth() + 1);
  const every = (t1 - t0) / 30 > 9 ? 2 : 1;
  while (d.getTime() / 86400000 <= t1) {
    if (d.getUTCMonth() % every === 0) out.push({ t: d.getTime() / 86400000, text: MONTHS[d.getUTCMonth()] });
    d.setUTCMonth(d.getUTCMonth() + 1);
  }
  return out;
}

export type Line = { label: string; color: string; points: TsPoint[]; note?: string };

/** Several time series on one axis, each with its middle-half band; a legend names them. */
export function MultiLineChart({ lines, unit, eventDate, width = 560, height = 240, still }: { lines: Line[]; unit: string; eventDate?: string | null; width?: number; height?: number; still?: boolean }) {
  const [hover, setHover] = useState<string | null>(null);
  const all = lines.flatMap((l) => l.points.filter((p) => Number.isFinite(p.value)));
  if (all.length < 2) return <p className="text-sm text-ink-2">Not enough readings to draw this chart.</p>;
  const M = { top: 12, right: 14, bottom: 26, left: 46 };
  const t0 = Math.min(...all.map((p) => day(p.date)));
  const t1 = Math.max(...all.map((p) => day(p.date)));
  const vals = all.flatMap((p) => [p.value, p.p25 ?? p.value, p.p75 ?? p.value]);
  let lo = Math.min(...vals);
  let hi = Math.max(...vals);
  const pad = (hi - lo) * 0.06 || 1;
  lo -= pad;
  hi += pad;
  const x = (t: number) => M.left + ((t - t0) / Math.max(1, t1 - t0)) * (width - M.left - M.right);
  const y = (v: number) => M.top + ((hi - v) / (hi - lo)) * (height - M.top - M.bottom);
  const hovered = hover ? all.filter((p) => p.date === hover) : [];
  return (
    <figure className="m-0">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full overflow-visible" role="img" aria-label={`${lines.map((l) => l.label).join(", ")} through time, ${unit}`} onMouseLeave={() => setHover(null)}>
        {niceTicks(lo, hi).map((v) => (
          <g key={v}>
            <line x1={M.left} x2={width - M.right} y1={y(v)} y2={y(v)} stroke="var(--line)" />
            <text x={M.left - 6} y={y(v) + 3.5} textAnchor="end" fontSize="10" fill="var(--ink-3)" fontFamily="var(--font-plex-mono)">{fmt(v)}</text>
          </g>
        ))}
        {monthTicks(t0, t1).map((t) => (
          <text key={t.t} x={x(t.t)} y={height - 8} textAnchor="middle" fontSize="10" fill="var(--ink-3)">{t.text}</text>
        ))}
        {eventDate && day(eventDate) >= t0 && day(eventDate) <= t1 && (
          <g>
            <line x1={x(day(eventDate))} x2={x(day(eventDate))} y1={M.top} y2={height - M.bottom} stroke="var(--drop)" strokeDasharray="3 3" />
            <text x={x(day(eventDate)) + 4} y={M.top + 9} fontSize="10" fill="var(--drop)">event</text>
          </g>
        )}
        {hover && <line x1={x(day(hover))} x2={x(day(hover))} y1={M.top} y2={height - M.bottom} stroke="var(--ink-3)" />}
        {lines.map((l) => {
          const pts = l.points.filter((p) => Number.isFinite(p.value));
          const band = pts.every((p) => p.p25 !== undefined)
            ? pts.map((p, i) => `${i ? "L" : "M"}${x(day(p.date)).toFixed(1)},${y(p.p75!).toFixed(1)}`).join("") + [...pts].reverse().map((p) => `L${x(day(p.date)).toFixed(1)},${y(p.p25!).toFixed(1)}`).join("") + "Z"
            : "";
          return (
            <g key={l.label}>
              {band && <path d={band} fill={l.color} opacity={0.13} />}
              <path d={pts.map((p, i) => `${i ? "L" : "M"}${x(day(p.date)).toFixed(1)},${y(p.value).toFixed(1)}`).join("")} fill="none" stroke={l.color} strokeWidth={2} strokeLinejoin="round" />
              {pts.map((p) => <circle key={p.date} cx={x(day(p.date))} cy={y(p.value)} r={2.6} fill={l.color} />)}
            </g>
          );
        })}
        {!still &&
          [...new Set(all.map((p) => p.date))].sort().map((d, i, arr) => {
            const a = i ? (x(day(arr[i - 1])) + x(day(d))) / 2 : M.left;
            const b = i < arr.length - 1 ? (x(day(d)) + x(day(arr[i + 1]))) / 2 : width - M.right;
            return <rect key={d} x={a} y={M.top} width={Math.max(1, b - a)} height={height - M.top - M.bottom} fill="transparent" onMouseEnter={() => setHover(d)} />;
          })}
        <text x={4} y={M.top - 2} fontSize="10" fill="var(--ink-3)">{unit}</text>
      </svg>
      <figcaption className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
        {lines.map((l) => (
          <span key={l.label} className="flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-4" style={{ background: l.color }} />
            {l.label}{l.note ? <span className="text-ink-3">{l.note}</span> : null}
            {hovered.length > 0 && <span className="font-mono text-ink">{fmt(l.points.find((p) => p.date === hover)?.value)}</span>}
          </span>
        ))}
        {hover && <span className="text-ink-3">{longDate(hover)}</span>}
      </figcaption>
    </figure>
  );
}

/** Share of the area with a strong drop (down) or rise (up) at each Pass. */
export function ChangeBars({ rows, threshold, unit, eventDate, width = 560, height = 200 }: { rows: { date: string; drop_share: number; rise_share: number }[]; threshold: number; unit: string; eventDate?: string | null; width?: number; height?: number }) {
  if (!rows.length) return null;
  const M = { top: 14, right: 10, bottom: 34, left: 46 };
  const max = Math.max(0.001, ...rows.map((r) => Math.max(r.drop_share, r.rise_share)));
  const bw = (width - M.left - M.right) / rows.length;
  const mid = (height - M.top - M.bottom) / 2 + M.top;
  const h = (v: number) => (v / max) * ((height - M.top - M.bottom) / 2);
  const firstAfter = eventDate ? rows.find((r) => r.date >= eventDate)?.date : null;
  return (
    <figure className="m-0">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full" role="img" aria-label={`Share of the area changing by more than ${threshold} ${unit} at each Pass`}>
        <line x1={M.left} x2={width - M.right} y1={mid} y2={mid} stroke="var(--ink-3)" />
        {[max, max / 2].map((v) => (
          <g key={v}>
            <text x={M.left - 6} y={mid - h(v) + 3.5} textAnchor="end" fontSize="10" fill="var(--ink-3)" fontFamily="var(--font-plex-mono)">{(v * 100).toFixed(v * 100 < 1 ? 2 : 1)}%</text>
            <text x={M.left - 6} y={mid + h(v) + 3.5} textAnchor="end" fontSize="10" fill="var(--ink-3)" fontFamily="var(--font-plex-mono)">{(v * 100).toFixed(v * 100 < 1 ? 2 : 1)}%</text>
          </g>
        ))}
        {rows.map((r, i) => {
          const cx = M.left + i * bw + bw / 2;
          return (
            <g key={r.date}>
              <rect x={cx - bw * 0.32} y={mid - h(r.rise_share)} width={bw * 0.64} height={h(r.rise_share)} fill="var(--rise)"><title>{`${longDate(r.date)}: rose on ${(r.rise_share * 100).toFixed(2)}%`}</title></rect>
              <rect x={cx - bw * 0.32} y={mid} width={bw * 0.64} height={h(r.drop_share)} fill="var(--drop)"><title>{`${longDate(r.date)}: fell on ${(r.drop_share * 100).toFixed(2)}%`}</title></rect>
              {(i % Math.ceil(rows.length / 10) === 0 || r.date === firstAfter) && (
                <text x={cx} y={height - 18} textAnchor="middle" fontSize="9.5" fill={r.date === firstAfter ? "var(--drop)" : "var(--ink-3)"}>{shortDate(r.date)}</text>
              )}
            </g>
          );
        })}
        <text x={M.left} y={10} fontSize="10" fill="var(--rise)">rose by more than {threshold} {unit}</text>
        <text x={M.left} y={height - 4} fontSize="10" fill="var(--drop)">fell by more than {threshold} {unit} (since the previous Pass)</text>
      </svg>
    </figure>
  );
}

/** How a layer's values are spread over the study area. */
export function HistogramChart({ hist, unit, color = "var(--accent)", width = 360, height = 130 }: { hist: Histogram; unit: string; color?: string; width?: number; height?: number }) {
  const M = { top: 6, right: 6, bottom: 22, left: 6 };
  const max = Math.max(1, ...hist.counts);
  const n = hist.counts.length;
  const bw = (width - M.left - M.right) / n;
  const total = hist.counts.reduce((a, b) => a + b, 0);
  return (
    <figure className="m-0">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full" role="img" aria-label={`Distribution of values, ${unit}`}>
        {hist.counts.map((c, i) => (
          <rect key={i} x={M.left + i * bw + 0.5} width={Math.max(0.5, bw - 1)} y={M.top + (1 - c / max) * (height - M.top - M.bottom)} height={(c / max) * (height - M.top - M.bottom)} fill={color} opacity={0.85}>
            <title>{`${fmt(hist.edges[i])} to ${fmt(hist.edges[i + 1])} ${unit}: ${((c / total) * 100).toFixed(1)}%`}</title>
          </rect>
        ))}
        <text x={M.left} y={height - 6} fontSize="10" fill="var(--ink-3)" fontFamily="var(--font-plex-mono)">{fmt(hist.edges[0])}</text>
        <text x={width / 2} y={height - 6} fontSize="10" fill="var(--ink-3)" textAnchor="middle">{unit}</text>
        <text x={width - M.right} y={height - 6} fontSize="10" fill="var(--ink-3)" textAnchor="end" fontFamily="var(--font-plex-mono)">{fmt(hist.edges[n])}</text>
      </svg>
    </figure>
  );
}

const COLLECTION_COLOR: Record<string, string> = { PROVISIONAL_V1: "#d97706", VALIDATED_V1: "#059669" };

/** Every Pass on a time line: collection (colour), the instrument gap, the event, and how much of the area each Pass covered. */
export function PassTimeline({ passes, coverage, eventDate, width = 560, height = 110 }: { passes: PassInfo[]; coverage?: Record<string, number>; eventDate?: string | null; width?: number; height?: number }) {
  const M = { top: 10, right: 14, bottom: 26, left: 14 };
  const t0 = day(passes[0].date);
  const t1 = day(passes[passes.length - 1].date);
  const x = (t: number) => M.left + ((t - t0) / Math.max(1, t1 - t0)) * (width - M.left - M.right);
  const base = height - M.bottom;
  const barH = height - M.top - M.bottom - 14;
  const maxCov = coverage ? Math.max(1, ...Object.values(coverage)) : 1;
  const gap = ["2026-07-27", "2026-08-10"].map(day);
  return (
    <figure className="m-0">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full" role="img" aria-label={`${passes.length} Passes from ${longDate(passes[0].date)} to ${longDate(passes[passes.length - 1].date)}`}>
        {gap[0] > t0 && gap[1] < t1 && <rect x={x(gap[0])} y={M.top} width={x(gap[1]) - x(gap[0])} height={base - M.top} fill="var(--ink-3)" opacity={0.15}><title>27 July to 10 August 2026: instrument gap</title></rect>}
        <line x1={M.left} x2={width - M.right} y1={base} y2={base} stroke="var(--ink-3)" />
        {passes.map((p) => {
          const c = coverage?.[p.date];
          const hh = c !== undefined ? Math.max(3, (c / maxCov) * barH) : barH * 0.6;
          return (
            <rect key={p.date} x={x(day(p.date)) - 2.5} y={base - hh} width={5} height={hh} rx={1} fill={COLLECTION_COLOR[p.collection] ?? "var(--accent)"}>
              <title>{`${longDate(p.date)} · ${p.collection} · Stack ${p.stack}${c !== undefined ? ` · ${c.toLocaleString("en-GB")} cells with data` : ""}`}</title>
            </rect>
          );
        })}
        {eventDate && day(eventDate) >= t0 && day(eventDate) <= t1 && (
          <g>
            <line x1={x(day(eventDate))} x2={x(day(eventDate))} y1={M.top - 4} y2={base} stroke="var(--drop)" strokeDasharray="3 3" />
            <text x={x(day(eventDate)) + 3} y={M.top + 4} fontSize="10" fill="var(--drop)">event</text>
          </g>
        )}
        {monthTicks(t0, t1).map((t) => <text key={t.t} x={x(t.t)} y={height - 8} textAnchor="middle" fontSize="10" fill="var(--ink-3)">{t.text}</text>)}
      </svg>
      <figcaption className="mt-1 flex flex-wrap gap-x-4 text-xs text-ink-2">
        {Object.entries(COLLECTION_COLOR).filter(([k]) => passes.some((p) => p.collection === k)).map(([k, c]) => (
          <span key={k} className="flex items-center gap-1.5"><span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: c }} />{k === "VALIDATED_V1" ? "Validated" : "Provisional"} collection</span>
        ))}
        {coverage && <span className="text-ink-3">Bar height: share of the area with data on that Pass</span>}
      </figcaption>
    </figure>
  );
}
