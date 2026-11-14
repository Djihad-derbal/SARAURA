"use client";

import type { CSSProperties } from "react";

/**
 * The mood behind each chapter of the home page's story, cross-faded as the chapter takes the screen:
 *   space   the default: a teal glow under the Earth
 *   city    Mexico City at dusk: a sodium-lit skyline, dust, and radar interferogram fringes contracting towards
 *           the centre of the sinking bowl (what NISAR actually sees over subsiding ground)
 *   fire    Jijel after the fire: a red heat glow, drifting smoke, embers rising over a burned ridge
 *   forest  Washington: misty pine ridges under moonlight, with pollen drifting over the regrowth
 * Everything is drawn from a fixed seed, so the server and browser render the same thing.
 */

export type Theme = "space" | "city" | "fire" | "forest";

function rng(seed: number) {
  let a = seed;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

type Mote = { left: number; top: number; size: number; dur: number; delay: number; dx: number };
function motes(seed: number, n: number, size: [number, number], dur: [number, number]): Mote[] {
  const r = rng(seed);
  return Array.from({ length: n }, () => ({
    left: r() * 100,
    top: 55 + r() * 45,
    size: size[0] + r() * (size[1] - size[0]),
    dur: dur[0] + r() * (dur[1] - dur[0]),
    delay: -r() * dur[1],
    dx: (r() - 0.5) * 160,
  }));
}
const moteStyle = (m: Mote, extra: CSSProperties = {}): CSSProperties => ({
  left: `${m.left}%`, top: `${m.top}%`, width: m.size, height: m.size,
  ["--dur" as string]: `${m.dur}s`, ["--delay" as string]: `${m.delay}s`, ["--dx" as string]: `${m.dx}px`, ...extra,
});

// ---------------------------------------------------------------- city: a skyline with lit windows
const SKY_W = 1600;
const SKY_H = 240;
const CITY = (() => {
  const r = rng(7);
  let x = 0;
  let d = `M0 ${SKY_H}`;
  const windows: { x: number; y: number; tw: boolean; dur: number; delay: number }[] = [];
  while (x < SKY_W) {
    const w = 28 + r() * 62;
    const mid = 1 - Math.abs(x / SKY_W - 0.55) * 1.4; // taller towards the centre, like downtown
    const h = 30 + r() * 70 + Math.max(0, mid) * r() * 120;
    d += ` L${x.toFixed(0)} ${(SKY_H - h).toFixed(0)} L${(x + w).toFixed(0)} ${(SKY_H - h).toFixed(0)}`;
    for (let wy = SKY_H - h + 8; wy < SKY_H - 6; wy += 11)
      for (let wx = x + 6; wx < x + w - 6; wx += 9)
        if (r() < 0.2) windows.push({ x: wx, y: wy, tw: r() < 0.08, dur: 3 + r() * 6, delay: -r() * 9 });
    x += w + (r() < 0.25 ? 6 + r() * 14 : 0);
  }
  d += ` L${SKY_W} ${SKY_H} Z`;
  return { d, windows };
})();
const DUST = motes(11, 26, [1.5, 3.2], [16, 30]);
const FRINGE = ["#ff5f6d", "#ffc371", "#f9f871", "#7ee8a1", "#4fc3f7", "#8e7cff", "#e86fd8"];

function City() {
  return (
    <>
      <div className="absolute inset-0" style={{ background: "linear-gradient(180deg, #0b0a1c 0%, #170d20 42%, #2f1419 74%, #4a2210 100%)" }} />
      <div className="amb-pulse absolute inset-x-0 bottom-0 h-[60%]" style={{ background: "radial-gradient(70% 70% at 50% 100%, rgb(246 160 77 / 0.32), transparent 70%)" }} />
      {/* interferogram fringes over the sinking bowl, behind the scene */}
      <svg className="absolute left-1/2 top-[30%] h-[70vmin] w-[110vmin] -translate-x-1/2 -translate-y-1/2 opacity-[0.22] mix-blend-screen md:left-[66%] md:top-1/2"
        viewBox="-200 -100 400 200" aria-hidden>
        {FRINGE.map((c, i) => (
          <ellipse key={c} className="amb-fringe" cx="0" cy="0" rx="190" ry="92" fill="none" stroke={c} strokeWidth="9"
            style={{ ["--delay" as string]: `${(-i * 14) / FRINGE.length}s` }} />
        ))}
      </svg>
      <svg className="absolute inset-x-0 bottom-0 h-[24vh] w-full" viewBox={`0 0 ${SKY_W} ${SKY_H}`} preserveAspectRatio="xMidYMax slice" aria-hidden>
        <path d={CITY.d} fill="#08050a" />
        {CITY.windows.map((w, i) => (
          <rect key={i} x={w.x} y={w.y} width="4" height="5" fill="#f6b56a" opacity={w.tw ? undefined : 0.55}
            className={w.tw ? "amb-twinkle" : undefined} style={w.tw ? { ["--dur" as string]: `${w.dur}s`, ["--delay" as string]: `${w.delay}s` } : undefined} />
        ))}
      </svg>
      {DUST.map((m, i) => (
        <span key={i} className="amb-rise absolute rounded-full bg-[#f6c08a]" style={moteStyle(m, { opacity: 0.5 })} />
      ))}
    </>
  );
}

// ---------------------------------------------------------------- fire: a burned ridge under embers
const RIDGE = (() => {
  const r = rng(23);
  const W = 1600, H = 260;
  const y = (x: number) => 150 + Math.sin(x / 190) * 32 + Math.sin(x / 67 + 1.3) * 12;
  let d = `M0 ${H}`;
  for (let x = 0; x <= W; x += 20) d += ` L${x} ${y(x).toFixed(1)}`;
  d += ` L${W} ${H} Z`;
  // dead trunks along the crest, a few with bare branches
  let trunks = "";
  for (let x = 30; x < W; x += 34 + r() * 60) {
    const b = y(x) + 4, h = 30 + r() * 55, t = b - h;
    trunks += ` M${x.toFixed(0)} ${b.toFixed(0)} L${(x + (r() - 0.5) * 6).toFixed(0)} ${t.toFixed(0)}`;
    if (r() < 0.7) {
      const by = b - h * (0.45 + r() * 0.3), s = r() < 0.5 ? -1 : 1;
      trunks += ` M${x.toFixed(0)} ${by.toFixed(0)} l${(s * (8 + r() * 10)).toFixed(0)} ${(-8 - r() * 10).toFixed(0)}`;
    }
  }
  return { d, trunks, W, H };
})();
const EMBERS = motes(5, 44, [2, 4.5], [7, 15]);
const SMOKE = [
  { left: "-10%", top: "8%", w: "70vw", h: "36vh", dur: 46, delay: 0 },
  { left: "40%", top: "22%", w: "60vw", h: "30vh", dur: 38, delay: -12 },
  { left: "10%", top: "46%", w: "80vw", h: "28vh", dur: 52, delay: -25 },
];

function Fire() {
  return (
    <>
      <div className="absolute inset-0" style={{ background: "linear-gradient(180deg, #0c0404 0%, #170605 50%, #2e0c05 82%, #4a1406 100%)" }} />
      <div className="amb-pulse absolute inset-x-0 bottom-0 h-[70%]" style={{ background: "radial-gradient(60% 65% at 50% 100%, rgb(255 96 32 / 0.42), transparent 72%)" }} />
      {SMOKE.map((s, i) => (
        <div key={i} className="amb-drift absolute rounded-full blur-3xl"
          style={{ left: s.left, top: s.top, width: s.w, height: s.h, background: "rgb(120 96 88 / 0.14)", ["--dur" as string]: `${s.dur}s`, ["--delay" as string]: `${s.delay}s` }} />
      ))}
      <svg className="absolute inset-x-0 bottom-0 h-[26vh] w-full" viewBox={`0 0 ${RIDGE.W} ${RIDGE.H}`} preserveAspectRatio="xMidYMax slice" aria-hidden>
        <defs>
          <linearGradient id="amb-crest" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#ff6a2b" stopOpacity="0.55" />
            <stop offset="0.12" stopColor="#1a0705" stopOpacity="1" />
            <stop offset="1" stopColor="#070202" />
          </linearGradient>
        </defs>
        <path d={RIDGE.trunks} stroke="#0a0302" strokeWidth="4" strokeLinecap="round" fill="none" />
        <path d={RIDGE.d} fill="url(#amb-crest)" />
      </svg>
      {EMBERS.map((m, i) => (
        <span key={i} className="amb-rise absolute rounded-full"
          style={moteStyle(m, { background: i % 3 ? "#ff8a3d" : "#ffd27a", boxShadow: "0 0 8px 2px rgb(255 120 40 / 0.7)", opacity: 0.8 })} />
      ))}
    </>
  );
}

// ---------------------------------------------------------------- forest: misty pine ridges
function pines(seed: number, base: number, amp: number, size: [number, number]) {
  const r = rng(seed);
  const W = 1600, H = 300;
  const y = (x: number) => base + Math.sin(x / 230 + seed) * amp + Math.sin(x / 90 + seed * 2) * amp * 0.3;
  let d = `M0 ${H}`;
  for (let x = 0; x <= W; x += 20) d += ` L${x} ${y(x).toFixed(1)}`;
  d += ` L${W} ${H} Z`;
  for (let x = 6; x < W; x += 9 + r() * 16) {
    const b = y(x) + 6, h = size[0] + r() * (size[1] - size[0]), w = h * 0.36;
    // two tiers, like a conifer
    d += ` M${(x - w / 2).toFixed(0)} ${b.toFixed(0)} L${x.toFixed(0)} ${(b - h).toFixed(0)} L${(x + w / 2).toFixed(0)} ${b.toFixed(0)} Z`;
    d += ` M${(x - w * 0.62).toFixed(0)} ${(b + 2).toFixed(0)} L${x.toFixed(0)} ${(b - h * 0.55).toFixed(0)} L${(x + w * 0.62).toFixed(0)} ${(b + 2).toFixed(0)} Z`;
  }
  return d;
}
const FAR = pines(3, 150, 30, [24, 46]);
const NEAR = pines(9, 205, 22, [40, 78]);
const POLLEN = motes(17, 24, [2, 3.5], [14, 26]);

function Forest() {
  return (
    <>
      <div className="absolute inset-0" style={{ background: "linear-gradient(180deg, #020b08 0%, #04140e 48%, #082419 80%, #0d3122 100%)" }} />
      <div className="absolute inset-0" style={{ background: "radial-gradient(45% 40% at 18% 8%, rgb(170 240 210 / 0.10), transparent 70%)" }} />
      <svg className="absolute inset-x-0 bottom-0 h-[34vh] w-full" viewBox="0 0 1600 300" preserveAspectRatio="xMidYMax slice" aria-hidden>
        <path d={FAR} fill="#0a281c" opacity="0.9" />
        <path d={NEAR} fill="#04150e" />
      </svg>
      {[{ top: "58%", dur: 44, delay: 0, o: 0.09 }, { top: "72%", dur: 36, delay: -18, o: 0.12 }].map((m, i) => (
        <div key={i} className="amb-drift absolute -left-[15%] h-[22vh] w-[130%] rounded-full blur-3xl"
          style={{ top: m.top, background: `rgb(190 235 215 / ${m.o})`, ["--dur" as string]: `${m.dur}s`, ["--delay" as string]: `${m.delay}s` }} />
      ))}
      {POLLEN.map((m, i) => (
        <span key={i} className="amb-rise absolute rounded-full bg-[#c8f59a]"
          style={moteStyle(m, { boxShadow: "0 0 6px rgb(200 245 154 / 0.7)", opacity: 0.6 })} />
      ))}
    </>
  );
}

function Space() {
  return <div className="absolute inset-0 bg-[radial-gradient(70%_60%_at_50%_100%,rgba(45,212,191,0.10),transparent_70%)]" />;
}

const LAYERS: [Theme, () => React.ReactElement][] = [["space", Space], ["city", City], ["fire", Fire], ["forest", Forest]];

export default function Ambience({ theme }: { theme: Theme }) {
  return (
    <div className="pointer-events-none fixed inset-0 z-0 overflow-hidden" aria-hidden>
      {LAYERS.map(([t, Layer]) => (
        <div key={t} className="amb absolute inset-0" data-on={t === theme}>
          <Layer />
        </div>
      ))}
    </div>
  );
}
