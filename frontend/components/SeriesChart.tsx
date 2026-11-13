"use client";

import { motion } from "motion/react";
import { useState } from "react";
import { longDate, type SeriesPoint } from "@/lib/api";

// Validated for the dark surface (lightness band, colour-vision separation, contrast).
const SERIES = [
  { key: "HV" as const, color: "var(--series-hv)", name: "HV" },
  { key: "HH" as const, color: "var(--series-hh)", name: "HH" },
];
const W = 320;
const H = 190;
const M = { top: 14, right: 34, bottom: 26, left: 34 };
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const day = (iso: string) => Date.parse(iso + "T00:00:00Z") / 86400000;

type Props = { points: SeriesPoint[]; currentDate?: string; baselineDate?: string; animate: boolean; onPick: (date: string) => void };

export default function SeriesChart({ points, currentDate, baselineDate, animate, onPick }: Props) {
  const [hover, setHover] = useState<number | null>(null);
  const valid = points.filter((p) => typeof p.HV === "number" || typeof p.HH === "number");
  if (valid.length < 2) return <p className="text-sm text-ink-2">Not enough readings at this point to draw a chart.</p>;

  const t0 = day(valid[0].date);
  const t1 = day(valid[valid.length - 1].date);
  const values = valid.flatMap((p) => [p.HV, p.HH]).filter((v): v is number => typeof v === "number");
  const lo = Math.floor(Math.min(...values) - 0.5);
  const hi = Math.ceil(Math.max(...values) + 0.5);
  const x = (iso: string) => M.left + ((day(iso) - t0) / Math.max(1, t1 - t0)) * (W - M.left - M.right);
  const y = (v: number) => M.top + ((hi - v) / (hi - lo)) * (H - M.top - M.bottom);

  const stepY = hi - lo > 8 ? 4 : 2;
  const ticksY: number[] = [];
  for (let v = Math.ceil(lo / stepY) * stepY; v <= hi; v += stepY) ticksY.push(v);
  const ticksX: { iso: string; label: string }[] = [];
  const d = new Date(valid[0].date + "T00:00:00Z");
  d.setUTCDate(1);
  d.setUTCMonth(d.getUTCMonth() + 1);
  while (d.getTime() / 86400000 <= t1) {
    ticksX.push({ iso: d.toISOString().slice(0, 10), label: MONTHS[d.getUTCMonth()] });
    d.setUTCMonth(d.getUTCMonth() + 1);
  }

  const nearest = (clientX: number, rect: DOMRect) => {
    const px = ((clientX - rect.left) / rect.width) * W;
    let best = 0;
    valid.forEach((p, i) => {
      if (Math.abs(x(p.date) - px) < Math.abs(x(valid[best].date) - px)) best = i;
    });
    return best;
  };
  const hp = hover === null ? null : valid[hover];

  return (
    <figure className="m-0">
      <div className="mb-1 flex items-center gap-4 text-xs text-ink-2">
        {SERIES.map((s) => (
          <span key={s.key} className="flex items-center gap-1.5">
            <span className="h-0.5 w-4 rounded-full" style={{ background: s.color }} aria-hidden />
            {s.name}
          </span>
        ))}
        <span className="ml-auto font-mono text-[11px] text-ink-3">dB</span>
      </div>
      <div className="relative">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="block w-full cursor-crosshair touch-none select-none"
          role="img"
          aria-label="Radar backscatter over time at the selected point, for the HV and HH channels"
          onPointerMove={(e) => setHover(nearest(e.clientX, e.currentTarget.getBoundingClientRect()))}
          onPointerLeave={() => setHover(null)}
          onClick={(e) => onPick(valid[nearest(e.clientX, e.currentTarget.getBoundingClientRect())].date)}
        >
          {ticksY.map((v) => (
            <g key={v}>
              <line x1={M.left} x2={W - M.right} y1={y(v)} y2={y(v)} stroke="rgb(255 255 255 / 0.08)" />
              <text x={M.left - 6} y={y(v) + 3.5} textAnchor="end" fontSize="10" fill="var(--ink-3)" className="font-mono">
                {v}
              </text>
            </g>
          ))}
          {ticksX.map((t) => (
            <text key={t.iso} x={x(t.iso)} y={H - 8} textAnchor="middle" fontSize="10" fill="var(--ink-3)" className="font-mono">
              {t.label}
            </text>
          ))}
          {baselineDate && <line x1={x(baselineDate)} x2={x(baselineDate)} y1={M.top} y2={H - M.bottom} stroke="var(--ink-3)" strokeDasharray="3 3" />}
          {currentDate && <line x1={x(currentDate)} x2={x(currentDate)} y1={M.top} y2={H - M.bottom} stroke="var(--accent)" strokeOpacity="0.7" />}
          {hp && <line x1={x(hp.date)} x2={x(hp.date)} y1={M.top} y2={H - M.bottom} stroke="rgb(255 255 255 / 0.35)" />}

          {SERIES.map((s, si) => {
            const pts = valid.filter((p) => typeof p[s.key] === "number");
            const path = pts.map((p, i) => `${i ? "L" : "M"}${x(p.date).toFixed(1)},${y(p[s.key] as number).toFixed(1)}`).join(" ");
            const last = pts[pts.length - 1];
            return (
              <g key={s.key}>
                <motion.path
                  d={path}
                  fill="none"
                  stroke={s.color}
                  strokeWidth="2"
                  strokeLinejoin="round"
                  strokeLinecap="round"
                  initial={animate ? { pathLength: 0 } : false}
                  animate={{ pathLength: 1 }}
                  transition={{ duration: 0.9, delay: si * 0.15, ease: "easeOut" }}
                />
                {pts.map((p, i) => (
                  <motion.circle
                    key={p.date}
                    cx={x(p.date)}
                    cy={y(p[s.key] as number)}
                    r={hp?.date === p.date ? 5 : 4}
                    fill={s.color}
                    stroke="var(--panel-solid)"
                    strokeWidth="2"
                    initial={animate ? { opacity: 0 } : false}
                    animate={{ opacity: 1 }}
                    transition={{ duration: 0.2, delay: animate ? 0.3 + si * 0.15 + (i / pts.length) * 0.6 : 0 }}
                  />
                ))}
                <text x={x(last.date) + 9} y={y(last[s.key] as number) + 3.5} fontSize="11" fill="var(--ink-2)">
                  {s.name}
                </text>
              </g>
            );
          })}
        </svg>
        {hp && (
          <div className="pointer-events-none absolute top-0 rounded-lg border border-line bg-panel-solid px-2.5 py-1.5 text-xs shadow-lg" style={{ left: `${(x(hp.date) / W) * 100}%`, transform: `translateX(${x(hp.date) > W / 2 ? "calc(-100% - 8px)" : "8px"})` }}>
            <div className="mb-0.5 font-mono text-ink-2">{longDate(hp.date)}</div>
            {SERIES.map((s) => (
              <div key={s.key} className="flex items-center gap-1.5 font-mono tabular-nums text-ink">
                <span className="h-2 w-2 rounded-full" style={{ background: s.color }} aria-hidden />
                {s.name} {typeof hp[s.key] === "number" ? `${(hp[s.key] as number).toFixed(1)} dB` : "no data"}
              </div>
            ))}
          </div>
        )}
      </div>
      <details className="mt-2 text-xs text-ink-2">
        <summary className="cursor-pointer py-1 text-ink-3 transition-colors duration-200 hover:text-ink">Show as table</summary>
        <table className="mt-1 w-full font-mono tabular-nums">
          <thead>
            <tr className="text-left text-ink-3">
              <th className="py-1 font-normal">Date</th>
              <th className="py-1 text-right font-normal">HV dB</th>
              <th className="py-1 text-right font-normal">HH dB</th>
            </tr>
          </thead>
          <tbody>
            {valid.map((p) => (
              <tr key={p.date} className="border-t border-line">
                <td className="py-1">{longDate(p.date)}</td>
                <td className="py-1 text-right">{typeof p.HV === "number" ? p.HV.toFixed(1) : "–"}</td>
                <td className="py-1 text-right">{typeof p.HH === "number" ? p.HH.toFixed(1) : "–"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
