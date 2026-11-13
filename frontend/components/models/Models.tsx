"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { StatusBadge } from "@/components/study/StudyPage";
import { fetchModelCard, fetchModels, longDate, lowerIsBetter, type ModelCard, type ModelRow, type Score } from "@/lib/api";
import { LENSES, fmt } from "@/lib/style";

const LABEL_KIND = { real: "Real labels", proxy: "Proxy labels", self_supervised: "Self-supervised" } as const;

/** Model and Baseline side by side; the better one is marked in words, not colour alone. */
export function ScoreBars({ metric, model, baseline }: { metric: string; model: number; baseline: number }) {
  const lower = lowerIsBetter(metric);
  const max = Math.max(model, baseline) || 1;
  const modelWins = lower ? model < baseline : model > baseline;
  const rows = [
    { name: "AI Model", v: model, color: "var(--accent)" },
    { name: "Baseline", v: baseline, color: "var(--ink-3)" },
  ];
  return (
    <div>
      {rows.map((r) => (
        <div key={r.name} className="flex items-center gap-2 text-xs">
          <span className="w-16 shrink-0 text-ink-2">{r.name}</span>
          <div className="h-2.5 flex-1 rounded-sm bg-white/5">
            <div className="h-full rounded-sm" style={{ width: `${(r.v / max) * 100}%`, background: r.color }} />
          </div>
          <span className="w-14 shrink-0 text-right font-mono text-ink">{fmt(r.v)}</span>
        </div>
      ))}
      <p className={`mt-1 text-xs ${modelWins ? "text-emerald-300" : "text-drop"}`}>
        {modelWins ? "The Model beats its Baseline" : "The Model does not beat its Baseline"} ({metric}, {lower ? "lower" : "higher"} is better)
      </p>
    </div>
  );
}

export function ModelsTable() {
  const [rows, setRows] = useState<ModelRow[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    fetchModels().then(setRows).catch((e) => setErr(e.message));
  }, []);
  return (
    <main className="h-dvh overflow-y-auto bg-bg">
      <div className="mx-auto max-w-5xl px-4 py-8">
        <Link href="/" className="text-xs text-ink-3 hover:text-ink">← Globe</Link>
        <h1 className="mt-2 font-display text-4xl">Models</h1>
        <p className="mt-2 max-w-2xl text-ink-2">
          One AI Model per Lens, each scored against a simple Baseline on ground it did not train on. AI runs only on the Showcase Sites; your own Analyses get the radar measurements and the Baseline.
        </p>
        {err && <p className="mt-6 text-drop" role="alert">{err}</p>}
        {!rows && !err && <div className="busy-bar mt-8 h-0.5" />}
        <ul className="mt-6 grid gap-3 sm:grid-cols-2">
          {rows?.map((r) => (
            <li key={r.lens}>
              <Link href={`/models/${r.lens}`} className="panel block p-4 transition-colors duration-200 hover:bg-white/10">
                <div className="flex items-center gap-2 text-xs">
                  <span className="font-medium uppercase tracking-wide" style={{ color: LENSES[r.lens].color }}>{LENSES[r.lens].label}</span>
                  <span className="text-ink-3">· {LABEL_KIND[r.labels]}</span>
                  <span className="ml-auto"><StatusBadge status={r.status} /></span>
                </div>
                <h2 className="mt-1 text-[15px] font-medium">{r.name}</h2>
                <p className="mb-3 text-xs text-ink-3">Baseline: {r.baseline}</p>
                <ScoreBars metric={r.metric} model={r.model_score} baseline={r.baseline_score} />
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </main>
  );
}

function ScoreList({ scores }: { scores: Score[] }) {
  return (
    <table className="w-full text-sm">
      <tbody>
        {scores.map((s) => (
          <tr key={s.name} className="border-t border-line first:border-0">
            <td className="py-1.5 pr-3 text-ink-2">{s.name}</td>
            <td className="py-1.5 pr-3 text-xs text-ink-3">{s.metric}</td>
            <td className="py-1.5 text-right font-mono">{fmt(s.score)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function ModelCardView({ lens, print }: { lens: string; print?: boolean }) {
  const [c, setC] = useState<ModelCard | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    fetchModelCard(lens).then(setC).catch((e) => setErr(e.message));
  }, [lens]);
  if (err) return <p className="p-6 text-drop" role="alert">{err}</p>;
  if (!c) return <div className="busy-bar m-8 h-0.5" />;
  const L = LENSES[c.lens];
  const body = (
    <article className="mx-auto max-w-3xl px-4 py-8" data-model-card-ready>
      {!print && <Link href="/models" className="text-xs text-ink-3 hover:text-ink">← All Models</Link>}
      <div className="mt-2 flex items-center gap-2 text-xs">
        <span className="font-medium uppercase tracking-wide" style={{ color: L.color }}>{L.label}</span>
        <span className="text-ink-3">· Model card · updated {longDate(c.updated)}</span>
        <span className="ml-auto"><StatusBadge status={c.status} /></span>
      </div>
      <h1 className="mt-1 font-display text-3xl leading-tight">{c.model.name}</h1>
      <p className="mt-2 text-ink">{c.job}.</p>
      <p className="mt-1 text-sm text-ink-2">For: {c.user}.</p>

      <section className="mt-6">
        <h2 className="text-xs font-medium uppercase tracking-wide text-ink-3">Score against the Baseline</h2>
        <div className="mt-2 max-w-md">
          {c.model.score !== null && c.baseline.score !== null && <ScoreBars metric={c.model.metric} model={c.model.score} baseline={c.baseline.score} />}
        </div>
        <p className="mt-2 text-sm text-ink-2">Baseline: {c.baseline.name}. Test: {c.split}.</p>
      </section>

      {!!c.extra_scores?.length && (
        <section className="mt-6">
          <h2 className="text-xs font-medium uppercase tracking-wide text-ink-3">Other scores</h2>
          <div className="mt-2"><ScoreList scores={c.extra_scores} /></div>
        </section>
      )}

      <section className="mt-6">
        <h2 className="text-xs font-medium uppercase tracking-wide text-ink-3">Labels</h2>
        <p className="mt-2 text-sm"><span className="rounded bg-white/10 px-1.5 py-0.5 text-xs">{LABEL_KIND[c.labels.kind]}</span> {c.labels.source}</p>
        {c.labels.notes && <p className="mt-1 text-sm text-ink-2">{c.labels.notes}</p>}
      </section>

      <section className="mt-6">
        <h2 className="text-xs font-medium uppercase tracking-wide text-ink-3">Limits</h2>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-ink-2">{c.limits.map((l) => <li key={l}>{l}</li>)}</ul>
      </section>

      <section className="mt-6 grid gap-4 sm:grid-cols-2">
        <div>
          <h2 className="text-xs font-medium uppercase tracking-wide text-ink-3">Inputs</h2>
          <p className="mt-2 text-sm text-ink-2">{c.inputs.join(", ")}</p>
          {c.model.framework && <p className="mt-1 text-xs text-ink-3">{c.model.framework}{c.model.parameters ? `, ${c.model.parameters.toLocaleString("en-GB")} parameters` : ""}</p>}
        </div>
        <div>
          <h2 className="text-xs font-medium uppercase tracking-wide text-ink-3">Showcase Sites</h2>
          <ul className="mt-2 text-sm">
            {c.sites.map((s) => <li key={s}>{print ? s : <Link href={`/study/${s}`} className="text-accent underline underline-offset-2">{s}</Link>}</li>)}
          </ul>
        </div>
      </section>
    </article>
  );
  return print ? body : <main className="h-dvh overflow-y-auto bg-bg">{body}</main>;
}
