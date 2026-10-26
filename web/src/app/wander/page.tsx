"use client";

import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { useShell } from "@/components/Shell";
import { hostOf } from "@/lib/format";
import { recordEvent, useResurface } from "@/lib/queries";
import { useHotkeys } from "@/lib/shortcuts";

/** One thing at a time, slowly. ← → or space to move, Enter to open, D for "not now". */
export default function WanderPage() {
  const { data, isPending } = useResurface("serendipity");
  const { openItem } = useShell();
  const [index, setIndex] = useState(0);
  const items = data?.items ?? [];
  const pick = items[index];

  const move = (d: number) => setIndex((i) => Math.min(Math.max(i + d, 0), Math.max(items.length - 1, 0)));
  const open = () => {
    if (!pick) return;
    recordEvent(pick.item.id, "open", { from: "resurface", surface: "serendipity" });
    openItem(pick.item.id);
  };
  const dismiss = () => {
    if (!pick) return;
    recordEvent(pick.item.id, "dismiss", { surface: "serendipity" });
    move(1);
  };
  useHotkeys({ ArrowRight: () => move(1), " ": () => move(1), ArrowLeft: () => move(-1), Enter: open, d: dismiss });

  if (isPending) return <div className="breathe mx-auto mt-24 h-[50vh] max-w-xl rounded-2xl bg-well" />;
  if (!pick)
    return (
      <p className="mx-auto mt-32 max-w-md text-center font-display text-3xl italic text-hint">
        Wandering needs somewhere to go. Save a few more things and come back.
      </p>
    );

  const item = pick.item;
  const meta = item.meta as { quote?: string; attribution?: string; colors?: string[] };

  return (
    <div className="flex min-h-[calc(100dvh-10rem)] flex-col items-center justify-center py-10">
      <AnimatePresence mode="wait">
        <motion.button
          key={item.id}
          type="button"
          onClick={open}
          initial={{ opacity: 0, y: 24, filter: "blur(6px)" }}
          animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
          exit={{ opacity: 0, y: -16, filter: "blur(6px)" }}
          transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
          className="group w-full max-w-xl text-left"
          aria-label={`Open ${item.title ?? "item"}`}
        >
          <div className="overflow-hidden rounded-[18px] bg-card shadow-[var(--shadow-hover)] transition-transform duration-500 group-hover:-translate-y-1">
            {item.lead_image ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={item.lead_thumb ?? item.lead_image} alt="" className="max-h-[52vh] w-full object-cover" />
            ) : item.type === "palette" && meta.colors ? (
              <div className="flex h-72">
                {meta.colors.map((c) => (
                  <span key={c} className="flex-1" style={{ background: c }} />
                ))}
              </div>
            ) : (
              <p className="px-10 py-14 font-display text-[34px] leading-[1.15]">
                {item.type === "quote" ? `“${meta.quote ?? item.summary}”` : item.summary ?? item.title}
              </p>
            )}
          </div>
          <div className="mt-6 px-1 text-center">
            {item.lead_image && <p className="font-display text-[28px] leading-tight">{item.title}</p>}
            <p className="mt-2 text-[13px] text-hint">{item.site_name ?? hostOf(item.url) ?? item.type}</p>
            <p className="mt-5 font-display text-lg italic text-muted">{pick.reason}</p>
          </div>
        </motion.button>
      </AnimatePresence>

      <div className="mt-10 flex items-center gap-2 text-[13px]">
        <button type="button" onClick={() => move(-1)} disabled={index === 0} className="rounded-full px-4 py-2 text-muted hover:bg-card hover:text-ink disabled:opacity-30">
          Back
        </button>
        <button type="button" onClick={dismiss} className="rounded-full px-4 py-2 text-muted hover:bg-card hover:text-ink">
          Not now
        </button>
        <button type="button" onClick={() => move(1)} disabled={index >= items.length - 1} className="rounded-full bg-ink px-5 py-2 font-medium text-canvas hover:opacity-90 disabled:opacity-30">
          Next
        </button>
      </div>
      <p className="mt-4 text-[12px] text-hint">
        {index + 1} of {items.length}
      </p>
    </div>
  );
}
