"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { fetchSeries, fetchStacks, type Pol, type Series, type Stack } from "@/lib/api";
import ControlPanel from "./ControlPanel";
import Inspector from "./Inspector";
import Intro from "./Intro";
import MapView, { type Focus, type View } from "./MapView";
import Timeline from "./Timeline";

// Act 1: the late-August 2026 fires in north-east Algeria.
const STORY = {
  bbox: [3.8, 36.3, 7.2, 37.1] as [number, number, number, number],
  stack: "109_D_070",
  before: "2026-08-20",
  after: "2026-09-01",
  focus: { center: [6.02, 36.7], zoom: 9.6, pitch: 55, bearing: -18 } as Focus,
};
const FRAME_MS = 1500;

export default function Explorer() {
  const reduced = useReducedMotion() ?? false;
  // /browse is a tool page reached from Explore, so it opens on the Granules, not the old intro.
  const [phase, setPhase] = useState<"intro" | "explore">("explore");
  const [stacks, setStacks] = useState<Stack[]>([]);
  const [stack, setStack] = useState<Stack | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [baselineIdx, setBaselineIdx] = useState(0);
  const [pol, setPol] = useState<Pol>("HV");
  const [showChange, setShowChange] = useState(true);
  const [terrain, setTerrain] = useState(true);
  // Start with the panel closed on phones, where it would cover the map.
  const [panelOpen, setPanelOpen] = useState(() => !window.matchMedia("(max-width: 767px)").matches);
  const [busy, setBusy] = useState(false);
  const [play, setPlay] = useState<"stopped" | "buffering" | "playing">("stopped");
  const [probe, setProbe] = useState<{ lon: number; lat: number } | null>(null);
  const [series, setSeries] = useState<Series | null>(null);
  const [seriesLoading, setSeriesLoading] = useState(false);
  const [seriesError, setSeriesError] = useState<string | null>(null);
  const [passesReady, setPassesReady] = useState(0);
  const readyRef = useRef(0);
  const onProgress = useCallback((b: boolean, ready: number) => {
    readyRef.current = ready;
    setBusy(b);
    setPassesReady(ready);
  }, []);

  const [goTo] = useState<{ lon: number; lat: number; zoom: number; key: number } | null>(null);
  const viewRef = useRef<View | null>(null);
  const onView = useCallback((v: View) => {
    viewRef.current = v;
  }, []);

  const choose = useCallback((s: Stack) => {
    setStack(s);
    const idx = (date: string, fallback: number) => {
      const i = s.passes.findIndex((p) => p.date === date);
      return i >= 0 ? i : fallback;
    };
    setCurrentIdx(idx(STORY.after, s.passes.length - 1));
    setBaselineIdx(idx(STORY.before, 0));
    setPlay("stopped");
    setProbe(null);
    setSeries(null);
  }, []);

  const load = useCallback(() => {
    fetchStacks(STORY.bbox)
      .then((r) => {
        setStacks(r.stacks);
        const first = r.stacks.find((s) => s.stack === STORY.stack) ?? r.stacks[0];
        if (first) choose(first);
        else setLoadError("No NISAR passes were found over this area.");
      })
      .catch(() => setLoadError("Cannot reach the radar service. Start the backend on port 8000, then retry."));
  }, [choose]);
  useEffect(load, [load]);

  // Playback: load every pass first, then step through them.
  useEffect(() => {
    if (play !== "buffering") return;
    const started = Date.now();
    const t = setInterval(() => {
      const waited = Date.now() - started;
      const total = stack?.passes.length ?? 0;
      if ((waited > 900 && readyRef.current >= total) || waited > 240000) setPlay("playing");
    }, 200);
    return () => clearInterval(t);
  }, [play, stack]);
  useEffect(() => {
    if (play !== "playing" || !stack) return;
    const t = setInterval(() => setCurrentIdx((i) => (i + 1) % stack.passes.length), FRAME_MS);
    return () => clearInterval(t);
  }, [play, stack]);

  // Point time series.
  useEffect(() => {
    if (!probe || !stack) return;
    const ctl = new AbortController();
    fetchSeries(probe.lon, probe.lat, stack.stack, ctl.signal)
      .then(setSeries)
      .catch((e) => {
        if (e.name !== "AbortError") setSeriesError(e.message || "Could not read this point.");
      })
      .finally(() => !ctl.signal.aborted && setSeriesLoading(false));
    return () => ctl.abort();
  }, [probe, stack]);

  const passes = useMemo(() => stack?.passes ?? [], [stack]);

  const onClick = useCallback((lon: number, lat: number) => {
    setSeries(null);
    setSeriesError(null);
    setSeriesLoading(true);
    setProbe({ lon, lat });
  }, []);
  const jumpTo = useCallback(
    (date: string) => {
      const i = passes.findIndex((p) => p.date === date);
      if (i >= 0) {
        setPlay("stopped");
        setCurrentIdx(i);
      }
    },
    [passes],
  );

  return (
    <main className="relative h-dvh w-full overflow-hidden bg-bg">
      <MapView
        phase={phase}
        focus={STORY.focus}
        stacks={stacks}
        stack={phase === "explore" ? stack : null}
        currentIdx={currentIdx}
        baselineIdx={baselineIdx}
        pol={pol}
        showChange={showChange && phase === "explore"}
        analysis={null}
        goTo={goTo}
        onView={onView}
        terrain={terrain}
        preload={play !== "stopped"}
        probe={probe}
        reducedMotion={reduced}
        onClick={onClick}
        onProgress={onProgress}
      />

      {busy && phase === "explore" && <div className="busy-bar pointer-events-none absolute inset-x-0 top-0 z-30 h-0.5" role="status" aria-label="Loading radar data" />}

      <AnimatePresence>{phase === "intro" && <Intro key="intro" onEnter={() => setPhase("explore")} ready={!!stack} reduced={reduced} />}</AnimatePresence>

      {loadError && (
        <div className="panel absolute left-1/2 top-4 z-50 flex -translate-x-1/2 items-center gap-3 px-4 py-3 text-sm text-ink" role="alert">
          {loadError}
          <button
            type="button"
            onClick={() => {
              setLoadError(null);
              load();
            }}
            className="h-9 cursor-pointer rounded-lg bg-white/10 px-3 transition-colors duration-200 hover:bg-white/20">
            Retry
          </button>
        </div>
      )}

      <AnimatePresence>
        {phase === "explore" && (
          <>
            <motion.div key="controls" className="absolute left-3 top-3 z-20 max-h-[calc(100dvh-120px)] overflow-y-auto sm:left-4 sm:top-4" initial={reduced ? false : { opacity: 0, x: -24 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.6, delay: reduced ? 0 : 2.4 }}>
              <ControlPanel
                stacks={stacks}
                stack={stack}
                pol={pol}
                showChange={showChange}
                terrain={terrain}
                baselineIdx={baselineIdx}
                open={panelOpen}
                onOpen={setPanelOpen}
                onStack={choose}
                onPol={setPol}
                onChange={setShowChange}
                onTerrain={setTerrain}
                onBaseline={setBaselineIdx}
                ai={
                  <p className="text-sm leading-relaxed text-ink-2">
                    This view shows raw NISAR Granules. To analyse an area with a Lens, use{" "}
                    <Link href="/?mode=explore" className="text-accent underline underline-offset-2">Explore</Link>.
                  </p>
                }
              />
            </motion.div>

            <motion.div key="timeline" className="absolute inset-x-3 bottom-8 z-20 mx-auto max-w-4xl sm:inset-x-4" initial={reduced ? false : { opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: reduced ? 0 : 2.8 }}>
              <Timeline
                passes={passes}
                currentIdx={currentIdx}
                baselineIdx={baselineIdx}
                showBaseline={showChange}
                playing={play === "playing"}
                buffering={play === "buffering"}
                passesReady={passesReady}
                onSelect={(i) => {
                  setPlay("stopped");
                  setCurrentIdx(i);
                }}
                onTogglePlay={() => setPlay((p) => (p === "stopped" ? (reduced ? "playing" : "buffering") : "stopped"))}
              />
            </motion.div>
          </>
        )}
        {phase === "explore" && probe && (
          <motion.div key="inspector" className="absolute bottom-28 right-3 top-auto z-20 max-h-[calc(100dvh-200px)] sm:right-4 md:bottom-auto md:top-16" initial={reduced ? false : { opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 24 }} transition={{ duration: 0.25 }}>
            <Inspector
              probe={probe}
              series={series}
              loading={seriesLoading}
              error={seriesError}
              currentDate={passes[currentIdx]?.date}
              baselineDate={showChange ? passes[baselineIdx]?.date : undefined}
              animate={!reduced}
              finding={null}
              onPick={jumpTo}
              onClose={() => setProbe(null)}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </main>
  );
}
