import type { StyleSpecification } from "maplibre-gl";

const BASEMAP_URL = "https://tiles.openfreemap.org/styles/dark";

type Layer = StyleSpecification["layers"][number];

/** Our layers are inserted below this anchor so place names stay on top. */
export const ANCHOR = "overlay-anchor";

/** Place names sit on bright radar imagery, so give them light text with a dark outline. */
function legible(l: Layer): Layer {
  if (l.type !== "symbol") return l;
  return { ...l, paint: { ...l.paint, "text-color": "#f1f5f9", "text-halo-color": "rgba(5, 7, 10, 0.92)", "text-halo-width": 1.6 } };
}

/** Elevation for 3D terrain and hillshade (Mapzen Terrarium tiles on AWS open data). */
export const DEM_SOURCE = "dem";

/** NASA Blue Marble when zoomed out, a dark vector basemap when zoomed in, labels above our overlays.
 *  With terrain, the map gets an elevation source and hillshade, so it can tilt into 3D. */
export async function buildStyle(projection: "globe" | "mercator", terrain = false): Promise<StyleSpecification> {
  let base: StyleSpecification | null = null;
  try {
    const r = await fetch(BASEMAP_URL);
    if (r.ok) base = await r.json();
  } catch {
    // Offline: Blue Marble alone.
  }
  const layers = base?.layers ?? [{ id: "bg", type: "background", paint: { "background-color": "#04111a" } } as Layer];
  const onTop = (l: Layer) => (l.type === "symbol" && !/^road_|^highway_name/.test(l.id)) || l.id.startsWith("boundary_");
  const drop = (l: Layer) => l.type === "symbol" && /^road_|^highway_name/.test(l.id);
  return {
    version: 8,
    projection: { type: projection },
    glyphs: base?.glyphs,
    sprite: base?.sprite,
    sources: {
      ...(base?.sources ?? {}),
      bluemarble: {
        type: "raster",
        tiles: ["https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg"],
        tileSize: 256,
        maxzoom: 8,
        attribution: "Blue Marble: NASA GIBS",
      },
      ...(terrain
        ? {
            [DEM_SOURCE]: {
              type: "raster-dem" as const,
              tiles: ["https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"],
              tileSize: 256,
              maxzoom: 13,
              encoding: "terrarium" as const,
              attribution: "Terrain: Mapzen, AWS Terrain Tiles",
            },
            hillshadeSrc: {
              type: "raster-dem" as const,
              tiles: ["https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"],
              tileSize: 256,
              maxzoom: 13,
              encoding: "terrarium" as const,
            },
          }
        : {}),
    },
    layers: [
      ...layers.filter((l) => !onTop(l) && !drop(l)),
      {
        id: "bluemarble",
        type: "raster",
        source: "bluemarble",
        paint: { "raster-opacity": ["interpolate", ["linear"], ["zoom"], 0, 1, 5, 1, 7.5, 0], "raster-saturation": -0.2, "raster-brightness-max": 0.85 },
      },
      ...(terrain
        ? [{
            id: "hillshade",
            type: "hillshade" as const,
            source: "hillshadeSrc",
            minzoom: 3,
            paint: { "hillshade-exaggeration": 0.45, "hillshade-shadow-color": "#000000", "hillshade-highlight-color": "#9aa7b8", "hillshade-accent-color": "#1f2937" },
          } as Layer]
        : []),
      { id: ANCHOR, type: "background", paint: { "background-opacity": 0 } },
      ...layers.filter(onTop).map(legible),
    ],
  };
}
