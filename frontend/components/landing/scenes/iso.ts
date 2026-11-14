/** Isometric projection helpers for the story scenes (x right-back, y left-back, z up; units are tiles). */

export const S = 34; // pixels per tile
const COS = 0.866;
const SIN = 0.5;

export type Pt = [number, number];

export function iso(x: number, y: number, z: number, ox: number, oy: number): Pt {
  return [(x - y) * COS * S + ox, (x + y) * SIN * S - z * S + oy];
}

export const pts = (p: Pt[]) => p.map(([a, b]) => `${a.toFixed(1)},${b.toFixed(1)}`).join(" ");

/** The three visible faces of a box, top first; `o` is the projection origin. */
export function box(x: number, y: number, z: number, w: number, d: number, h: number, o: Pt) {
  const P = (a: number, b: number, c: number) => iso(a, b, c, o[0], o[1]);
  const top = [P(x, y, z + h), P(x + w, y, z + h), P(x + w, y + d, z + h), P(x, y + d, z + h)];
  const left = [P(x, y + d, z + h), P(x + w, y + d, z + h), P(x + w, y + d, z), P(x, y + d, z)];
  const right = [P(x + w, y, z + h), P(x + w, y + d, z + h), P(x + w, y + d, z), P(x + w, y, z)];
  return { top: pts(top), left: pts(left), right: pts(right) };
}

/** Shade a hex colour: f < 1 darker, f > 1 lighter. */
export function shade(hex: string, f: number) {
  const n = parseInt(hex.slice(1), 16);
  const c = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => Math.max(0, Math.min(255, Math.round(v * f))));
  return `#${c.map((v) => v.toString(16).padStart(2, "0")).join("")}`;
}

export const clamp01 = (v: number) => Math.max(0, Math.min(1, v));
/** 0 before a, 1 after b, linear in between. */
export const phase = (v: number, a: number, b: number) => clamp01((v - a) / (b - a));
