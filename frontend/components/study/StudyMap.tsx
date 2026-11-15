"use client";

import { Map as MlMap, Marker, NavigationControl, Popup, setWorkerUrl, type FilterSpecification, type GeoJSONSource, type MapGeoJSONFeature, type RasterTileSource } from "maplibre-gl";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { layerTileUrl, shortDate, type AnswerFeatures, type Bbox } from "@/lib/api";
import { ANCHOR, DEM_SOURCE, buildStyle } from "@/lib/basemap";

type Props = {
  studyId: string;
  bbox: Bbox;
  layerId: string;
  date: string;
  opacity: number;
  /** Before/after swipe: the date shown on the left of the handle. */
  compareDate: string | null;
  probe: { lon: number; lat: number } | null;
  onPick: (lon: number, lat: number) => void;
  /** Drape the layer over real terrain and tilt the camera. */
  terrain: boolean;
  /** A Question's ranked items, drawn as styled lines or labelled points over the raster. */
  features?: AnswerFeatures | null;
  /** Hide the raster while vector features tell the story (e.g. road sections). */
  hideRaster?: boolean;
  /** Fly the camera here when `key` changes (search results, list rows). */
  focus?: { lon: number; lat: number; zoom: number; key: number } | null;
  /** Content of the answer bubble anchored at the clicked spot. */
  popup?: ReactNode;
};

// A gentle tilt: terrain still reads in 3D, but the study area fills the view and answers stay legible.
const TILT = { pitch: 38, bearing: -8 };
const FEATURE_LAYERS = ["answers-casing", "answers-line", "answers-halo", "answers-pt", "answers-label"];

function textFont(m: MlMap): string[] {
  for (const l of m.getStyle().layers ?? []) {
    const f = l.type === "symbol" ? (l.layout as Record<string, unknown> | undefined)?.["text-font"] : undefined;
    if (Array.isArray(f)) return f as string[];
  }
  return ["Noto Sans Regular"];
}

