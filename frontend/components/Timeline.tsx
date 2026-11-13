"use client";

import { ChevronLeft, ChevronRight, Loader2, Pause, Play } from "lucide-react";
import { motion } from "motion/react";
import { longDate, shortDate, type Pass } from "@/lib/api";

type Props = {
  passes: Pass[];
  currentIdx: number;
  baselineIdx: number;
  showBaseline: boolean;
  playing: boolean;
  buffering: boolean;
  passesReady: number;
  onSelect: (i: number) => void;
  onTogglePlay: () => void;
};

const day = (iso: string) => Date.parse(iso + "T00:00:00Z") / 86400000;

export default function Timeline({ passes, currentIdx, baselineIdx, showBaseline, playing, buffering, passesReady, onSelect, onTogglePlay }: Props) {
  if (passes.length === 0) return null;
  const t0 = day(passes[0].date);
  const span = Math.max(1, day(passes[passes.length - 1].date) - t0);
  const pos = (i: number) => ((day(passes[i].date) - t0) / span) * 100;
  const step = (d: number) => onSelect((currentIdx + d + passes.length) % passes.length);

  return (
    <div
      className="panel flex items-center gap-3 px-3 py-2.5 sm:gap-4 sm:px-4"
      onKeyDown={(e) => {
        if (e.key === "ArrowLeft") step(-1);
        if (e.key === "ArrowRight") step(1);
      }}
    >
      <button
        type="button"
        onClick={onTogglePlay}
        aria-label={playing || buffering ? "Pause" : "Play through the passes"}
        className="flex h-11 w-11 shrink-0 cursor-pointer items-center justify-center rounded-full bg-accent text-black transition-colors duration-200 hover:bg-amber-400"
      >
        {buffering ? <Loader2 className="h-5 w-5 animate-spin" /> : playing ? <Pause className="h-5 w-5" /> : <Play className="h-5 w-5 translate-x-px" />}
      </button>

      <div className="min-w-0 shrink-0">
        <div className="font-mono text-[11px] uppercase tracking-wider text-ink-3">{buffering ? `Loading ${Math.min(passesReady, passes.length)} of ${passes.length}` : `Pass ${currentIdx + 1} of ${passes.length}`}</div>
        <div className="font-mono text-sm tabular-nums text-ink sm:text-base">{longDate(passes[currentIdx].date)}</div>
      </div>

      <button type="button" onClick={() => step(-1)} aria-label="Previous pass" className="hidden h-11 w-9 cursor-pointer items-center justify-center rounded-lg text-ink-2 transition-colors duration-200 hover:bg-white/10 hover:text-ink sm:flex">
        <ChevronLeft className="h-5 w-5" />
      </button>

      <div className="relative h-11 min-w-0 flex-1" role="group" aria-label="Radar passes">
        <div className="absolute left-0 right-0 top-1/2 h-px bg-white/15" />
        {passes.map((p, i) => {
          const current = i === currentIdx;
          const base = showBaseline && i === baselineIdx;
          return (
            <button
              key={p.id}
              type="button"
              onClick={() => onSelect(i)}
              aria-label={`${longDate(p.date)}${base ? ", comparison baseline" : ""}`}
              aria-current={current}
              title={longDate(p.date) + (base ? " (before)" : "")}
              style={{ left: `${pos(i)}%` }}
              className="group absolute top-0 flex h-11 w-7 -translate-x-1/2 cursor-pointer items-center justify-center"
            >
              {current && <motion.span layoutId="playhead" className="absolute h-5 w-5 rounded-full bg-accent/25 ring-1 ring-accent" transition={{ type: "spring", stiffness: 380, damping: 32 }} />}
              <span
                className={
                  "relative block rounded-full transition-colors duration-200 " +
                  (current ? "h-2.5 w-2.5 bg-accent" : base ? "h-2.5 w-2.5 border-2 border-ink bg-panel-solid" : "h-2 w-2 bg-ink-3 group-hover:bg-ink")
                }
              />
              {(current || base || i === 0 || i === passes.length - 1) && (
                <span
                  className={
                    "pointer-events-none absolute whitespace-nowrap font-mono text-[10px] " +
                    // The "before" label sits above the line so it never collides with the current date below it.
                    (base && !current ? "top-[-3px] text-ink-2 max-sm:hidden" : "top-[30px] " + (current ? "text-accent" : "text-ink-3 max-sm:hidden"))
                  }
                >
                  {base && !current ? "before · " : ""}
                  {shortDate(p.date)}
                </span>
              )}
            </button>
          );
        })}
      </div>

      <button type="button" onClick={() => step(1)} aria-label="Next pass" className="hidden h-11 w-9 cursor-pointer items-center justify-center rounded-lg text-ink-2 transition-colors duration-200 hover:bg-white/10 hover:text-ink sm:flex">
        <ChevronRight className="h-5 w-5" />
      </button>
    </div>
  );
}
