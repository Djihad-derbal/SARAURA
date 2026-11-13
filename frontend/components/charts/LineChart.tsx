"use client";

import { useId, useState } from "react";
import { longDate, type TsPoint } from "@/lib/api";
import { fmt } from "@/lib/style";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const day = (iso: string) => Date.parse(iso + "T00:00:00Z") / 86400000;

type Props = {
  points: TsPoint[];
  unit: string;
  label: string;
  color?: string;
  eventDate?: string | null;
  currentDate?: string;
  onPick?: (date: string) => void;
  width?: number;
  height?: number;
  /** Static rendering for print: no hover. */
  still?: boolean;
};

export default function LineChart({ points, unit, label, color = "var(--accent)", eventDate, currentDate, onPick, width = 360, height = 200, still }: Props) {
  const [hover, setHover] = useState<number | null>(null);
  const clip = useId();
  const pts = points.filter((p) => Number.isFinite(p.value));
  if (pts.length < 2) return <p className="text-sm text-ink-2">Not enough readings to draw a chart here.</p>;

  const M = { top: 12, right: 12, bottom: 26, left: 44 };
  const t0 = day(pts[0].date);
  const t1 = day(pts[pts.length - 1].date);
  const vals = pts.flatMap((p) => [p.value, p.p25 ?? p.value, p.p75 ?? p.value]);
  let lo = Math.min(...vals);
  let hi = Math.max(...vals);
  const pad = (hi - lo) * 0.08 || 1;
  lo -= pad;
  hi += pad;
  const x = (iso: string) => M.left + ((day(iso) - t0) / Math.max(1, t1 - t0)) * (width - M.left - M.right);
  const y = (v: number) => M.top + ((hi - v) / (hi - lo)) * (height - M.top - M.bottom);

  const span = hi - lo;
  const raw = span / 4;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((k) => k * mag).find((s) => s >= raw) ?? raw;
  const ticksY: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) ticksY.push(+v.toFixed(6));
  const ticksX: { iso: string; text: string }[] = [];
  const d = new Date(pts[0].date + "T00:00:00Z");
  d.setUTCDate(1);
  d.setUTCMonth(d.getUTCMonth() + 1);
  const months = (t1 - t0) / 30;
  const every = months > 9 ? 2 : 1;
  while (d.getTime() / 86400000 <= t1) {
    if (d.getUTCMonth() % every === 0) ticksX.push({ iso: d.toISOString().slice(0, 10), text: MONTHS[d.getUTCMonth()] });
    d.setUTCMonth(d.getUTCMonth() + 1);
  }

  const line = pts.map((p, i) => `${i ? "L" : "M"}${x(p.date).toFixed(1)},${y(p.value).toFixed(1)}`).join("");
  const hasBand = pts.every((p) => p.p25 !== undefined && p.p75 !== undefined);
  const band = hasBand
    ? pts.map((p, i) => `${i ? "L" : "M"}${x(p.date).toFixed(1)},${y(p.p75!).toFixed(1)}`).join("") +
      [...pts].reverse().map((p) => `L${x(p.date).toFixed(1)},${y(p.p25!).toFixed(1)}`).join("") + "Z"
    : "";
  const h = hover !== null ? pts[hover] : null;

  return (
    <figure className="m-0">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full overflow-visible"
        role="img"
        aria-label={`${label} from ${longDate(pts[0].date)} to ${longDate(pts[pts.length - 1].date)}, ${unit}`}
        onMouseLeave={() => setHover(null)}>
        <defs>
          <clipPath id={clip}>
            <rect x={M.left} y={M.top} width={width - M.left - M.right} height={height - M.top - M.bottom} />
          </clipPath>
        </defs>
        {ticksY.map((v) => (
          <g key={v}>
            <line x1={M.left} x2={width - M.right} y1={y(v)} y2={y(v)} stroke="var(--line)" />
            <text x={M.left - 6} y={y(v) + 3.5} textAnchor="end" fontSize="10" fill="var(--ink-3)" fontFamily="var(--font-plex-mono)">{fmt(v)}</text>
          </g>
        ))}
        {ticksX.map((t) => (
          <text key={t.iso} x={x(t.iso)} y={height - 8} textAnchor="middle" fontSize="10" fill="var(--ink-3)">{t.text}</text>
        ))}
        {eventDate && day(eventDate) >= t0 && day(eventDate) <= t1 && (
          <g>
            <line x1={x(eventDate)} x2={x(eventDate)} y1={M.top} y2={height - M.bottom} stroke="var(--drop)" strokeDasharray="3 3" />
            <text x={x(eventDate) + 4} y={M.top + 9} fontSize="10" fill="var(--drop)">event</text>
          </g>
        )}
        {currentDate && <line x1={x(currentDate)} x2={x(currentDate)} y1={M.top} y2={height - M.bottom} stroke="var(--ink-3)" />}
        <g clipPath={`url(#${clip})`}>
          {band && <path d={band} fill={color} opacity={0.16} />}
          <path d={line} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" />
          {pts.map((p, i) => (
            <circle key={p.date} cx={x(p.date)} cy={y(p.value)} r={hover === i || p.date === currentDate ? 4.5 : 3} fill={color} stroke="var(--panel-solid)" strokeWidth={1.5} />
          ))}
        </g>
        {!still &&
          pts.map((p, i) => {
            const a = i ? (x(pts[i - 1].date) + x(p.date)) / 2 : M.left;
            const b = i < pts.length - 1 ? (x(p.date) + x(pts[i + 1].date)) / 2 : width - M.right;
            return (
              <rect key={"h" + p.date} x={a} y={M.top} width={Math.max(1, b - a)} height={height - M.top - M.bottom} fill="transparent"
                onMouseEnter={() => setHover(i)} onClick={() => onPick?.(p.date)} style={{ cursor: onPick ? "pointer" : "default" }} />
            );
          })}
        <text x={4} y={M.top - 2} fontSize="10" fill="var(--ink-3)">{unit}</text>
      </svg>
      <figcaption className="mt-1 min-h-5 text-xs text-ink-2" aria-live="polite">
        {h ? (
          <>
            <span className="font-mono text-ink">{fmt(h.value, unit)}</span> on {longDate(h.date)}
            {h.p25 !== undefined && <span className="text-ink-3"> (middle half {fmt(h.p25)} to {fmt(h.p75)})</span>}
          </>
        ) : (
          <span className="text-ink-3">{label}{hasBand ? ": mean, with the middle half of values shaded" : ""}</span>
        )}
      </figcaption>
    </figure>
  );
}