function addFeatureLayers(m: MlMap) {
  m.addSource("answers", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
  const isLine: FilterSpecification = ["==", ["geometry-type"], "LineString"];
  const isPoint: FilterSpecification = ["==", ["geometry-type"], "Point"];
  m.addLayer({ id: "answers-casing", type: "line", source: "answers", filter: isLine, layout: { "line-cap": "round", "line-join": "round" },
    paint: { "line-color": "#04111a", "line-opacity": 0.85, "line-width": ["interpolate", ["linear"], ["zoom"], 9, 4, 14, 10] } });
  m.addLayer({ id: "answers-line", type: "line", source: "answers", filter: isLine, layout: { "line-cap": "round", "line-join": "round", "line-sort-key": ["get", "class"] },
    paint: { "line-color": ["get", "color"], "line-width": ["interpolate", ["linear"], ["zoom"], 9, 2.2, 14, 6] } });
  m.addLayer({ id: "answers-halo", type: "circle", source: "answers", filter: isPoint,
    paint: { "circle-color": ["get", "color"], "circle-opacity": 0.22, "circle-radius": ["interpolate", ["linear"], ["zoom"], 9, 9, 14, 20] } });
  m.addLayer({ id: "answers-pt", type: "circle", source: "answers", filter: isPoint,
    paint: { "circle-color": ["get", "color"], "circle-stroke-color": "#ffffff", "circle-stroke-width": 1.5, "circle-radius": ["interpolate", ["linear"], ["zoom"], 9, 4.5, 14, 9] } });
  m.addLayer({ id: "answers-label", type: "symbol", source: "answers", filter: ["all", isPoint, ["<=", ["get", "rank"], 30]],
    layout: { "text-field": ["get", "label"], "text-font": textFont(m), "text-size": 12, "text-offset": [0, 1.3], "text-anchor": "top", "text-optional": true },
    paint: { "text-color": "#ffffff", "text-halo-color": "#04111a", "text-halo-width": 1.6 } });
}

function outline([w, s, e, n]: Bbox) {
  return { type: "Feature" as const, properties: {}, geometry: { type: "LineString" as const, coordinates: [[w, s], [e, s], [e, n], [w, n], [w, s]] } };
}

async function makeMap(el: HTMLElement, bbox: Bbox, interactive: boolean) {
  const style = await buildStyle("mercator", true);
  const map = new MlMap({
    container: el,
    style,
    bounds: [[bbox[0], bbox[1]], [bbox[2], bbox[3]]],
    fitBoundsOptions: { padding: 40 },
    interactive,
    attributionControl: interactive ? { compact: true } : false,
    fadeDuration: 0,
  });
  await new Promise<void>((r) => map.once("load", () => r()));
  map.setTerrain({ source: DEM_SOURCE, exaggeration: 1.6 });
  return map;
}

/** Fade the layer as you zoom in, so streets and place names show through at plot scale. */
const zoomOpacity = (o: number) => ["interpolate", ["linear"], ["zoom"], 11, o, 13, o * 0.8, 16, o * 0.5] as unknown as number;

function addOverlay(map: MlMap, url: string, opacity: number, bbox: Bbox) {
  map.addSource("study", { type: "raster", tiles: [url], tileSize: 256, bounds: bbox });
  map.addLayer({ id: "study", type: "raster", source: "study", paint: { "raster-opacity": zoomOpacity(opacity), "raster-fade-duration": 150, "raster-resampling": "nearest" } }, ANCHOR);
}

export default function StudyMap({ studyId, bbox, layerId, date, opacity, compareDate, probe, onPick, terrain, features, hideRaster, focus, popup }: Props) {
  const mainEl = useRef<HTMLDivElement>(null);
  const cmpEl = useRef<HTMLDivElement>(null);
  const main = useRef<MlMap | null>(null);
  const cmp = useRef<MlMap | null>(null);
  const marker = useRef<Marker | null>(null);
  const [ready, setReady] = useState(false);
  const [cmpReady, setCmpReady] = useState(false);
  const [split, setSplit] = useState(50);
  const [drawnKey, setDrawnKey] = useState<string | null>(null); // which layer/date has finished drawing
  const bubble = useRef<Popup | null>(null);
  const [bubbleEl, setBubbleEl] = useState<HTMLDivElement | null>(null);
  const pickRef = useRef(onPick);
  useEffect(() => {
    pickRef.current = onPick;
  });

  useEffect(() => {
    setWorkerUrl("/maplibre-gl-worker.mjs");
    let alive = true;
    let map: MlMap | null = null;
    makeMap(mainEl.current!, bbox, true).then((m) => {
      if (!alive) return m.remove();
      map = m;
      main.current = m;
      m.addControl(new NavigationControl({ visualizePitch: false }), "bottom-right");
      m.addSource("outline", { type: "geojson", data: outline(bbox) });
      m.addLayer({ id: "outline", type: "line", source: "outline", paint: { "line-color": "#ffffff", "line-opacity": 0.5, "line-width": 1.2, "line-dasharray": [3, 2] } });
      addFeatureLayers(m);
      // A click on a drawn road, line or village snaps to that item; anywhere else answers that spot.
      m.on("click", (e) => {
        const r = 10; // finger-sized tolerance around the tap
        const box: [[number, number], [number, number]] = [[e.point.x - r, e.point.y - r], [e.point.x + r, e.point.y + r]];
        const hit = m.queryRenderedFeatures(box, { layers: ["answers-pt", "answers-line"] })[0] as MapGeoJSONFeature | undefined;
        const p = hit?.properties as { lon?: number; lat?: number } | undefined;
        if (hit && hit.geometry.type === "Point" && p?.lon !== undefined && p?.lat !== undefined) pickRef.current(p.lon, p.lat);
        else pickRef.current(e.lngLat.lng, e.lngLat.lat);
      });
      const tip = new Popup({ closeButton: false, closeOnClick: false, offset: 10, className: "map-tip", maxWidth: "260px" });
      for (const id of ["answers-line", "answers-pt"]) {
        m.on("mousemove", id, (e) => {
          const f = e.features?.[0];
          if (!f) return;
          m.getCanvas().style.cursor = "pointer";
          const pr = f.properties as Record<string, string | number>;
          const el = document.createElement("div");
          const b = document.createElement("strong");
          b.textContent = String(pr.name ?? "");
          const sm = document.createElement("div");
          sm.textContent = String(pr.class_label ?? "");
          el.append(b, sm);
          tip.setLngLat(e.lngLat).setDOMContent(el).addTo(m);
        });
        m.on("mouseleave", id, () => {
          m.getCanvas().style.cursor = "crosshair";
          tip.remove();
        });
      }
      m.getCanvas().style.cursor = "crosshair";
      m.fitBounds([[bbox[0], bbox[1]], [bbox[2], bbox[3]]], { padding: 30, duration: 0, ...TILT });
      setReady(true);
    });
    return () => {
      alive = false;
      map?.remove();
      main.current = null;
      setReady(false);
    };
    // The bbox of a study never changes while the page is open.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [studyId]);

  // Layer, date and opacity.
  useEffect(() => {
    const m = main.current;
    if (!m || !ready) return;
    const url = layerTileUrl(studyId, layerId, date);
    const src = m.getSource("study") as RasterTileSource | undefined;
    if (!src) addOverlay(m, url, opacity, bbox);
    else src.setTiles([url]);
    const key = url;
    m.once("idle", () => setDrawnKey(key)); // the map is idle once these tiles have drawn
  }, [ready, studyId, layerId, date, bbox, opacity]);
  const drawing = !ready || drawnKey !== layerTileUrl(studyId, layerId, date);

  // Vector answers (lines and points) and whether the raster stays visible under them.
  useEffect(() => {
    const m = main.current;
    if (!m || !ready) return;
    const empty: AnswerFeatures = { type: "FeatureCollection", features: [] };
    (m.getSource("answers") as GeoJSONSource | undefined)?.setData((features ?? empty) as Parameters<GeoJSONSource["setData"]>[0]);
    for (const id of FEATURE_LAYERS) if (m.getLayer(id)) m.moveLayer(id); // keep them above the raster when it is re-added
  }, [features, ready, layerId]);

  useEffect(() => {
    const m = main.current;
    if (m && ready && m.getLayer("study")) m.setLayoutProperty("study", "visibility", hideRaster ? "none" : "visible");
  }, [hideRaster, ready, layerId]);

  useEffect(() => {
    const m = main.current;
    if (!m || !ready || !focus) return;
    m.flyTo({ center: [focus.lon, focus.lat], zoom: Math.max(m.getZoom(), focus.zoom), duration: 1200, essential: true });
  }, [focus?.key, ready]); // eslint-disable-line react-hooks/exhaustive-deps

  // The answer bubble at the clicked spot; its React content is rendered into the popup's element.
  useEffect(() => {
    const m = main.current;
    if (!m || !ready || !probe || !popup) {
      bubble.current?.remove();
      return;
    }
    if (!bubble.current) {
      const el = document.createElement("div");
      bubble.current = new Popup({ closeButton: false, closeOnClick: false, offset: 16, className: "answer-bubble", maxWidth: "300px", focusAfterOpen: false });
      bubble.current.setDOMContent(el);
      setBubbleEl(el);
    }
    bubble.current.setLngLat([probe.lon, probe.lat]).addTo(m);
  }, [probe, ready, popup]);

  // A spot high on the map would put its bubble under the search box and legend: pan it down a little.
  useEffect(() => {
    const m = main.current;
    if (!m || !ready || !probe) return;
    const pt = m.project([probe.lon, probe.lat]);
    const h = m.getContainer().clientHeight;
    if (pt.y < h * 0.58 && pt.y > 0) m.panBy([0, pt.y - h * 0.68], { duration: 500 });
  }, [probe, ready]);

  useEffect(() => {
    const m = main.current;
    if (m && ready && m.getLayer("study")) m.setPaintProperty("study", "raster-opacity", zoomOpacity(opacity));
    const c = cmp.current;
    if (c && cmpReady && c.getLayer("study")) c.setPaintProperty("study", "raster-opacity", zoomOpacity(opacity));
  }, [opacity, ready, cmpReady]);

  // The comparison map for the swipe, kept on the same camera.
  useEffect(() => {
    if (!compareDate || !ready) return;
    let alive = true;
    let c: MlMap | null = null;
    const sync = () => {
      const m = main.current;
      if (m && c) c.jumpTo({ center: m.getCenter(), zoom: m.getZoom(), bearing: m.getBearing(), pitch: m.getPitch() });
    };
    makeMap(cmpEl.current!, bbox, false).then((m) => {
      if (!alive) return m.remove();
      c = m;
      cmp.current = m;
      sync();
      main.current?.on("move", sync);
      setCmpReady(true);
    });
    return () => {
      alive = false;
      main.current?.off("move", sync);
      c?.remove();
      cmp.current = null;
      setCmpReady(false);
    };
  }, [compareDate !== null, ready, bbox]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const c = cmp.current;
    if (!c || !cmpReady || !compareDate) return;
    const url = layerTileUrl(studyId, layerId, compareDate);
    const src = c.getSource("study") as RasterTileSource | undefined;
    if (!src) addOverlay(c, url, opacity, bbox);
    else src.setTiles([url]);
  }, [cmpReady, studyId, layerId, compareDate, bbox, opacity]);

  // 3D terrain on or off; the comparison map follows.
  useEffect(() => {
    const m = main.current;
    if (!m || !ready) return;
    const t = terrain ? { source: DEM_SOURCE, exaggeration: 1.6 } : null;
    m.setTerrain(t);
    cmp.current?.setTerrain(t);
    m.easeTo({ ...(terrain ? TILT : { pitch: 0, bearing: 0 }), duration: 800 });
  }, [terrain, ready, cmpReady]);

  // Clicked point.
  useEffect(() => {
    const m = main.current;
    if (!m || !ready) return;
    if (!probe) {
      marker.current?.remove();
      marker.current = null;
      return;
    }
    if (!marker.current) {
      const el = document.createElement("div");
      el.className = "probe";
      marker.current = new Marker({ element: el });
    }
    marker.current.setLngLat([probe.lon, probe.lat]).addTo(m);
    // A spot picked from a list (not the map) may be off screen: bring it into view.
    if (!m.getBounds().contains([probe.lon, probe.lat])) m.easeTo({ center: [probe.lon, probe.lat], zoom: Math.max(m.getZoom(), 13), duration: 900 });
  }, [probe, ready]);

  useEffect(() => {
    const m = main.current;
    if (m && ready) (m.getSource("outline") as GeoJSONSource | undefined)?.setData(outline(bbox));
  }, [bbox, ready]);

  return (
    <div className="relative h-full w-full">
      <div ref={mainEl} className="h-full w-full" />
      {drawing && (
        <div className="pointer-events-none absolute left-1/2 top-1/2 z-10 -translate-x-1/2 -translate-y-1/2 rounded-xl border border-line bg-bg/85 px-4 py-3 text-center backdrop-blur" role="status">
          <div className="busy-bar h-0.5 w-40" />
          <p className="mt-2 text-xs text-ink-2">Drawing the answer map…</p>
        </div>
      )}
      {bubbleEl && popup && createPortal(popup, bubbleEl)}
      {compareDate && (
        <>
          <div ref={cmpEl} className="pointer-events-none" style={{ position: "absolute", inset: 0, clipPath: `inset(0 ${100 - split}% 0 0)` }} aria-hidden />
          <div className="pointer-events-none absolute inset-y-0 w-0.5 bg-white/80" style={{ left: `${split}%` }} aria-hidden />
          <span className="panel pointer-events-none absolute top-3 px-2 py-1 text-xs" style={{ left: `calc(${split}% - 8px)`, transform: "translateX(-100%)" }}>{shortDate(compareDate)}</span>
          <span className="panel pointer-events-none absolute top-3 px-2 py-1 text-xs" style={{ left: `calc(${split}% + 8px)` }}>{shortDate(date)}</span>
          <input
            type="range"
            min={5}
            max={95}
            value={split}
            onChange={(e) => setSplit(Number(e.target.value))}
            aria-label="Move the before/after divider"
            className="swipe-range absolute inset-x-0 top-1/2 z-10 w-full -translate-y-1/2"
          />
        </>
      )}
    </div>
  );
}
