"use client";

import { Map as MlMap, Marker, NavigationControl, setWorkerUrl, type GeoJSONSource, type RasterTileSource } from "maplibre-gl";
import { useEffect, useRef, useState } from "react";
import { layerTileUrl, shortDate, type Bbox } from "@/lib/api";
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
};

const TILT = { pitch: 55, bearing: -12 };

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

function addOverlay(map: MlMap, url: string, opacity: number, bbox: Bbox) {
  map.addSource("study", { type: "raster", tiles: [url], tileSize: 256, bounds: bbox });
  map.addLayer({ id: "study", type: "raster", source: "study", paint: { "raster-opacity": opacity, "raster-fade-duration": 150, "raster-resampling": "nearest" } }, ANCHOR);
}

export default function StudyMap({ studyId, bbox, layerId, date, opacity, compareDate, probe, onPick, terrain }: Props) {
  const mainEl = useRef<HTMLDivElement>(null);
  const cmpEl = useRef<HTMLDivElement>(null);
  const main = useRef<MlMap | null>(null);
  const cmp = useRef<MlMap | null>(null);
  const marker = useRef<Marker | null>(null);
  const [ready, setReady] = useState(false);
  const [cmpReady, setCmpReady] = useState(false);
  const [split, setSplit] = useState(50);
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
      m.on("click", (e) => pickRef.current(e.lngLat.lng, e.lngLat.lat));
      m.getCanvas().style.cursor = "crosshair";
      m.fitBounds([[bbox[0], bbox[1]], [bbox[2], bbox[3]]], { padding: 40, duration: 0, ...TILT });
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
  }, [ready, studyId, layerId, date, bbox, opacity]);

  useEffect(() => {
    const m = main.current;
    if (m && ready && m.getLayer("study")) m.setPaintProperty("study", "raster-opacity", opacity);
    const c = cmp.current;
    if (c && cmpReady && c.getLayer("study")) c.setPaintProperty("study", "raster-opacity", opacity);
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
  }, [probe, ready]);

  useEffect(() => {
    const m = main.current;
    if (m && ready) (m.getSource("outline") as GeoJSONSource | undefined)?.setData(outline(bbox));
  }, [bbox, ready]);

  return (
    <div className="relative h-full w-full">
      <div ref={mainEl} className="h-full w-full" />
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
