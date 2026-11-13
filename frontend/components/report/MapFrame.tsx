/* eslint-disable @next/next/no-img-element */
import type { Bbox } from "@/lib/api";

const merc = (lat: number) => Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360));

function ticks(a: number, b: number, n = 4) {
  const raw = (b - a) / n;
  // Wide areas (a locator map) get whole-degree ticks; small ones finer steps.
  const step = [0.01, 0.02, 0.05, 0.1, 0.2, 0.25, 0.5, 1, 2, 5, 10, 15, 20, 30].find((s) => s >= raw) ?? 30;
  const out: number[] = [];
  for (let v = Math.ceil(a / step) * step; v <= b + 1e-9; v += step) out.push(+v.toFixed(4));
  return out;
}

const dec = (span: number) => (span >= 8 ? 0 : span >= 1.5 ? 1 : 2);
const fmtLon = (v: number, d: number) => `${Math.abs(v).toFixed(d)}°${v < 0 ? "W" : "E"}`;
const fmtLat = (v: number, d: number) => `${Math.abs(v).toFixed(d)}°${v < 0 ? "S" : "N"}`;

/** A map picture with longitude/latitude ticks, a scale bar and a north arrow, so it reads on paper.
 *  projection: "mercator" for our previews (Web Mercator), "plate" for GIBS images (plain lon/lat). */
export default function MapFrame({ src, bbox, alt, caption, projection = "mercator", onDone, overlay, maxRatio = 0.62, tickCount }: { src: string; bbox: Bbox; alt: string; caption?: React.ReactNode; projection?: "mercator" | "plate"; onDone?: () => void; overlay?: Bbox; /** Height may not exceed this share of the column width, so tall areas do not take a whole page. */ maxRatio?: number; tickCount?: number }) {
  const [w, s, e, n] = bbox;
  const yOf = (lat: number) => (projection === "mercator" ? (merc(n) - merc(lat)) / (merc(n) - merc(s)) : (n - lat) / (n - s));
  const xOf = (lon: number) => (lon - w) / (e - w);
  const aspect = projection === "mercator" ? (merc(n) - merc(s)) / (((e - w) * Math.PI) / 180) : (n - s) / (e - w);
  // Scale bar: about a fifth of the width, rounded to a nice number of km.
  const kmWide = ((e - w) * 111.32 * Math.cos((((s + n) / 2) * Math.PI) / 180));
  const widthPct = Math.min(100, (maxRatio / aspect) * 100);
  const nT = tickCount ?? (widthPct < 60 ? 3 : 4);
  const dx = dec(e - w);
  const dy = dec(n - s);
  const nice = [1, 2, 5, 10, 20, 25, 50, 100, 200, 500, 1000].reduce((a, b) => (Math.abs(b - kmWide / 5) < Math.abs(a - kmWide / 5) ? b : a), 1);
  return (
    <figure className="m-0">
      <div className="relative mx-auto mt-1 mb-5 pl-11 pr-2" style={{ maxWidth: `${widthPct}%`, minWidth: "40%" }}>
        <div className="relative w-full border border-neutral-400" style={{ aspectRatio: `${1 / aspect}` }}>
          <img src={src} alt={alt} onLoad={onDone} onError={onDone} className="absolute inset-0 h-full w-full bg-[repeating-conic-gradient(#eef0f3_0_25%,#fff_0_50%)] object-fill [background-size:14px_14px]" />
          {overlay && (
            <div className="absolute border-2 border-red-600" style={{ left: `${xOf(overlay[0]) * 100}%`, right: `${(1 - xOf(overlay[2])) * 100}%`, top: `${yOf(overlay[3]) * 100}%`, bottom: `${(1 - yOf(overlay[1])) * 100}%` }} />
          )}
          <svg className="absolute right-2 top-2 h-9 w-6" viewBox="0 0 24 36" aria-label="North is up">
            <path d="M12 2 L20 22 L12 17 L4 22 Z" fill="#111" stroke="#fff" strokeWidth="1.2" />
            <text x="12" y="34" textAnchor="middle" fontSize="11" fontWeight="700" fill="#111" stroke="#fff" strokeWidth="2.5" paintOrder="stroke">N</text>
          </svg>
          {/* The bar's width is the true fraction of the map width that `nice` km covers. */}
          <div className="absolute bottom-2 left-2 text-[9px] leading-none text-neutral-900" style={{ width: `${(nice / kmWide) * 100}%` }}>
            <div className="h-1.5 w-full border-x-2 border-b-2 border-neutral-900 bg-white/60" />
            <span className="mt-0.5 inline-block rounded bg-white/85 px-1">{nice} km</span>
          </div>
        </div>
        {/* Tick labels sit outside the picture: x along the bottom, y down the left. */}
        <div className="pointer-events-none absolute bottom-0 left-11 right-2 top-0">
          {ticks(w, e, nT).map((v) => (
            <span key={`x${v}`} className="absolute -bottom-4 -translate-x-1/2 whitespace-nowrap text-[9px] text-neutral-600" style={{ left: `${xOf(v) * 100}%` }}>{fmtLon(v, dx)}</span>
          ))}
          {ticks(s, n, nT).map((v) => (
            <span key={`y${v}`} className="absolute -left-11 w-10 -translate-y-1/2 text-right text-[9px] text-neutral-600" style={{ top: `${yOf(v) * 100}%` }}>{fmtLat(v, dy)}</span>
          ))}
        </div>
      </div>
      {caption && <figcaption className="text-xs text-neutral-600">{caption}</figcaption>}
    </figure>
  );
}
