"use client";

import { motion, useTransform, type MotionValue } from "motion/react";
import { box, iso, phase, pts, S, shade, type Pt } from "./iso";

/**
 * Mexico City, as a scroll-driven isometric scene in three acts (p from 0 to 1):
 *   0.00-0.30  NISAR scans the city every 12 days (beam and a scan band crossing the ground)
 *   0.30-0.65  the lake clay compacts: the ground sinks into a bowl, so buildings at its rim tilt,
 *              the Metro line breaks into steps and cracks open where neighbouring ground sinks unevenly
 *   0.65-1.00  the answer: the ground takes the "Is it safe to build here?" colours
 */

const O: Pt = [300, 150];
const N = 8;
const BLUE = "#2c7bb6";
const AMBER = "#fdae61";
const RED = "#d7191c";
const RAIL_ROW = 5;

// how much each tile sinks (tile units) at the end of act two: a bowl over the old lake bed, deeper to the east
function bowl(x: number, y: number) {
  const d = Math.hypot((x - 5.1) / 1.15, y - 3.4);
  return Math.pow(Math.max(0, 1 - d / 4), 1.2) * 1.45;
}
const grad = (x: number, y: number) => Math.hypot(bowl(x + 0.5, y) - bowl(x - 0.5, y), bowl(x, y + 0.5) - bowl(x, y - 0.5));

type Tile = { x: number; y: number; s: number; g: number; cls: string; h: number; tilt: number };
const TILES: Tile[] = [];
for (let y = 0; y < N; y++)
  for (let x = 0; x < N; x++) {
    const s = bowl(x + 0.5, y + 0.5);
    const g = grad(x + 0.5, y + 0.5);
    const cls = g > 0.27 || s > 0.85 ? RED : g > 0.12 || s > 0.25 ? AMBER : BLUE;
    // buildings: taller downtown, none on the rail row and a park in one corner
    const seed = (x * 37 + y * 61) % 11;
    // sparse and low enough that the sinking bowl stays visible between them
    const h = y === RAIL_ROW || (x < 2 && y > 5) || seed > 5 || (x + y) % 3 === 0 ? 0 : 0.35 + ((seed * 0.29) % 0.9) + (x > 2 && x < 6 && y < 4 ? 0.45 : 0);
    // lean towards the bowl's centre, more where the ground sinks unevenly
    const dir = Math.sign((5.1 - (x + 0.5)) - (3.4 - (y + 0.5)) || 1);
    TILES.push({ x, y, s, g, cls, h, tilt: dir * Math.min(11, g * 30) });
  }
TILES.sort((a, b) => a.x + a.y - (b.x + b.y)); // painter's order: back to front

function TileView({ t, p }: { t: Tile; p: MotionValue<number> }) {
  const y = useTransform(p, (v) => phase(v, 0.3, 0.62) * t.s * S);
  const answer = useTransform(p, [0.66, 0.82], [0, 0.88]);
  const tilt = useTransform(p, (v) => phase(v, 0.36, 0.64) * t.tilt);
  const crack = useTransform(p, [0.45, 0.64], [0, 1]);
  const wet = useTransform(p, (v) => phase(v, 0.3, 0.62) * Math.min(0.55, t.s * 0.5)); // compacted clay darkens
  const col = box(t.x, t.y, -1.1, 1, 1, 1.1, O);
  const ground = "#a58a68"; // dry lake clay
  const b = t.h > 0 ? box(t.x + 0.18, t.y + 0.18, 0, 0.64, 0.64, t.h, O) : null;
  const top = [iso(t.x, t.y, 0, ...O), iso(t.x + 1, t.y, 0, ...O), iso(t.x + 1, t.y + 1, 0, ...O), iso(t.x, t.y + 1, 0, ...O)];
  const base = iso(t.x + 0.5, t.y + 0.82, 0, ...O);
  return (
    <motion.g style={{ y }}>
      <polygon points={col.left} fill={shade(ground, 0.62)} />
      <polygon points={col.right} fill={shade(ground, 0.48)} />
      <polygon points={pts(top)} fill={ground} stroke="#00000022" strokeWidth="0.6" />
      <motion.polygon points={pts(top)} fill="#2a1d12" style={{ opacity: wet }} />
      <motion.polygon points={pts(top)} fill={t.cls} style={{ opacity: answer }} />
      {t.y === RAIL_ROW && (
        <g>
          <polyline points={pts([iso(t.x, t.y + 0.38, 0.03, ...O), iso(t.x + 1, t.y + 0.38, 0.03, ...O)])} stroke="#e4f2f4" strokeWidth="2" />
          <polyline points={pts([iso(t.x, t.y + 0.62, 0.03, ...O), iso(t.x + 1, t.y + 0.62, 0.03, ...O)])} stroke="#e4f2f4" strokeWidth="2" />
        </g>
      )}
      {t.g > 0.26 && (t.x + t.y) % 2 === 0 && (
        <motion.path d={`M${pts([iso(t.x + 0.15, t.y + 0.5, 0.01, ...O), iso(t.x + 0.4, t.y + 0.3, 0.01, ...O), iso(t.x + 0.6, t.y + 0.65, 0.01, ...O), iso(t.x + 0.88, t.y + 0.45, 0.01, ...O)]).replace(/ /g, " L")}`}
          fill="none" stroke="#1a0f08" strokeWidth="1.6" strokeLinecap="round" style={{ pathLength: crack }} />
      )}
      {b && (
        <motion.g style={{ rotate: tilt, originX: `${base[0]}px`, originY: `${base[1]}px` }}>
          <polygon points={b.left} fill="#6f8796" />
          <polygon points={b.right} fill="#506674" />
          <polygon points={b.top} fill="#a9bfcb" />
        </motion.g>
      )}
    </motion.g>
  );
}

