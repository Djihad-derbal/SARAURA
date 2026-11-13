"use client";

import { Layers, Mountain, X } from "lucide-react";
import { useState } from "react";
import { longDate, type Pol, type Stack } from "@/lib/api";

type Props = {
  stacks: Stack[];
  stack: Stack | null;
  pol: Pol;
  showChange: boolean;
  terrain: boolean;
  baselineIdx: number;
  open: boolean;
  onOpen: (open: boolean) => void;
  onStack: (s: Stack) => void;
  onPol: (p: Pol) => void;
  onChange: (on: boolean) => void;
  onTerrain: (on: boolean) => void;
  onBaseline: (i: number) => void;
  /** Content of the AI tab. */
  ai: React.ReactNode;
};

const LAYERS: { id: Pol; label: string; help: string }[] = [
  { id: "HV", label: "HV", help: "Cross-polarized echo. Bright where the surface scatters in many directions, such as forest canopy. Dark over water and bare, smooth ground." },
  { id: "HH", label: "HH", help: "Same-polarized echo. Bright over rough ground, buildings and flooded vegetation. Dark over calm water." },
  { id: "RGB", label: "Colour", help: "Both channels combined. Green tones are vegetation, purple is bare or sparse ground, dark blue is water, pale spots are built-up areas." },
];

function Switch({ on, onChange, label, icon }: { on: boolean; onChange: (v: boolean) => void; label: string; icon?: React.ReactNode }) {
  return (
    <button type="button" role="switch" aria-checked={on} onClick={() => onChange(!on)} className="flex min-h-11 w-full cursor-pointer items-center justify-between gap-3 rounded-lg px-1 text-left text-sm text-ink transition-colors duration-200 hover:bg-white/5">
      <span className="flex items-center gap-2">
        {icon}
        {label}
      </span>
      <span className={"relative h-5 w-9 shrink-0 rounded-full transition-colors duration-200 " + (on ? "bg-accent" : "bg-white/20")}>
        <span className={"absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform duration-200 " + (on ? "translate-x-[18px]" : "translate-x-0.5")} />
      </span>
    </button>
  );
}

export default function ControlPanel(p: Props) {
  const [tab, setTab] = useState<"layers" | "ai">("layers");
  if (!p.open) {
    return (
      <button type="button" onClick={() => p.onOpen(true)} aria-label="Open layer controls" className="panel flex h-11 cursor-pointer items-center gap-2 px-3 text-sm text-ink transition-colors duration-200 hover:bg-white/10">
        <Layers className="h-4 w-4" /> Layers
      </button>
    );
  }
  const active = LAYERS.find((l) => l.id === p.pol)!;
  return (
    <section className="panel w-[300px] max-w-[calc(100vw-24px)] p-4" aria-label="Layer controls">
      <div className="mb-3 flex items-start justify-between gap-2">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-wider text-accent">Act 1 · Fire</p>
          <h2 className="font-display text-2xl leading-tight text-ink">North-east Algeria, August 2026</h2>
        </div>
        <button type="button" onClick={() => p.onOpen(false)} aria-label="Close layer controls" className="-mr-1 -mt-1 flex h-9 w-9 cursor-pointer items-center justify-center rounded-lg text-ink-3 transition-colors duration-200 hover:bg-white/10 hover:text-ink">
          <X className="h-4 w-4" />
        </button>
      </div>
      <p className="mb-4 text-[13px] leading-relaxed text-ink-2">Wildfires swept the coastal mountains from Béjaïa to Skikda in late August. Play the timeline to watch the radar echo change.</p>

      <div role="tablist" aria-label="Panel section" className="mb-4 grid grid-cols-2 border-b border-line">
        {(["layers", "ai"] as const).map((t) => (
          <button key={t} type="button" role="tab" aria-selected={tab === t} onClick={() => setTab(t)} className={"-mb-px h-10 cursor-pointer border-b-2 text-sm transition-colors duration-200 " + (tab === t ? "border-accent text-ink" : "border-transparent text-ink-3 hover:text-ink")}>
            {t === "layers" ? "Layers" : "AI analysis"}
          </button>
        ))}
      </div>
      {tab === "ai" ? (
        p.ai
      ) : (
        <>
      <label htmlFor="track" className="mb-1 block font-mono text-[11px] uppercase tracking-wider text-ink-3">
        Satellite track
      </label>
      <select
        id="track"
        value={p.stack ? `${p.stack.stack}|${p.stack.bandwidth_mhz}` : ""}
        onChange={(e) => {
          const s = p.stacks.find((x) => `${x.stack}|${x.bandwidth_mhz}` === e.target.value);
          if (s) p.onStack(s);
        }}
        className="mb-4 h-11 w-full cursor-pointer rounded-lg border border-line bg-panel-solid px-2 text-sm text-ink"
      >
        {p.stacks.map((s) => (
          <option key={`${s.stack}|${s.bandwidth_mhz}`} value={`${s.stack}|${s.bandwidth_mhz}`}>
            Track {s.track} · {s.direction} · {s.passes.length} passes
          </option>
        ))}
      </select>

      <div className="mb-1 font-mono text-[11px] uppercase tracking-wider text-ink-3">Radar layer</div>
      <div role="radiogroup" aria-label="Radar layer" className="mb-2 grid grid-cols-3 gap-1 rounded-lg bg-white/5 p-1">
        {LAYERS.map((l) => (
          <button key={l.id} type="button" role="radio" aria-checked={p.pol === l.id} onClick={() => p.onPol(l.id)} className={"h-9 cursor-pointer rounded-md text-sm transition-colors duration-200 " + (p.pol === l.id ? "bg-white/15 text-ink" : "text-ink-2 hover:text-ink")}>
            {l.label}
          </button>
        ))}
      </div>
      <p className="mb-4 text-[13px] leading-relaxed text-ink-2">{active.help}</p>

      <div className="border-t border-line pt-2">
        <Switch on={p.showChange} onChange={p.onChange} label="Show what changed" />
        {p.showChange && p.stack && (
          <div className="mb-2 mt-1 rounded-lg bg-white/5 p-3">
            <label htmlFor="baseline" className="mb-1 block text-[13px] text-ink-2">
              Compared with the pass on
            </label>
            <select id="baseline" value={p.baselineIdx} onChange={(e) => p.onBaseline(Number(e.target.value))} className="mb-3 h-10 w-full cursor-pointer rounded-lg border border-line bg-panel-solid px-2 text-sm text-ink">
              {p.stack.passes.map((x, i) => (
                <option key={x.id} value={i}>
                  {longDate(x.date)}
                </option>
              ))}
            </select>
            <ul className="space-y-1.5 text-[13px] text-ink-2">
              <li className="flex items-center gap-2">
                <span className="h-3 w-3 shrink-0 rounded-sm bg-drop" aria-hidden /> Echo got weaker
              </li>
              <li className="flex items-center gap-2">
                <span className="h-3 w-3 shrink-0 rounded-sm bg-rise" aria-hidden /> Echo got stronger
              </li>
            </ul>
            <p className="mt-2 text-xs leading-relaxed text-ink-3">Changes under 1.5 dB are hidden. Red patches match the fires in place and time but are not yet verified against fire records.</p>
          </div>
        )}
        <Switch on={p.terrain} onChange={p.onTerrain} label="3D terrain" icon={<Mountain className="h-4 w-4 text-ink-3" />} />
      </div>
        </>
      )}
    </section>
  );
}
