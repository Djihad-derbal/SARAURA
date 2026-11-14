"use client";

import { motion, useTransform, type MotionValue } from "motion/react";
import { iso, phase, pts, shade, type Pt } from "./iso";

/**
 * Jijel after the August 2026 fires, as a scroll-driven isometric hillside (p from 0 to 1):
 *   0.00-0.30  the forest burns; NISAR's radar maps the burn through the smoke
 *   0.30-0.45  ash: steep burned slopes above a village and a road
 *   0.45-0.72  winter rain: mud follows the channel down to the village and across the road
 *   0.72-1.00  what to do first: barriers on the slope, the road closes in heavy rain, saplings after the rains
 */

const O: Pt = [300, 150];
const NX = 9;
const NY = 7;
const CH = 4.5; // channel x

function h(x: number, y: number) {
  const slope = 3 * Math.pow(Math.max(0, 1 - y / NY), 1.25);
  const ridge = 0.32 * Math.sin(x * 0.9 + 0.4);
  const valley = 0.85 * Math.exp(-((x - CH) ** 2) / 1.6) * (1 - y / (NY + 1));
  return Math.max(0, slope + ridge - valley);
}
const burnedAt = (x: number, y: number) => x >= 1 && x <= 8 && y < 4.4 - 0.5 * Math.sin(x * 1.3);
const P = (x: number, y: number, z = h(x, y)) => iso(x, y, z, ...O);

type Cell = { x: number; y: number; top: string; light: number; burned: boolean; tree: Pt | null };
const CELLS: Cell[] = [];
for (let y = 0; y < NY; y++)
  for (let x = 0; x < NX; x++) {
    const q = [P(x, y), P(x + 1, y), P(x + 1, y + 1), P(x, y + 1)];
    const light = 0.82 + 0.32 * (h(x, y + 1) - h(x + 1, y)) * 0.6 + (h(x, y) - h(x, y + 1)) * 0.08;
    const village = y >= 5.5 && x >= 3 && x <= 7;
    const road = y === 5;
    CELLS.push({ x, y, top: pts(q), light: Math.max(0.55, Math.min(1.25, light)), burned: burnedAt(x + 0.5, y + 0.5), tree: village || road ? null : P(x + 0.5, y + 0.5) });
  }
CELLS.sort((a, b) => a.x + a.y - (b.x + b.y));

const FOREST = "#2f6b4a";
const ASH = "#3d302a";
const mud = (() => {
  const out: Pt[] = [];
  for (let y = 0.3; y <= 6.7; y += 0.25) out.push(P(CH + 0.15 * Math.sin(y * 1.7), y, h(CH, y) + 0.04));
  return `M${pts(out).replace(/ /g, " L")}`;
})();
const roadPts = (x0: number, x1: number) => {
  const out: Pt[] = [];
  for (let x = x0; x <= x1 + 1e-6; x += 0.25) out.push(P(x, 5.5, h(x, 5.5) + 0.04));
  return pts(out);
};
const HOUSES: [number, number][] = [[3.4, 6.1], [5.6, 6.0], [6.4, 6.5], [4.2, 6.6]];

function CellView({ c, p }: { c: Cell; p: MotionValue<number> }) {
  const char = useTransform(p, [0.22, 0.32], [0, 1]);
  const green = useTransform(p, (v) => (c.burned ? 1 - phase(v, 0.1, 0.24) : 1));
  const fire = useTransform(p, [0.05, 0.1, 0.24, 0.3], [0, 1, 1, 0]);
  const sapling = useTransform(p, [0.84, 0.96], [0, 1]);
  const t = c.tree;
  return (
    <g>
      <polygon points={c.top} fill={shade(FOREST, c.light)} stroke="#00000018" strokeWidth="0.5" />
      {c.burned && <motion.polygon points={c.top} fill={shade(ASH, c.light)} style={{ opacity: char }} />}
      {t && (
        <g>
          <motion.g style={{ opacity: green }}>
            <polygon points={`${t[0] - 6},${t[1]} ${t[0] + 6},${t[1]} ${t[0]},${t[1] - 17}`} fill={shade("#3f8f5f", c.light)} />
          </motion.g>
          {c.burned && (
            <>
              <motion.g style={{ opacity: fire }}>
                <polygon className="flicker" points={`${t[0] - 6},${t[1]} ${t[0] + 6},${t[1]} ${t[0]},${t[1] - 19}`} fill="#f97316" />
                <polygon className="flicker" style={{ animationDelay: "0.3s" }} points={`${t[0] - 3},${t[1] - 2} ${t[0] + 3},${t[1] - 2} ${t[0]},${t[1] - 13}`} fill="#fde047" />
              </motion.g>
              <motion.line x1={t[0]} y1={t[1]} x2={t[0]} y2={t[1] - 13} stroke="#16100d" strokeWidth="1.8" style={{ opacity: char }} />
              <motion.g style={{ scale: sapling, originX: `${t[0] + 7}px`, originY: `${t[1]}px` }}>
                <polygon points={`${t[0] + 3},${t[1]} ${t[0] + 11},${t[1]} ${t[0] + 7},${t[1] - 10}`} fill="#4ade80" />
              </motion.g>
            </>
          )}
        </g>
      )}
    </g>
  );
}

