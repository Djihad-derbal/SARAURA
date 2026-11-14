"use client";

import { Map as MlMap, Marker, NavigationControl, Popup, setWorkerUrl, type GeoJSONSource, type MapMouseEvent } from "maplibre-gl";
import { motion, useReducedMotion } from "motion/react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  API,
  AREA_LIMIT_KM2,
  LENS_PRODUCT,
  bboxKm2,
  fetchCoverage,
  fetchJob,
  fetchJobs,
  fetchSites,
  longDate,
  startJob,
  type Bbox,
  type Job,
  type Lens,
  type SiteSummary,
} from "@/lib/api";
import { ANCHOR, DEM_SOURCE, buildStyle } from "@/lib/basemap";
import SiteNav from "@/components/SiteNav";
import { LENSES } from "@/lib/style";

type Mode = "showcase" | "explore";
const EMPTY = { type: "FeatureCollection" as const, features: [] };
const today = new Date().toISOString().slice(0, 10);

function boxFeature(b: Bbox) {
  const [w, s, e, n] = b;
  return { type: "Feature" as const, properties: {}, geometry: { type: "Polygon" as const, coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] } };
}

export default function Home() {
  const router = useRouter();
  const params = useSearchParams();
  const reduced = useReducedMotion() ?? false;
  // Explore is the main mode; ?mode=showcase opens the site list.
  const [mode, setMode] = useState<Mode>(params.get("mode") === "showcase" ? "showcase" : "explore");
  const [terrain3d, setTerrain3d] = useState(true);
  const userTilted = useRef(false);
  const [sites, setSites] = useState<SiteSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hover, setHover] = useState<string | null>(null);
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MlMap | null>(null);
  const [ready, setReady] = useState(false);
  const markers = useRef<Record<string, Marker>>({});

  // ---------------------------------------------------------------- map
  useEffect(() => {
    if (!container.current) return;
    setWorkerUrl("/maplibre-gl-worker.mjs");
    let map: MlMap | null = null;
    let spin = 0;
    let cancelled = false;
    buildStyle("globe", true).then((style) => {
      if (cancelled || !container.current) return;
      map = new MlMap({ container: container.current, style, center: [20, 20], zoom: 1.6, attributionControl: { compact: true } });
      map.addControl(new NavigationControl({ visualizePitch: true }), "bottom-right");
      mapRef.current = map;
      map.on("load", () => {
        map!.addSource("coverage", { type: "geojson", data: EMPTY });
        map!.addSource("draw", { type: "geojson", data: EMPTY });
        map!.addLayer({ id: "coverage-fill", type: "fill", source: "coverage", paint: { "fill-color": "#2dd4bf", "fill-opacity": 0.05 } }, ANCHOR);
        map!.addLayer({ id: "coverage-line", type: "line", source: "coverage", paint: { "line-color": "#2dd4bf", "line-opacity": 0.5, "line-width": 1 } }, ANCHOR);
        map!.addLayer({ id: "draw-fill", type: "fill", source: "draw", paint: { "fill-color": "#ffffff", "fill-opacity": 0.12 } });
        map!.addLayer({ id: "draw-line", type: "line", source: "draw", paint: { "line-color": "#ffffff", "line-width": 2, "line-dasharray": [2, 1] } });
        // 3D: real terrain under every layer, and an atmosphere on the globe.
        map!.setTerrain({ source: DEM_SOURCE, exaggeration: 1.5 });
        try {
          map!.setSky({ "sky-color": "#06283a", "horizon-color": "#12586b", "fog-color": "#04111a", "sky-horizon-blend": 0.6, "horizon-fog-blend": 0.6, "fog-ground-blend": 0.4, "atmosphere-blend": ["interpolate", ["linear"], ["zoom"], 0, 1, 6, 0.6, 9, 0] });
        } catch {
          // Older renderers without sky support still get terrain.
        }
        setReady(true);
      });
      // Tilt into the landscape as you zoom in, unless you have set the tilt yourself.
      map.on("pitchstart", (e) => {
        if ((e as unknown as { originalEvent?: Event }).originalEvent) userTilted.current = true;
      });
      map.on("zoomend", () => {
        if (!map || userTilted.current || map.isMoving()) return;
        const z = map.getZoom();
        const want = z >= 9 ? 60 : z >= 6 ? 50 : z >= 4.5 ? 30 : 0;
        if (Math.abs(map.getPitch() - want) > 5) map.easeTo({ pitch: want, duration: reduced ? 0 : 900 });
      });
      // A slow turn of the globe until someone touches it.
      if (!reduced) {
        const step = () => {
          if (!map || map.isMoving() || map.getZoom() > 3) return;
          const c = map.getCenter();
          map.easeTo({ center: [c.lng + 2.5, c.lat], duration: 1000, easing: (t) => t });
        };
        spin = window.setInterval(step, 1000);
        map.once("mousedown", () => clearInterval(spin));
        map.once("touchstart", () => clearInterval(spin));
      }
    });
    return () => {
      cancelled = true;
      clearInterval(spin);
      map?.remove();
      mapRef.current = null;
    };
  }, [reduced]);

  useEffect(() => {
    const ctl = new AbortController();
    fetchSites(ctl.signal)
      .then(setSites)
      .catch((e) => e.name !== "AbortError" && setError("Cannot reach the SARAURA API. Start it on port 8000, then reload."));
    return () => ctl.abort();
  }, []);

  // Site markers, shown in Showcase mode.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || !sites) return;
    for (const s of sites) {
      if (markers.current[s.id]) continue;
      const el = document.createElement("button");
      el.type = "button";
      el.className = "site-marker";
      el.style.setProperty("--lens", LENSES[s.lens].color);
      el.setAttribute("aria-label", `${s.name}: open the Study page`);
      el.innerHTML = `<span></span>`;
      el.addEventListener("click", () => router.push(`/study/${s.id}`));
      el.addEventListener("mouseenter", () => setHover(s.id));
      el.addEventListener("mouseleave", () => setHover(null));
      markers.current[s.id] = new Marker({ element: el }).setLngLat(s.center).addTo(map);
    }
  }, [ready, sites, router]);

  useEffect(() => {
    for (const [id, m] of Object.entries(markers.current)) {
      const el = m.getElement();
      el.style.display = "";
      el.classList.toggle("is-hover", hover === id);
    }
  }, [mode, hover, sites]);

  const flyTo = useCallback((s: SiteSummary) => {
    const map = mapRef.current;
    if (!map) return;
    map.fitBounds([[s.bbox[0], s.bbox[1]], [s.bbox[2], s.bbox[3]]], { padding: 120, maxZoom: 9, pitch: 55, bearing: -12, duration: reduced ? 0 : 2200 });
  }, [reduced]);

  // ---------------------------------------------------------------- Explore: coverage, drawing, jobs
  const [product, setProduct] = useState<"GCOV" | "GUNW">("GCOV");
  const [lens, setLens] = useState<Lens | "">("");
  const [start, setStart] = useState("2026-06-17");
  const [end, setEnd] = useState(today);
  const [eventDate, setEventDate] = useState("");
  const [drawing, setDrawing] = useState(false);
  const [box, setBox] = useState<Bbox | null>(null);
  const [coverage, setCoverage] = useState<{ n: number; note: string | null }>({ n: 0, note: "Zoom in to see where NISAR has looked." });
  const [job, setJob] = useState<Job | null>(null);
  const [jobError, setJobError] = useState<string | null>(null);
  const [recent, setRecent] = useState<Job[]>([]);
  const corner = useRef<[number, number] | null>(null);
  const km2 = box ? bboxKm2(box) : 0;
  const limit = AREA_LIMIT_KM2[product];
  const lensOk = !lens || LENS_PRODUCT[lens].includes(product);
  const needsEvent = lens === "wildfire";

  useEffect(() => {
    if (mode !== "explore") return;
    const ctl = new AbortController();
    fetchJobs(ctl.signal).then(setRecent).catch(() => {});
    return () => ctl.abort();
  }, [mode, job?.status]);

  // Footprints for the current view.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const src = map.getSource("coverage") as GeoJSONSource;
    if (mode !== "explore") {
      src.setData(EMPTY);
      return;
    }
    let ctl: AbortController | null = null;
    let t = 0;
    const load = () => {
      ctl?.abort();
      const b = map.getBounds();
      const bb: Bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()];
      if (map.getZoom() < 4.5 || (bb[2] - bb[0]) * (bb[3] - bb[1]) > 60) {
        src.setData(EMPTY);
        setCoverage({ n: 0, note: "Zoom in to see where NISAR has looked." });
        return;
      }
      ctl = new AbortController();
      setCoverage((c) => ({ ...c, note: "Looking up NISAR footprints…" }));
      fetchCoverage(bb, product, ctl.signal)
        .then((fc) => {
          src.setData(fc as unknown as Parameters<GeoJSONSource["setData"]>[0]);
          setCoverage({ n: fc.features.length, note: null });
        })
        .catch((e) => e.name !== "AbortError" && setCoverage({ n: 0, note: e.message }));
    };
    const onMove = () => {
      clearTimeout(t);
      t = window.setTimeout(load, 500);
    };
    load();
    map.on("moveend", onMove);
    return () => {
      ctl?.abort();
      clearTimeout(t);
      map.off("moveend", onMove);
    };
  }, [mode, product, ready]);

  // Quicklook of a footprint.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || mode !== "explore") return;
    const onClick = (e: MapMouseEvent & { features?: { properties: unknown }[] }) => {
      if (drawing || !e.features?.length) return;
      const p = e.features[0].properties as { id: string; date: string; stack: string; product: string; secondary_date: string | null };
      const img = p.product === "GCOV" ? `<img src="${API}/browse/${p.id}/preview/HV.png" alt="NASA preview of this Granule (HV)" onerror="this.remove()" />` : "";
      const when = p.secondary_date ? `${longDate(p.date)} to ${longDate(p.secondary_date)}` : longDate(p.date);
      new Popup({ className: "quicklook", maxWidth: "260px" })
        .setLngLat(e.lngLat)
        .setHTML(`<strong>${p.product} · Stack ${p.stack}</strong><br/>${when}${img}<a href="/browse">Open raw Granules</a>`)
        .addTo(map);
    };
    map.on("click", "coverage-fill", onClick);
    return () => {
      map.off("click", "coverage-fill", onClick);
    };
  }, [mode, ready, drawing]);

  // Two clicks draw a box.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || !drawing) return;
    const src = map.getSource("draw") as GeoJSONSource;
    map.getCanvas().style.cursor = "crosshair";
    const toBox = (a: [number, number], b: [number, number]): Bbox => [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[0], b[0]), Math.max(a[1], b[1])];
    const onClick = (e: MapMouseEvent) => {
      const p: [number, number] = [e.lngLat.lng, e.lngLat.lat];
      if (!corner.current) {
        corner.current = p;
        return;
      }
      const b = toBox(corner.current, p);
      corner.current = null;
      setBox(b);
      src.setData({ type: "FeatureCollection", features: [boxFeature(b)] });
      setDrawing(false);
      map.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: 160, pitch: 50, duration: reduced ? 0 : 1400, maxZoom: 12 });
    };
    const onMove = (e: MapMouseEvent) => {
      if (!corner.current) return;
      const b = toBox(corner.current, [e.lngLat.lng, e.lngLat.lat]);
      setBox(b);
      src.setData({ type: "FeatureCollection", features: [boxFeature(b)] });
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        corner.current = null;
        setDrawing(false);
      }
    };
    map.on("click", onClick);
    map.on("mousemove", onMove);
    window.addEventListener("keydown", onKey);
    return () => {
      map.getCanvas().style.cursor = "";
      map.off("click", onClick);
      map.off("mousemove", onMove);
      window.removeEventListener("keydown", onKey);
    };
  }, [drawing, ready, reduced]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    if (mode !== "explore") (map.getSource("draw") as GeoJSONSource).setData(EMPTY);
  }, [mode, ready]);

  // Poll a running Analysis, then open it.
  useEffect(() => {
    if (!job || job.status === "done" || job.status === "error") return;
    const t = setInterval(() => {
      fetchJob(job.id)
        .then((j) => {
          setJob(j);
          if (j.status === "done") router.push(`/study/${j.id}`);
        })
        .catch(() => {});
    }, 3000);
    return () => clearInterval(t);
  }, [job, router]);

  const run = () => {
    if (!box) return;
    setJobError(null);
    startJob({ bbox: box, product, start, end, lens: lens || null, event_date: eventDate || null })
      .then((j) => {
        setJob(j);
        if (j.status === "done") router.push(`/study/${j.id}`);
      })
      .catch((e) => setJobError(e.message));
  };

  const ordered = useMemo(() => sites ?? [], [sites]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    map.setTerrain(terrain3d ? { source: DEM_SOURCE, exaggeration: 1.5 } : null);
    if (!terrain3d) map.easeTo({ pitch: 0, duration: reduced ? 0 : 600 });
  }, [terrain3d, ready, reduced]);

  // ---------------------------------------------------------------- render
  return (
    <main className="relative h-dvh w-full overflow-hidden bg-bg">
      <div ref={container} className="h-full w-full" aria-label="Globe" />

      <header className="pointer-events-none absolute inset-x-0 top-0 z-20 flex flex-col gap-2 p-3 sm:p-4">
        <div className="pointer-events-auto"><SiteNav active="research" floating /></div>
        <div className="pointer-events-auto flex items-center gap-2">
          <div className="panel flex p-1" role="tablist" aria-label="Research tools">
            {([["explore", "Any area"], ["showcase", "Showcase Sites"]] as const).map(([m, label]) => (
              <button
                key={m}
                role="tab"
                aria-selected={mode === m}
                onClick={() => setMode(m)}
                className={`h-9 cursor-pointer rounded-lg px-4 text-sm transition-colors duration-200 ${mode === m ? "bg-white/15 text-ink" : "text-ink-2 hover:text-ink"}`}>
                {label}
              </button>
            ))}
          </div>
          <Link href="/browse" className="panel hidden h-11 items-center px-4 text-sm text-ink-2 transition-colors duration-200 hover:text-ink sm:flex">Raw Granules</Link>
        </div>
      </header>

      {error && (
        <div className="panel absolute left-1/2 top-24 z-30 -translate-x-1/2 px-4 py-3 text-sm" role="alert">
          {error}
        </div>
      )}

      {mode === "showcase" && (
        <motion.section
          key="showcase"
          initial={reduced ? false : { opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          className="absolute inset-x-3 bottom-3 z-20 max-h-[45dvh] overflow-y-auto sm:inset-x-auto sm:bottom-auto sm:left-4 sm:top-36 sm:max-h-[calc(100dvh-160px)] sm:w-[380px]"
          aria-label="Showcase Sites">
          <ul className="flex flex-col gap-2">
            {!sites && !error && Array.from({ length: 4 }).map((_, i) => <li key={i} className="panel h-24 animate-pulse" aria-hidden />)}
            {ordered.map((s) => (
              <li key={s.id}>
                <Link
                  href={`/study/${s.id}`}
                  onMouseEnter={() => {
                    setHover(s.id);
                    flyTo(s);
                  }}
                  onMouseLeave={() => setHover(null)}
                  onFocus={() => flyTo(s)}
                  className={`panel block px-4 py-3 transition-colors duration-200 hover:bg-white/10 ${hover === s.id ? "bg-white/10" : ""}`}>
                  <div className="flex items-center gap-2 text-xs">
                    <span className="h-2 w-2 rounded-full" style={{ background: LENSES[s.lens].color }} aria-hidden />
                    <span className="font-medium uppercase tracking-wide" style={{ color: LENSES[s.lens].color }}>{LENSES[s.lens].label}</span>
                    <span className="text-ink-3">· {s.passes} Passes{s.view === "3d" ? " · 3D" : ""}</span>
                    {s.has_model && <span className="ml-auto rounded bg-white/10 px-1.5 py-0.5 text-[11px] text-ink-2">AI Model</span>}
                  </div>
                  <h2 className="mt-1 text-[15px] font-medium leading-snug text-ink">{s.name}</h2>
                  {s.headline && <p className="mt-1 line-clamp-2 text-sm leading-relaxed text-ink-2">{s.headline}</p>}
                </Link>
              </li>
            ))}
          </ul>
        </motion.section>
      )}

      {mode === "explore" && (
        <motion.section
          key="explore"
          initial={reduced ? false : { opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          className="panel absolute inset-x-3 bottom-3 z-20 max-h-[55dvh] overflow-y-auto p-4 sm:inset-x-auto sm:bottom-auto sm:left-4 sm:top-36 sm:max-h-[calc(100dvh-160px)] sm:w-[380px]"
          aria-label="Explore: analyse any area">
          <p className="text-[11px] uppercase tracking-[0.18em] text-ink-3">For research and teaching</p>
          <h2 className="mt-1 text-base font-medium">Every NISAR Pass, on a 3D globe</h2>
          <p className="mt-1 text-sm leading-relaxed text-ink-2">Fly to a Showcase Site, or zoom anywhere: the globe tilts into real terrain as you go. Looking for answers about a place? <Link href="/" className="text-accent underline underline-offset-2">Go to Places</Link>.</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {ordered.map((s) => (
              <button key={s.id} type="button" onClick={() => flyTo(s)} onDoubleClick={() => router.push(`/study/${s.id}`)}
                className="flex h-8 cursor-pointer items-center gap-1.5 rounded-full border border-line px-3 text-xs text-ink-2 transition-colors duration-200 hover:text-ink"
                title={`${s.name}: click to fly there, double-click to open its Study page`}>
                <span className="h-1.5 w-1.5 rounded-full" style={{ background: LENSES[s.lens].color }} aria-hidden />
                {s.name.split(/[,(]/)[0].replace(/ (ground|wildfires|earthquakes|lava flows|maize and soybean season|flood pulse).*/i, "")}
              </button>
            ))}
          </div>
          <label className="mt-2 flex cursor-pointer items-center gap-2 text-xs text-ink-3">
            <input type="checkbox" checked={terrain3d} onChange={(e) => setTerrain3d(e.target.checked)} />
            3D terrain
          </label>

          <h2 className="mt-5 border-t border-line pt-4 text-base font-medium">Analyse any area</h2>
          <p className="mt-1 text-sm leading-relaxed text-ink-2">
            Draw a box where NISAR has looked. You get the radar measurements and, with a Lens, its Baseline. AI Models run only on the Showcase Sites.
          </p>
          <p className="mt-2 text-xs text-ink-3" aria-live="polite">{coverage.note ?? `${coverage.n} calibrated ${product} Granules in view. Click one for a preview.`}</p>

          <fieldset className="mt-4">
            <legend className="text-xs uppercase tracking-wide text-ink-3">Data</legend>
            <div className="mt-2 flex gap-2">
              {(["GCOV", "GUNW"] as const).map((p) => (
                <button key={p} type="button" aria-pressed={product === p} onClick={() => setProduct(p)}
                  className={`h-9 flex-1 cursor-pointer rounded-lg border text-sm transition-colors duration-200 ${product === p ? "border-accent bg-accent/15 text-ink" : "border-line text-ink-2 hover:text-ink"}`}>
                  {p === "GCOV" ? "Backscatter (GCOV)" : "Ground motion (GUNW)"}
                </button>
              ))}
            </div>
          </fieldset>

          <fieldset className="mt-4">
            <legend className="text-xs uppercase tracking-wide text-ink-3">Lens (optional)</legend>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <button type="button" aria-pressed={!lens} onClick={() => setLens("")}
                className={`h-8 cursor-pointer rounded-full border px-3 text-xs transition-colors duration-200 ${!lens ? "border-white/60 text-ink" : "border-line text-ink-2 hover:text-ink"}`}>
                None
              </button>
              {(Object.keys(LENSES) as Lens[]).filter((l) => LENS_PRODUCT[l].includes(product)).map((l) => (
                <button key={l} type="button" aria-pressed={lens === l} onClick={() => setLens(l)}
                  className="h-8 cursor-pointer rounded-full border px-3 text-xs transition-colors duration-200"
                  style={lens === l ? { borderColor: LENSES[l].color, color: "var(--ink)", background: `${LENSES[l].color}26` } : { borderColor: "var(--line)", color: "var(--ink-2)" }}>
                  {LENSES[l].label}
                </button>
              ))}
            </div>
          </fieldset>

          <div className="mt-4 grid grid-cols-2 gap-2">
            <label className="text-xs text-ink-3">From
              <input type="date" value={start} min="2025-10-29" max={end} onChange={(e) => setStart(e.target.value)} className="mt-1 h-9 w-full rounded-lg border border-line bg-black/30 px-2 text-sm text-ink" />
            </label>
            <label className="text-xs text-ink-3">To
              <input type="date" value={end} min={start} max={today} onChange={(e) => setEnd(e.target.value)} className="mt-1 h-9 w-full rounded-lg border border-line bg-black/30 px-2 text-sm text-ink" />
            </label>
            {lens && (
              <label className="col-span-2 text-xs text-ink-3">Event date {needsEvent ? "(needed: when the fire started)" : "(optional)"}
                <input type="date" value={eventDate} min={start} max={end} onChange={(e) => setEventDate(e.target.value)} className="mt-1 h-9 w-full rounded-lg border border-line bg-black/30 px-2 text-sm text-ink" />
              </label>
            )}
          </div>

          <div className="mt-4 flex items-center gap-2">
            <button type="button" onClick={() => { setDrawing(true); setBox(null); }}
              className="h-10 flex-1 cursor-pointer rounded-lg border border-line text-sm text-ink transition-colors duration-200 hover:bg-white/10">
              {drawing ? "Click two corners…" : box ? "Redraw the area" : "Draw an area"}
            </button>
          </div>
          {box && (
            <p className={`mt-2 text-sm ${km2 > limit ? "text-drop" : "text-ink-2"}`} aria-live="polite">
              {Math.round(km2).toLocaleString("en-GB")} km² of {limit.toLocaleString("en-GB")} km² allowed for {product}
              {km2 > limit ? ": draw a smaller area." : "."}
            </p>
          )}

          <button type="button" onClick={run}
            disabled={!box || km2 > limit || !lensOk || (needsEvent && !eventDate) || (!!job && (job.status === "queued" || job.status === "running"))}
            className="mt-3 h-11 w-full cursor-pointer rounded-lg bg-accent text-sm font-medium text-black transition-opacity duration-200 hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40">
            Run the Analysis
          </button>
          {job && job.status !== "done" && (
            <div className="mt-3 rounded-lg border border-line p-3 text-sm" role="status">
              <div className="busy-bar mb-2 h-0.5" aria-hidden />
              {job.status === "queued" ? `Waiting${job.place ? ` (place ${job.place})` : ""}…` : job.status === "error" ? <span className="text-drop">{job.message}</span> : job.message ?? "Working…"}
              {job.granules ? <span className="block text-xs text-ink-3">{job.granules} Granules · {job.area_km2} km²</span> : null}
            </div>
          )}
          {jobError && <p className="mt-2 text-sm text-drop" role="alert">{jobError}</p>}

          {recent.length > 0 && (
            <div className="mt-5">
              <h3 className="text-xs uppercase tracking-wide text-ink-3">Recent Analyses</h3>
              <ul className="mt-2 flex flex-col gap-1">
                {recent.map((r) => (
                  <li key={r.id}>
                    <Link href={r.status === "done" ? `/study/${r.id}` : "#"} aria-disabled={r.status !== "done"}
                      className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm transition-colors duration-200 hover:bg-white/10">
                      <span className={`h-1.5 w-1.5 rounded-full ${r.status === "done" ? "bg-emerald-400" : r.status === "error" ? "bg-drop" : "bg-accent"}`} aria-hidden />
                      <span className="truncate text-ink-2">{r.request?.name ?? `${r.request?.product}${r.request?.lens ? " / " + r.request.lens : ""}`}</span>
                      <span className="ml-auto shrink-0 text-xs text-ink-3">{r.area_km2 ? `${Math.round(r.area_km2)} km²` : r.status}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </motion.section>
      )}
    </main>
  );
}
