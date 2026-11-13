"use client";

import { Loader2, X } from "lucide-react";
import { shortDate, type Finding, type Series } from "@/lib/api";
import SeriesChart from "./SeriesChart";

type Props = {
  probe: { lon: number; lat: number };
  series: Series | null;
  loading: boolean;
  error: string | null;
  currentDate?: string;
  baselineDate?: string;
  animate: boolean;
  finding: Finding | null;
  onPick: (date: string) => void;
  onClose: () => void;
};

function reading(series: Series, before?: string, after?: string) {
  const a = series.series.find((p) => p.date === before);
  const b = series.series.find((p) => p.date === after);
  if (!a || !b || a === b) return null;
  const dHV = typeof a.HV === "number" && typeof b.HV === "number" ? b.HV - a.HV : null;
  const dHH = typeof a.HH === "number" && typeof b.HH === "number" ? b.HH - a.HH : null;
  if (dHV === null || dHH === null) return null;
  let meaning = "Both channels are close to where they started. Nothing at this spot stands out from normal pass-to-pass variation.";
  if (dHV <= -1.5 && dHH > -1.5) meaning = "The cross-polarized echo weakened while HH held steady. That pattern usually means vegetation structure was lost. It is consistent with fire but is not confirmed here.";
  else if (dHV <= -1.5 && dHH <= -1.5) meaning = "Both channels weakened. That happens when a surface becomes smoother or wetter, for example open water appearing, or vegetation being cleared.";
  else if (dHV >= 1.5 || dHH >= 1.5) meaning = "The echo strengthened. Common causes are rain-wetted soil, growing vegetation or a rougher surface.";
  return { dHV, dHH, meaning };
}

const fmt = (v: number) => `${v > 0 ? "+" : ""}${v.toFixed(1)} dB`;

export default function Inspector({ probe, series, loading, error, currentDate, baselineDate, animate, finding, onPick, onClose }: Props) {
  const r = series ? reading(series, baselineDate, currentDate) : null;
  return (
    <aside className="panel max-h-full w-[360px] max-w-[calc(100vw-24px)] overflow-y-auto p-4" aria-label="Point inspector" aria-live="polite">
      <div className="mb-3 flex items-start justify-between gap-2">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-wider text-ink-3">At this point</p>
          <p className="font-mono text-sm tabular-nums text-ink">
            {Math.abs(probe.lat).toFixed(4)}°{probe.lat >= 0 ? "N" : "S"}, {Math.abs(probe.lon).toFixed(4)}°{probe.lon >= 0 ? "E" : "W"}
          </p>
        </div>
        <button type="button" onClick={onClose} aria-label="Close inspector" className="-mr-1 -mt-1 flex h-9 w-9 cursor-pointer items-center justify-center rounded-lg text-ink-3 transition-colors duration-200 hover:bg-white/10 hover:text-ink">
          <X className="h-4 w-4" />
        </button>
      </div>

      {finding?.class && (
        <p className="mb-3 rounded-lg bg-white/5 px-3 py-2 text-[13px] leading-relaxed text-ink">
          <span className="text-ink-3">Analysis: </span>
          {finding.class === "stable" ? "no clear change here." : `${finding.label}, first seen ${finding.changed_on ? shortDate(finding.changed_on) : "at an unknown date"} (HV ${(finding.hv_change_db ?? 0) > 0 ? "+" : ""}${(finding.hv_change_db ?? 0).toFixed(1)} dB).`}
        </p>
      )}
      {loading && (
        <div className="flex min-h-[220px] flex-col items-center justify-center gap-3 text-center">
          <Loader2 className="h-6 w-6 animate-spin text-accent" />
          <p className="text-sm text-ink">Reading every pass at this point</p>
          <p className="max-w-[26ch] text-xs leading-relaxed text-ink-3">The first reading on a track fetches from NASA and can take up to a minute. After that it is quick.</p>
        </div>
      )}
      {error && !loading && <p className="rounded-lg bg-red-500/10 p-3 text-sm text-red-200">{error}</p>}
      {series && !loading && (
        <>
          <SeriesChart points={series.series} currentDate={currentDate} baselineDate={baselineDate} animate={animate} onPick={onPick} />
          {r && baselineDate && currentDate && (
            <div className="mt-3 border-t border-line pt-3">
              <p className="mb-2 text-xs text-ink-3">
                From {shortDate(baselineDate)} to {shortDate(currentDate)}
              </p>
              <dl className="mb-3 grid grid-cols-2 gap-2">
                {[
                  ["HV", r.dHV],
                  ["HH", r.dHH],
                ].map(([k, v]) => (
                  <div key={k as string} className="rounded-lg bg-white/5 px-3 py-2">
                    <dt className="text-xs text-ink-3">{k as string}</dt>
                    <dd className="font-mono text-lg tabular-nums text-ink">{fmt(v as number)}</dd>
                  </div>
                ))}
              </dl>
              <p className="text-[13px] leading-relaxed text-ink-2">{r.meaning}</p>
            </div>
          )}
          <p className="mt-3 text-xs leading-relaxed text-ink-3">
            Average over a {Math.round(series.radius_m * 2)} m square, track {series.stack.split("_")[0].replace(/^0+/, "")}. Click a point on the chart to jump to that pass.
          </p>
        </>
      )}
    </aside>
  );
}
