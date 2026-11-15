"use client";

import { useEffect, useMemo, useState } from "react";
import { ChangeBars, MultiLineChart, PassTimeline } from "@/components/charts/Charts";
import {
  agreementPngUrl,
  fetchAgreement,
  fetchAreaSeries,
  fetchChangeByDate,
  fetchClassArea,
  fetchSeriesByClass,
  longDate,
  splitLayer,
  type Agreement,
  type ChangeByDate,
  type ClassArea,
  type GeoPolygon,
  type Manifest,
  type SeriesByClass,
  type Timeseries,
} from "@/lib/api";
import { ha } from "@/lib/style";

const VAR_LABEL: Record<string, string> = { hv_db: "Vegetation scattering (HV)", hh_db: "Surface scattering (HH)", cum_disp_cm: "Ground motion since the first Pass (line of sight)" };
const NEUTRAL = "var(--ink-3)";

const READ: Record<string, string> = {
  hv_db: "HV comes from radar bouncing around inside vegetation. A lasting drop inside a class (for example after a fire or a harvest) that the other classes do not show is the signal; changes shared by all classes are weather or season.",
  hh_db: "HH is strongest from rough or wet ground and buildings. Rain and soil moisture move all classes together; a jump in one class only points at a surface change there.",
  cum_disp_cm: "Line-of-sight motion accumulated since the first Pass (positive: toward the satellite). A step at the event that differs between classes is motion caused by the event; slow common drifts are the reference choice and atmosphere.",
};

const WET = ["Open water", "Flooded vegetation"];

/** Class areas through time as chart lines in km², plus "All water" when a Model maps both kinds of water. */
function areaLines(r: ClassArea) {
  const km2 = (row: ClassArea["rows"][number], vs: number[]) => vs.reduce((t, v) => t + (row.area_ha[String(v)] ?? 0), 0) / 100;
  const lines = r.classes.map((c) => ({ label: c.label, color: c.color, points: r.rows.map((row) => ({ date: row.date, value: km2(row, [c.value]) })) }));
  const wet = r.classes.filter((c) => WET.includes(c.label)).map((c) => c.value);
  if (wet.length > 1) lines.unshift({ label: "All water", color: "#e2e8f0", points: r.rows.map((row) => ({ date: row.date, value: km2(row, wet) })) });
  return lines;
}

function boxPolygon([w, s, e, n]: number[]): GeoPolygon {
  return { type: "Polygon", coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] };
}

