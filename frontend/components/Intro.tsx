"use client";

import { ArrowRight } from "lucide-react";
import { motion } from "motion/react";

const rise = (delay: number, reduced: boolean) => ({
  initial: reduced ? false : { opacity: 0, y: 18 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.9, delay, ease: [0.2, 0.7, 0.2, 1] as const },
});

export default function Intro({ onEnter, ready, reduced }: { onEnter: () => void; ready: boolean; reduced: boolean }) {
  return (
    <motion.div
      className="absolute inset-0 z-40 flex items-end justify-start bg-[radial-gradient(ellipse_at_70%_40%,transparent_20%,rgb(5_7_10/0.85)_75%)] p-6 sm:items-center sm:p-16"
      exit={{ opacity: 0, transition: { duration: reduced ? 0 : 0.8 } }}
    >
      <div className="max-w-xl">
        <motion.p {...rise(0.1, reduced)} className="mb-4 font-mono text-xs uppercase tracking-[0.2em] text-accent">
          NISAR L-band radar · NASA / ISRO
        </motion.p>
        <motion.h1 {...rise(0.25, reduced)} className="font-display text-5xl leading-[1.02] text-ink sm:text-7xl">
          Dancing with <em className="text-accent">the SARs</em>
        </motion.h1>
        <motion.p {...rise(0.45, reduced)} className="mt-6 max-w-[46ch] text-base leading-relaxed text-ink-2 sm:text-lg">
          Earth&apos;s surface never holds still. Every twelve days a radar satellite passes overhead and sees it move, by day or night, through cloud and smoke.
        </motion.p>
        <motion.div {...rise(0.65, reduced)} className="mt-8">
          <button
            type="button"
            onClick={onEnter}
            disabled={!ready}
            className="group flex h-12 cursor-pointer items-center gap-3 rounded-full bg-accent px-6 text-base font-medium text-black transition-colors duration-200 hover:bg-amber-400 disabled:cursor-wait disabled:opacity-60"
          >
            {ready ? "Begin in Algeria" : "Finding radar passes"}
            <ArrowRight className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-0.5" />
          </button>
        </motion.div>
      </div>
    </motion.div>
  );
}
