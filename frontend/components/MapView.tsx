"use client";

import { Map as MlMap, Marker, NavigationControl, setWorkerUrl, type StyleSpecification } from "maplibre-gl";
import { useEffect, useRef, useState } from "react";
import { analysisTileUrl, bboxOf, changeUrl, tileUrl, type Pol, type Stack } from "@/lib/api";

const FADE = 700;

const BASEMAP_URL = "https://tiles.openfreemap.org/styles/dark";

const OWN_SOURCES: StyleSpecification["sources"] = {
  // NASA Blue Marble for the far-out globe view; the dark basemap takes over when zoomed in.
  globe: {
    type: "raster",
    tiles: ["https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg"],
    tileSize: 256,
    maxzoom: 8,
    attribution: "Blue Marble: NASA GIBS",
  },
  dem: {
    type: "raster-dem",
    tiles: ["https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"],
    tileSize: 256,
    maxzoom: 13,
    encoding: "terrarium",
    attribution: "Terrain: Mapzen, AWS Terrain Tiles",
  },
  footprints: { type: "geojson", data: { type: "FeatureCollection", features: [] } },
};

type Layer = StyleSpecification["layers"][number];

const OWN_LAYERS: Layer[] = [
  {
    id: "globe",
    type: "raster",
    source: "globe",
    paint: {
      "raster-opacity": ["interpolate", ["linear"], ["zoom"], 0, 1, 5, 1, 7.5, 0],
      "raster-saturation": -0.2,
      "raster-brightness-max": 0.85,
    },
  },
  // Radar layers are inserted below this anchor, the change overlay above it.
  { id: "change-anchor", type: "background", paint: { "background-opacity": 0 } },
  {
    id: "footprints",
    type: "line",
    source: "footprints",
    paint: {
      "line-color": ["case", ["get", "selected"], "#2dd4bf", "#ffffff"],
      "line-opacity": ["case", ["get", "selected"], 0.9, 0.22],
      "line-width": ["case", ["get", "selected"], 1.6, 1],
    },
  },
];

/** Place names sit on bright radar imagery, so give them light text with a dark outline. */
function legible(l: Layer): Layer {
  if (l.type !== "symbol") return l;
  // Thin out small places so the radar stays readable.
  const minzoom = l.id === "place_village" ? 10.5 : l.id === "place_other" || l.id === "place_suburb" ? 12 : l.minzoom;
  if (minzoom !== undefined) l = { ...l, minzoom };
  return { ...l, paint: { ...l.paint, "text-color": "#f1f5f9", "text-halo-color": "rgba(5, 7, 10, 0.92)", "text-halo-width": 1.6, "text-halo-blur": 0.4 } };
}

/** Dark vector basemap with our layers slotted between its ground layers and its labels. */
async function buildStyle(): Promise<StyleSpecification> {
  let base: StyleSpecification | null = null;
  try {
    const r = await fetch(BASEMAP_URL);
    if (r.ok) base = await r.json();
  } catch {
    // Offline or blocked: fall back to the globe imagery alone.
  }
  const layers = base?.layers ?? [{ id: "bg", type: "background", paint: { "background-color": "#04111a" } } as Layer];
  const onTop = (l: Layer) => (l.type === "symbol" && !/^road_|^highway_name/.test(l.id)) || l.id.startsWith("boundary_");
  const drop = (l: Layer) => l.type === "symbol" && /^road_|^highway_name/.test(l.id);
  return {
    version: 8,
    projection: { type: "globe" },
    glyphs: base?.glyphs,
    sprite: base?.sprite,
    sources: { ...(base?.sources ?? {}), ...OWN_SOURCES },
    layers: [...layers.filter((l) => !onTop(l) && !drop(l)), ...OWN_LAYERS, ...layers.filter(onTop).map(legible)],
  };
}

export type Focus = { center: [number, number]; zoom: number; pitch: number; bearing: number };

export type View = { bbox: [number, number, number, number]; center: [number, number]; zoom: number };