function Barrier({ x, y, p, i }: { x: number; y: number; p: MotionValue<number>; i: number }) {
  const o = useTransform(p, [0.74 + i * 0.012, 0.8 + i * 0.012], [0, 1]);
  const a = P(x - 0.32, y);
  const b = P(x + 0.32, y);
  return <motion.line x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke="#b07a46" strokeWidth="3" strokeLinecap="round" style={{ opacity: o }} />;
}

export default function AfterFire({ p, className = "" }: { p: MotionValue<number>; className?: string }) {
  const smoke = useTransform(p, [0.04, 0.12, 0.3, 0.4], [0, 0.9, 0.9, 0]);
  const scan = useTransform(p, [0.08, 0.14, 0.3, 0.36], [0, 1, 1, 0]);
  const cloudY = useTransform(p, [0.42, 0.52], [-80, 0]);
  const rain = useTransform(p, [0.46, 0.52, 0.72, 0.78], [0, 1, 1, 0]);
  const mudLen = useTransform(p, [0.5, 0.68], [0, 1]);
  const alarm = useTransform(p, [0.64, 0.7], [0, 1]);
  const solve = useTransform(p, [0.76, 0.86], [0, 1]);
  const label1 = useTransform(p, [0.12, 0.18, 0.3, 0.36], [0, 1, 1, 0]);
  const label2 = useTransform(p, [0.6, 0.66, 0.72, 0.76], [0, 1, 1, 0]);
  const cross = P(CH, 5.5, h(CH, 5.5) + 0.04);
  const village = P(5, 6.4, h(5, 6.4));
  const sat: Pt = [96, 30];
  const barriers = CELLS.filter((c) => c.burned && (c.x + c.y) % 2 === 0).map((c) => [c.x + 0.5, c.y + 0.75] as [number, number]);
  return (
    <svg viewBox="0 0 600 520" className={className} role="img" aria-label="An isometric burned hillside above a village: radar maps the burn through smoke, rain sends mud down a channel, then barriers, a road closure and new trees">
      <defs>
        <linearGradient id="af-beam" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#5eead4" stopOpacity="0.6" />
          <stop offset="1" stopColor="#5eead4" stopOpacity="0" />
        </linearGradient>
        <filter id="af-blur"><feGaussianBlur stdDeviation="6" /></filter>
      </defs>

      {CELLS.map((c) => <CellView key={`${c.x},${c.y}`} c={c} p={p} />)}

      {/* road and village */}
      <polyline points={roadPts(0, NX)} fill="none" stroke="#2b2f33" strokeWidth="7" strokeLinecap="round" />
      <polyline points={roadPts(0, NX)} fill="none" stroke="#9aa5ad" strokeWidth="1" strokeDasharray="4 5" />
      <motion.polyline points={roadPts(CH - 0.8, CH + 0.8)} fill="none" stroke="#d7191c" strokeWidth="7" strokeLinecap="round" style={{ opacity: alarm }} />
      {HOUSES.map(([x, y]) => {
        const c = P(x, y, h(x, y));
        return (
          <g key={`${x}${y}`} transform={`translate(${c[0]} ${c[1]})`}>
            <polygon points="-9,0 0,5 0,-6 -9,-11" fill="#c9b79c" />
            <polygon points="0,5 9,0 9,-11 0,-6" fill="#a8957b" />
            <polygon points="-10,-11 0,-18 10,-11 0,-5" fill="#b4533c" />
          </g>
        );
      })}

      {/* mud down the channel */}
      <motion.path d={mud} fill="none" stroke="#8b5a2b" strokeWidth="7" strokeLinecap="round" style={{ pathLength: mudLen }} />
      <motion.path d={mud} fill="none" stroke="#c08a4f" strokeWidth="2.5" strokeLinecap="round" style={{ pathLength: mudLen }} />
      <motion.circle cx={village[0]} cy={village[1] - 6} r="30" fill="none" stroke="#d7191c" strokeWidth="2" style={{ opacity: alarm }} className="alarm-ring" />

      {/* smoke, and the radar that sees through it */}
      <motion.g style={{ opacity: smoke }} filter="url(#af-blur)">
        {[[200, 150], [280, 120], [360, 140], [240, 190], [330, 180], [420, 170]].map(([x, y], i) => (
          <circle key={i} className="smoke" style={{ animationDelay: `${i * 0.5}s` }} cx={x} cy={y} r={26 + (i % 3) * 8} fill="#8a8f94" fillOpacity="0.55" />
        ))}
      </motion.g>
      <motion.g style={{ opacity: scan }}>
        <polygon points={`${sat[0]},${sat[1] + 8} ${P(1, 0).join(",")} ${P(8, 4.5).join(",")}`} fill="url(#af-beam)" opacity="0.55" />
      </motion.g>
      <g transform={`translate(${sat[0]} ${sat[1]}) rotate(18)`}>
        <rect x="-26" y="-3" width="16" height="6" fill="#38bdf8" />
        <rect x="10" y="-3" width="16" height="6" fill="#38bdf8" />
        <rect x="-7" y="-5" width="14" height="10" rx="2" fill="#e4f2f4" />
      </g>

      {/* winter rain */}
      <motion.g style={{ y: cloudY, opacity: rain }}>
        <g fill="#5b6770">
          <ellipse cx="300" cy="40" rx="120" ry="24" />
          <ellipse cx="240" cy="30" rx="60" ry="22" />
          <ellipse cx="350" cy="26" rx="70" ry="24" />
        </g>
        <g className="rain" stroke="#9ec9e6" strokeOpacity="0.55" strokeWidth="1.4">
          {Array.from({ length: 26 }, (_, i) => <line key={i} x1={200 + i * 8} y1={60 + (i % 4) * 9} x2={194 + i * 8} y2={76 + (i % 4) * 9} />)}
        </g>
      </motion.g>

      {/* what to do first */}
      {barriers.map(([x, y], i) => <Barrier key={`${x},${y}`} x={x} y={y} p={p} i={i} />)}
      <motion.g style={{ opacity: solve }}>
        <circle cx={cross[0]} cy={cross[1]} r="7" fill="#04111a" stroke="#2dd4bf" strokeWidth="2.5" />
        <g transform={`translate(${cross[0] + 34} ${cross[1] - 40})`}>
          <line x1="0" y1="0" x2="0" y2="34" stroke="#e4f2f4" strokeWidth="2" />
          <rect x="-34" y="-22" width="68" height="24" rx="4" fill="#d7191c" />
          <text x="0" y="-11" textAnchor="middle" fill="#fff" fontSize="8.5" fontWeight="700" fontFamily="var(--font-plex-sans), sans-serif">CLOSED IN</text>
          <text x="0" y="-2" textAnchor="middle" fill="#fff" fontSize="8.5" fontWeight="700" fontFamily="var(--font-plex-sans), sans-serif">HEAVY RAIN</text>
        </g>
      </motion.g>

      {/* labels */}
      <g fontFamily="var(--font-plex-sans), sans-serif" fontSize="12.5">
        <motion.g style={{ opacity: label1 }} transform="translate(410 70)">
          <rect x="0" y="-16" width="170" height="40" rx="8" fill="#08202c" stroke="#2dd4bf" strokeOpacity="0.6" />
          <text x="10" y="0" fill="#e4f2f4" fontWeight="600">Burn map, through smoke</text>
          <text x="10" y="15" fill="#a6c0c6" fontSize="11">L-band radar, day and night</text>
        </motion.g>
        <motion.g style={{ opacity: label2 }} transform="translate(410 420)">
          <rect x="0" y="-16" width="170" height="40" rx="8" fill="#08202c" stroke="#d7191c" strokeOpacity="0.7" />
          <text x="10" y="0" fill="#e4f2f4" fontWeight="600">Mud reaches the village</text>
          <text x="10" y="15" fill="#a6c0c6" fontSize="11">and crosses the road</text>
        </motion.g>
        <motion.g style={{ opacity: solve }}>
          {[["#b07a46", "Barriers on the slope"], ["#d7191c", "Road closes in heavy rain"], ["#4ade80", "Replant after the rains"]].map(([c, l], i) => (
            <g key={l} transform={`translate(${24 + i * 190} 498)`}>
              <rect width="12" height="12" rx="2" fill={c} />
              <text x="18" y="10.5" fill="#e4f2f4" fontSize="12">{l}</text>
            </g>
          ))}
        </motion.g>
      </g>
    </svg>
  );
}
