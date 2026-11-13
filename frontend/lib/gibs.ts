import type { Bbox } from "./api";

/** NASA GIBS (Global Imagery Browse Services) pictures for context: no key, any date, any box. */
const WMS = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi";

function getMap(layer: string, [w, s, e, n]: Bbox, width: number, time?: string, format = "image/jpeg") {
  const height = Math.max(64, Math.round((width * (n - s)) / (e - w)));
  const q = new URLSearchParams({ SERVICE: "WMS", REQUEST: "GetMap", VERSION: "1.3.0", LAYERS: layer, STYLES: "", FORMAT: format, CRS: "EPSG:4326", BBOX: [s, w, n, e].join(","), WIDTH: String(width), HEIGHT: String(height) });
  if (time) q.set("TIME", time);
  return `${WMS}?${q.toString()}`;
}

/** MODIS Terra true colour on one day: what an optical satellite saw (clouds and smoke included). */
export const modisTrueColor = (bbox: Bbox, date: string, width = 900) => getMap("MODIS_Terra_CorrectedReflectance_TrueColor", bbox, width, date);

/** Blue Marble around a site, for the locator map. */
export function locator(bbox: Bbox, pad = 20, width = 520): { url: string; box: Bbox } {
  const cx = (bbox[0] + bbox[2]) / 2;
  const cy = (bbox[1] + bbox[3]) / 2;
  const box: Bbox = [Math.max(-180, cx - pad * 1.6), Math.max(-90, cy - pad), Math.min(180, cx + pad * 1.6), Math.min(90, cy + pad)];
  return { url: getMap("BlueMarble_ShadedRelief_Bathymetry", box, width), box };
}

export const addDays = (iso: string, days: number) => new Date(Date.parse(iso + "T00:00:00Z") + days * 86400000).toISOString().slice(0, 10);