export default function SinkingCity({ p, className = "" }: { p: MotionValue<number>; className?: string }) {
  const scanX = useTransform(p, [0.02, 0.3], [-1, N]);
  const scanOn = useTransform(p, [0, 0.04, 0.28, 0.33], [0, 1, 1, 0]);
  const bandX = useTransform(scanX, (v) => v * 0.866 * S);
  const bandY = useTransform(scanX, (v) => v * 0.5 * S);
  const act2 = useTransform(p, [0.42, 0.5, 0.64, 0.7], [0, 1, 1, 0]);
  const act3 = useTransform(p, [0.7, 0.8], [0, 1]);
  const band = (sx: number) => pts([iso(sx, 0, 0.05, ...O), iso(sx + 0.7, 0, 0.05, ...O), iso(sx + 0.7, N, 0.05, ...O), iso(sx, N, 0.05, ...O)]);
  const sat: Pt = [118, 34];
  return (
    <svg viewBox="0 0 600 520" className={className} role="img" aria-label="An isometric city on lake clay: radar scans it, the ground sinks unevenly, then the safe and unsafe ground is coloured">
      <defs>
        <linearGradient id="sc-beam" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#5eead4" stopOpacity="0.55" />
          <stop offset="1" stopColor="#5eead4" stopOpacity="0" />
        </linearGradient>
      </defs>
      {TILES.map((t) => <TileView key={`${t.x},${t.y}`} t={t} p={p} />)}

      {/* act one: the radar scan */}
      <motion.g style={{ opacity: scanOn }}>
        <polygon points={`${sat[0]},${sat[1] + 8} ${iso(0, 0, 0, ...O).join(",")} ${iso(N, N, 0, ...O).join(",")}`} fill="url(#sc-beam)" opacity="0.45" />
        <motion.polygon points={band(0)} fill="#2dd4bf" style={{ opacity: 0.35, x: bandX, y: bandY }} />
      </motion.g>
      <g transform={`translate(${sat[0]} ${sat[1]}) rotate(18)`}>
        <rect x="-26" y="-3" width="16" height="6" fill="#38bdf8" />
        <rect x="10" y="-3" width="16" height="6" fill="#38bdf8" />
        <rect x="-7" y="-5" width="14" height="10" rx="2" fill="#e4f2f4" />
      </g>
      <text x={sat[0] + 34} y={sat[1] - 2} fill="#a6c0c6" fontSize="11" fontFamily="var(--font-plex-mono), monospace" letterSpacing="1.5">NISAR · EVERY 12 DAYS</text>

      {/* act two: what the radar measured */}
      <motion.g style={{ opacity: act2 }} fontFamily="var(--font-plex-sans), sans-serif" fontSize="12.5">
        <g transform="translate(420 150)">
          <rect x="0" y="-16" width="160" height="40" rx="8" fill="#08202c" stroke="#d7191c" strokeOpacity="0.7" />
          <text x="10" y="0" fill="#e4f2f4" fontWeight="600">−30 cm a year</text>
          <text x="10" y="15" fill="#a6c0c6" fontSize="11">the old lake bed compacts</text>
        </g>
        <g transform="translate(20 300)">
          <rect x="0" y="-16" width="176" height="40" rx="8" fill="#08202c" stroke="#fdae61" strokeOpacity="0.7" />
          <text x="10" y="0" fill="#e4f2f4" fontWeight="600">Uneven sinking</text>
          <text x="10" y="15" fill="#a6c0c6" fontSize="11">walls crack in about 10 years</text>
        </g>
        <g transform="translate(400 430)">
          <rect x="0" y="-16" width="170" height="40" rx="8" fill="#08202c" stroke="#e4f2f4" strokeOpacity="0.4" />
          <text x="10" y="0" fill="#e4f2f4" fontWeight="600">Metro line steps</text>
          <text x="10" y="15" fill="#a6c0c6" fontSize="11">inspect these segments first</text>
        </g>
      </motion.g>

      {/* act three: the answer, as a legend */}
      <motion.g style={{ opacity: act3 }} fontFamily="var(--font-plex-sans), sans-serif" fontSize="12">
        {[[BLUE, "Build normally"], [AMBER, "Build with conditions"], [RED, "Avoid, or special design"]].map(([c, l], i) => (
          <g key={l} transform={`translate(${24 + i * 190} 492)`}>
            <rect width="12" height="12" rx="2" fill={c} />
            <text x="18" y="10.5" fill="#e4f2f4">{l}</text>
          </g>
        ))}
      </motion.g>
    </svg>
  );
}