type Props = {
  phase: "intro" | "explore";
  focus: Focus;
  stacks: Stack[];
  stack: Stack | null;
  currentIdx: number;
  baselineIdx: number;
  pol: Pol;
  showChange: boolean;
  terrain: boolean;
  preload: boolean;
  probe: { lon: number; lat: number } | null;
  reducedMotion: boolean;
  onClick: (lon: number, lat: number) => void;
  /** Analysis result to draw over the radar, if any. */
  analysis: { id: string; layer: "class" | "when"; bbox: number[] } | null;
  /** Fly here when the key changes. */
  goTo: { lon: number; lat: number; zoom: number; key: number } | null;
  /** The area at the centre of the screen, as if looking straight down. */
  onView: (view: View) => void;
  /** Reported a few times a second: are tiles still loading, and how many passes are fully loaded. */
  onProgress: (busy: boolean, passesReady: number) => void;
};

function whenSourceReady(map: MlMap, sourceId: string, cb: () => void, timeout: number) {
  let done = false;
  const finish = () => {
    if (done) return;
    done = true;
    map.off("sourcedata", check);
    clearTimeout(timer);
    cb();
  };
  const check = () => {
    if (map.getSource(sourceId) && map.isSourceLoaded(sourceId)) finish();
  };
  const timer = setTimeout(finish, timeout);
  map.on("sourcedata", check);
  setTimeout(check, 80);
}

