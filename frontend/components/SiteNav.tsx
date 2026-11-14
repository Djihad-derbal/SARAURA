"use client";

import { motion } from "motion/react";
import Link from "next/link";

type Section = "places" | "research" | "models";

const ITEMS: { id: Section; href: string; label: string; short: string }[] = [
  { id: "places", href: "/", label: "Places and decisions", short: "Places" },
  { id: "research", href: "/explore", label: "Research explorer", short: "Research" },
  { id: "models", href: "/models", label: "Models vs Baselines", short: "Models" },
];

/** A small Earth with a satellite on its orbit: the SARAURA mark. */
export function Mark({ size = 26 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden className="shrink-0">
      <defs>
        <radialGradient id="mk-earth" cx="35%" cy="30%" r="80%">
          <stop offset="0%" stopColor="#2dd4bf" />
          <stop offset="60%" stopColor="#0e5a6b" />
          <stop offset="100%" stopColor="#062534" />
        </radialGradient>
      </defs>
      <circle cx="16" cy="16" r="8.5" fill="url(#mk-earth)" />
      <ellipse cx="16" cy="16" rx="14" ry="5" fill="none" stroke="#5eead4" strokeOpacity="0.55" transform="rotate(-20 16 16)" />
      <g className="anim-spin" style={{ transformOrigin: "16px 16px", animationDuration: "9s" }}>
        <circle cx="29.2" cy="11.3" r="1.8" fill="#e4f2f4" />
      </g>
    </svg>
  );
}

/** The site's two halves, decisions first and research second, plus the Model scores. */
export default function SiteNav({ active, floating = false }: { active: Section; floating?: boolean }) {
  return (
    <nav aria-label="Main" className={`flex items-center gap-3 ${floating ? "" : "border-b border-line bg-bg/70 px-4 py-2.5 backdrop-blur-md sm:px-6"}`}>
      <Link href="/" className="mr-auto flex items-center gap-2">
        <Mark />
        <span className="font-display text-xl font-semibold tracking-tight text-ink">SARAURA</span>
        <span className="eyebrow hidden text-ink-3 md:inline">NISAR radar, explained</span>
      </Link>
      <ul className="panel flex gap-0.5 p-1">
        {ITEMS.map((it) => {
          const on = active === it.id;
          return (
            <li key={it.id} className="relative">
              {on && <motion.span layoutId="nav-pill" className="absolute inset-0 rounded-lg bg-accent/15 ring-1 ring-accent/40" transition={{ type: "spring", stiffness: 380, damping: 32 }} aria-hidden />}
              <Link href={it.href} aria-current={on ? "page" : undefined}
                className={`relative flex h-9 items-center rounded-lg px-3 text-[13px] transition-colors duration-200 ${on ? "font-medium text-ink" : "text-ink-2 hover:text-ink"}`}>
                <span className="sm:hidden">{it.short}</span>
                <span className="hidden sm:inline">{it.label}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