/** Research plots for one study. `onReady` fires once everything has loaded (the PDF waits for it). */
export default function ResearchPlots({ m, print, onReady }: { m: Manifest; print?: boolean; onReady?: () => void }) {
  const split = useMemo(() => splitLayer(m), [m]);
  const splitDate = split ? split.dates[split.dates.length - 1] : null;
  const variables = m.series.map((s) => s.variable).filter((v) => v !== "hh_db" || !m.series.some((s) => s.variable === "hv_db") || print);
  const hasDhv = m.layers.some((l) => l.id === "dhv");
  const hasAgreement = m.kind === "showcase" && !!split && split.kind === "prediction" && m.layers.some((l) => l.kind === "baseline" && l.colormap === "categorical");

  const [byClass, setByClass] = useState<Record<string, SeriesByClass | null>>({});
  const [change, setChange] = useState<ChangeByDate | null | undefined>(undefined);
  const [agree, setAgree] = useState<Agreement | null | undefined>(undefined);
  const [area, setArea] = useState<Timeseries | null | undefined>(undefined);
  const hasPulse = !!split && split.dates.length > 1;
  const [pulse, setPulse] = useState<ClassArea | null | undefined>(undefined);
  const [imgDone, setImgDone] = useState(!hasAgreement);

  useEffect(() => {
    const ctl = new AbortController();
    if (split && splitDate)
      for (const v of variables)
        fetchSeriesByClass(m.id, v, split.id, splitDate, ctl.signal)
          .then((r) => setByClass((s) => ({ ...s, [v]: r })))
          .catch(() => setByClass((s) => ({ ...s, [v]: null })));
    if (hasDhv) fetchChangeByDate(m.id, "dhv", 3, ctl.signal).then(setChange).catch(() => setChange(null));
    if (hasAgreement) fetchAgreement(m.id, ctl.signal).then(setAgree).catch(() => setAgree(null));
    if (hasPulse) fetchClassArea(m.id, ctl.signal).then(setPulse).catch(() => setPulse(null));
    if (m.series[0]) fetchAreaSeries(m.id, m.series[0].variable, boxPolygon(m.bbox), ctl.signal).then(setArea).catch(() => setArea(null));
    return () => ctl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [m.id]);

  const done =
    (!split || variables.every((v) => v in byClass)) && (!hasDhv || change !== undefined) && (!hasAgreement || (agree !== undefined && imgDone)) && (!m.series[0] || area !== undefined) && (!hasPulse || pulse !== undefined);
  useEffect(() => {
    if (done) onReady?.();
  }, [done, onReady]);

  const coverage = area ? Object.fromEntries(area.series.map((p) => [p.date, p.n ?? 0])) : undefined;
  const H = print ? "text-base font-semibold" : "text-sm font-medium text-ink";
  const P = "mt-1 text-xs leading-relaxed text-ink-2";
  const W = print ? 720 : 560;

  return (
    <div className="flex flex-col gap-7">
      <section className="break-inside-avoid">
        <h3 className={H}>When NISAR looked</h3>
        <p className={P}>Each bar is one Pass (12 days apart). Colour: the calibrated collection it comes from. Height: how much of the area had valid data that day (low bars mean water, steep slopes or swath edges were masked).</p>
        <div className="mt-2"><PassTimeline passes={m.passes} coverage={coverage} eventDate={m.event_date} width={W} /></div>
      </section>

      {pulse && pulse.rows.length > 1 && (() => {
        const lines = areaLines(pulse);
        const main = lines[0];
        const peak = main.points.reduce((a, b) => (b.value > a.value ? b : a), main.points[0]);
        const low = main.points.reduce((a, b) => (b.value < a.value ? b : a), main.points[0]);
        const isWater = pulse.classes.some((c) => WET.includes(c.label));
        return (
          <section className="break-inside-avoid">
            <h3 className={H}>{isWater ? "The flood pulse: water through the season" : "Each class through time"}</h3>
            <p className={P}>
              Area of each class of &ldquo;{pulse.label}&rdquo; on every Pass, in km². {main.label} peaks on {longDate(peak.date)} ({peak.value.toFixed(0)} km²) and is lowest on {longDate(low.date)} ({low.value.toFixed(0)} km²).
              {isWater && " A real flood pulse rises and falls smoothly over weeks; a peak on the very first Pass, or jumps between neighbouring Passes, usually mean the Model is reacting to something else (wind on water, wet soil, a new look angle). Compare with optical images on clear days."}
            </p>
            <div className="mt-2"><MultiLineChart width={W} still={print} unit="km²" eventDate={m.event_date} lines={lines} /></div>
          </section>
        );
      })()}

      {split &&
        variables.map((v) => {
          const r = byClass[v];
          if (!r || !r.classes.length) return null;
          return (
            <section key={v} className="break-inside-avoid">
              <h3 className={H}>{VAR_LABEL[v] ?? v}: inside each {split.kind === "prediction" ? "AI Model" : "Baseline"} class</h3>
              <p className={P}>
                Mean of every {m.series.find((s) => s.variable === v)?.grid_m ?? ""} m cell in each class of &ldquo;{r.layer_label}&rdquo; on {longDate(r.date)}; shading is the middle half of values. {READ[v]}
              </p>
              <div className="mt-2">
                <MultiLineChart
                  width={W}
                  still={print}
                  unit={r.unit}
                  eventDate={m.event_date}
                  lines={r.classes.map((c) => ({ label: c.label, color: c.color ?? NEUTRAL, points: c.series, note: ` (${c.cells.toLocaleString("en-GB")} cells)` }))}
                />
              </div>
            </section>
          );
        })}

      {change && change.rows.length > 0 && (
        <section className="break-inside-avoid">
          <h3 className={H}>When the biggest changes happened</h3>
          <p className={P}>
            Share of the area where vegetation scattering (HV) fell (red, below the line) or rose (blue, above) by more than {change.threshold} dB since the previous Pass. A single tall bar right after the event is the event; bars on many dates are season, harvest, rain or noise. Strong drops that recover at the next Pass are usually noise.
          </p>
          <div className="mt-2"><ChangeBars rows={change.rows} threshold={change.threshold} unit="dB" eventDate={m.event_date} width={W} /></div>
        </section>
      )}

      {agree && (
        <section className="break-inside-avoid">
          <h3 className={H}>Where the AI Model and the Baseline agree</h3>
          <p className={P}>
            Red: both flag it. Amber: only the AI Model. Blue: only the Baseline rule. Amber areas are what the Model adds; check them against optical images before relying on them. They overlap on {agree.overlap_share !== null ? `${(agree.overlap_share * 100).toFixed(0)}%` : "n/a"} of the area either one flags.
          </p>
          <div className={`mt-2 grid items-start gap-4 ${print ? "grid-cols-[2fr_1fr]" : "grid-cols-1"}`}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={agreementPngUrl(m.id, print ? 1100 : 800)} alt="Agreement map between the AI Model and the Baseline" onLoad={() => setImgDone(true)} onError={() => setImgDone(true)}
              className="w-full rounded border border-line bg-[repeating-conic-gradient(rgb(127_127_127/0.12)_0_25%,transparent_0_50%)] [background-size:16px_16px]" />
            <table className="w-full text-sm">
              <tbody>
                {agree.classes.map((c) => (
                  <tr key={c.value} className="border-t border-line first:border-0">
                    <td className="py-1.5"><span className="mr-2 inline-block h-3 w-3 rounded-sm align-middle" style={{ background: c.color }} />{c.label}</td>
                    <td className="py-1.5 text-right font-mono">{ha(c.area_ha)}</td>
                  </tr>
                ))}
                <tr className="border-t border-line text-ink-3"><td className="py-1.5">Area with data</td><td className="py-1.5 text-right font-mono">{ha(agree.analysed_ha)}</td></tr>
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