export default function MapView(props: Props) {
  const { phase, focus, stacks, stack, currentIdx, baselineIdx, pol, showChange, terrain, preload, probe, reducedMotion } = props;
  const el = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MlMap | null>(null);
  const [loaded, setLoaded] = useState(false);
  const built = useRef(0); // number of radar layers currently on the map
  const [builtKey, setBuiltKey] = useState("");
  const shown = useRef(-1);
  // Latest props for map event handlers, which are registered once.
  const latest = useRef(props);
  useEffect(() => {
    latest.current = props;
  });

  // Create the map once.
  useEffect(() => {
    if (!el.current) return;
    setWorkerUrl("/maplibre-gl-worker.mjs"); // copied into public/ by scripts/copy-map-worker.mjs
    let map: MlMap | null = null;
    let cancelled = false;
    buildStyle().then((style) => {
      if (cancelled || !el.current) return;
      const m = new MlMap({
        container: el.current,
        style,
        center: [6, 24],
        zoom: 1.5,
        maxPitch: 75,
        attributionControl: { compact: true },
      });
      map = m;
      mapRef.current = m;
      m.addControl(new NavigationControl({ visualizePitch: true }), "top-right");
      m.on("load", () => {
        try {
          m.setSky({
            "sky-color": "#0a1322",
            "horizon-color": "#16263d",
            "fog-color": "#04111a",
            "atmosphere-blend": ["interpolate", ["linear"], ["zoom"], 0, 1, 5, 0.8, 8, 0],
          });
        } catch {
          // Sky is decoration; engines without it still work.
        }
        setLoaded(true);
      });
      const report = () => {
        const c = m.getCenter();
        const box = m.getContainer();
        // Degrees per screen pixel at this zoom; a pitched camera sees far beyond this, which is too much to analyse.
        const dpp = 360 / (512 * 2 ** m.getZoom());
        const dx = (box.clientWidth / 2) * dpp;
        const dy = (box.clientHeight / 2) * dpp * Math.cos((c.lat * Math.PI) / 180);
        latest.current.onView({ bbox: [c.lng - dx, c.lat - dy, c.lng + dx, c.lat + dy], center: [c.lng, c.lat], zoom: m.getZoom() });
      };
      m.on("moveend", report);
      m.on("load", report);
      m.on("click", (e) => {
        if (latest.current.phase === "explore") latest.current.onClick(e.lngLat.lng, e.lngLat.lat);
      });
    });
    return () => {
      cancelled = true;
      mapRef.current = null;
      map?.remove();
      setLoaded(false);
    };
  }, []);

  // Loading state. Polled, because the pulsing overlay keeps the map from ever reporting "idle".
  useEffect(() => {
    if (!loaded) return;
    const t = setInterval(() => {
      const map = mapRef.current;
      if (!map) return;
      let ready = 0;
      for (let i = 0; i < built.current; i++) {
        const id = `radar-${i}`;
        if (map.getLayer(id) && map.getLayoutProperty(id, "visibility") !== "none" && map.isSourceLoaded(id)) ready++;
      }
      latest.current.onProgress(!map.areTilesLoaded(), ready);
    }, 300);
    return () => clearInterval(t);
  }, [loaded]);

  // Intro: slow spin. Explore: fly to the story area.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded) return;
    if (phase === "intro") {
      // Push the globe to the right of the title on wide screens.
      const wide = map.getContainer().clientWidth >= 900;
      map.jumpTo({ zoom: wide ? 2.1 : 1.3, padding: { left: wide ? map.getContainer().clientWidth * 0.42 : 0, top: 0, right: 0, bottom: wide ? 0 : map.getContainer().clientHeight * 0.3 } });
      if (reducedMotion) return;
      let raf = 0;
      let last = performance.now();
      const spin = (now: number) => {
        const c = map.getCenter();
        map.setCenter([c.lng + ((now - last) / 1000) * 3, c.lat]);
        last = now;
        raf = requestAnimationFrame(spin);
      };
      raf = requestAnimationFrame(spin);
      return () => cancelAnimationFrame(raf);
    }
    const view = { ...focus, padding: { left: 0, top: 0, right: 0, bottom: 0 } };
    if (reducedMotion) map.jumpTo(view);
    else map.flyTo({ ...view, duration: 6500, curve: 1.5, essential: true });
  }, [phase, loaded, focus, reducedMotion]);

  // 3D terrain.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded) return;
    map.setTerrain(terrain && phase === "explore" ? { source: "dem", exaggeration: 1.6 } : null);
  }, [terrain, phase, loaded]);

  // Track outlines.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded) return;
    const src = map.getSource("footprints") as { setData?: (d: unknown) => void } | undefined;
    src?.setData?.({
      type: "FeatureCollection",
      features: stacks.map((s) => ({
        type: "Feature",
        properties: { selected: s === stack },
        geometry: { type: "LineString", coordinates: s.footprint },
      })),
    });
  }, [stacks, stack, loaded]);

  // One raster layer per pass of the chosen track.
  const stackKey = stack ? `${stack.stack}|${stack.bandwidth_mhz}|${pol}` : "";
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded) return;
    for (let i = 0; i < built.current; i++) {
      if (map.getLayer(`radar-${i}`)) map.removeLayer(`radar-${i}`);
      if (map.getSource(`radar-${i}`)) map.removeSource(`radar-${i}`);
    }
    built.current = 0;
    shown.current = -1;
    const s = latest.current.stack;
    if (!s) {
      setBuiltKey("");
      return;
    }
    const cur = latest.current.currentIdx;
    const bounds = bboxOf(s.footprint);
    s.passes.forEach((p, i) => {
      map.addSource(`radar-${i}`, {
        type: "raster",
        tiles: [tileUrl(p.id, latest.current.pol)],
        tileSize: 256,
        minzoom: 5,
        maxzoom: 14,
        bounds,
        attribution: "NISAR: NASA / ISRO, via ASF DAAC",
      });
      map.addLayer(
        {
          id: `radar-${i}`,
          type: "raster",
          source: `radar-${i}`,
          layout: { visibility: i === cur || latest.current.preload ? "visible" : "none" },
          paint: {
            "raster-opacity": i === cur ? 1 : 0,
            "raster-opacity-transition": { duration: latest.current.reducedMotion ? 0 : FADE, delay: 0 },
            "raster-fade-duration": 0,
          },
        },
        "change-anchor",
      );
    });
    built.current = s.passes.length;
    shown.current = cur;
    setBuiltKey(stackKey);
  }, [stackKey, loaded]);

  // Cross-fade when the current pass changes.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !builtKey || builtKey !== stackKey) return;
    const next = currentIdx;
    const prev = shown.current;
    if (next === prev || !map.getLayer(`radar-${next}`)) return;
    shown.current = next;
    map.setLayoutProperty(`radar-${next}`, "visibility", "visible");
    const settle = () => {
      if (shown.current !== next) return;
      for (let i = 0; i < built.current; i++) {
        if (i === next || !map.getLayer(`radar-${i}`)) continue;
        map.setPaintProperty(`radar-${i}`, "raster-opacity", 0);
        if (!latest.current.preload) setTimeout(() => shown.current === next && map.getLayer(`radar-${i}`) && map.setLayoutProperty(`radar-${i}`, "visibility", "none"), FADE + 60);
      }
    };
    whenSourceReady(
      map,
      `radar-${next}`,
      () => {
        if (shown.current !== next || !map.getLayer(`radar-${next}`)) return;
        map.setPaintProperty(`radar-${next}`, "raster-opacity", 1);
        // A later pass sits above an earlier one, so it can fade in on top first.
        setTimeout(settle, next > prev ? FADE : 0);
      },
      20000,
    );
  }, [currentIdx, builtKey, stackKey]);

  // While playing, keep every pass loaded so frames do not stall.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !builtKey) return;
    for (let i = 0; i < built.current; i++) {
      if (!map.getLayer(`radar-${i}`)) continue;
      map.setLayoutProperty(`radar-${i}`, "visibility", preload || i === shown.current ? "visible" : "none");
    }
  }, [preload, builtKey]);

  // Change overlay between the "before" pass and the current one.
  // Always earlier pass -> later pass, so red means "weaker at the later date" whichever one is selected.
  const beforeId = stack?.passes[Math.min(baselineIdx, currentIdx)]?.id;
  const afterId = stack?.passes[Math.max(baselineIdx, currentIdx)]?.id;
  const changePol = pol === "HH" ? "HH" : "HV";
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded) return;
    if (map.getLayer("change")) map.removeLayer("change");
    if (map.getSource("change")) map.removeSource("change");
    if (!showChange || !stack || !beforeId || !afterId || beforeId === afterId) return;
    map.addSource("change", {
      type: "raster",
      tiles: [changeUrl(beforeId, afterId, changePol)],
      tileSize: 256,
      minzoom: 5,
      maxzoom: 14,
      bounds: bboxOf(stack.footprint),
    });
    map.addLayer({ id: "change", type: "raster", source: "change", paint: { "raster-opacity": 0.95, "raster-fade-duration": 250 } }, "footprints");
    if (reducedMotion) return;
    let raf = 0;
    const t0 = performance.now();
    const pulse = (now: number) => {
      if (map.getLayer("change")) map.setPaintProperty("change", "raster-opacity", 0.8 + 0.2 * Math.sin((now - t0) / 520));
      raf = requestAnimationFrame(pulse);
    };
    raf = requestAnimationFrame(pulse);
    return () => cancelAnimationFrame(raf);
  }, [showChange, beforeId, afterId, changePol, stack, loaded, reducedMotion]);

  // Analysis overlay.
  const analysisKey = props.analysis ? `${props.analysis.id}|${props.analysis.layer}` : "";
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded) return;
    if (map.getLayer("analysis")) map.removeLayer("analysis");
    if (map.getSource("analysis")) map.removeSource("analysis");
    const a = latest.current.analysis;
    if (!analysisKey || !a) return;
    map.addSource("analysis", { type: "raster", tiles: [analysisTileUrl(a.id, a.layer)], tileSize: 256, minzoom: 5, maxzoom: 14, bounds: a.bbox as [number, number, number, number] });
    map.addLayer({ id: "analysis", type: "raster", source: "analysis", paint: { "raster-opacity": 0.92, "raster-resampling": "nearest", "raster-fade-duration": 200 } }, "footprints");
  }, [analysisKey, loaded]);

  // Camera moves requested by the assistant.
  const goKey = props.goTo?.key;
  useEffect(() => {
    const map = mapRef.current;
    const g = latest.current.goTo;
    if (!map || !loaded || !g) return;
    const view = { center: [g.lon, g.lat] as [number, number], zoom: g.zoom, pitch: 45 };
    if (latest.current.reducedMotion) map.jumpTo(view);
    else map.flyTo({ ...view, duration: 3500, essential: true });
  }, [goKey, loaded]);

  // Marker at the inspected point.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !probe) return;
    const node = document.createElement("div");
    node.className = "probe";
    const marker = new Marker({ element: node }).setLngLat([probe.lon, probe.lat]).addTo(map);
    return () => {
      marker.remove();
    };
  }, [probe, loaded]);

  // MapLibre forces position:relative on its container, so size it inside an absolutely placed wrapper.
  return (
    <div className="absolute inset-0">
      <div ref={el} className="h-full w-full" role="application" aria-label="Radar map" />
    </div>
  );
}
