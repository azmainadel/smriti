"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { useShell } from "@/components/Shell";
import type { Item } from "@/lib/api";
import { hostOf, timeAgo } from "@/lib/format";
import { keys, recordEvent, useResurface } from "@/lib/queries";

const countWord = (n: number) => (n === 1 ? "One thing" : `${["Two", "Three", "Four", "Five", "Six", "Seven"][n - 2] ?? n} things`);

/** The weekly look back: seven things, each with why it came back. */
export default function DigestPage() {
  const { data, isPending } = useResurface("digest");
  const { data: onThisDay } = useResurface("on-this-day");
  const { openItem, setSequence } = useShell();
  const qc = useQueryClient();
  const items = data?.items ?? [];

  useEffect(() => {
    setSequence(items.map((p) => p.item.id));
  }, [items, setSequence]);

  const dismiss = (item: Item) => {
    recordEvent(item.id, "dismiss", { surface: "digest" });
    qc.setQueryData(keys.resurface("digest"), data && { ...data, items: items.filter((p) => p.item.id !== item.id) });
  };
  const open = (item: Item) => {
    recordEvent(item.id, "open", { from: "resurface", surface: "digest" });
    openItem(item.id);
  };

  const week = new Date().toLocaleDateString(undefined, { month: "long", day: "numeric" });

  return (
    <div className="mx-auto max-w-3xl pb-16 pt-10 sm:pt-16">
      <p className="label text-accent-ink">Week of {week}</p>
      <h1 className="mt-3 font-display text-5xl leading-[1.05] sm:text-6xl">Look back</h1>
      {items.length > 0 && (
        <p className="mt-4 max-w-md text-[15px] text-muted">
          {countWord(items.length)} worth another look, picked from what you are into now and what you have not opened in a while.
        </p>
      )}

      {isPending && <div className="breathe mt-14 h-72 rounded-2xl bg-well" />}

      <ol className="mt-14">
        {items.map((p, i) => (
          <li key={p.item.id} className="group grid grid-cols-[2.5rem_1fr_auto] gap-x-5 border-t border-hairline py-7">
            <span className="font-display text-3xl leading-none text-hint">{i + 1}</span>
            <div className="min-w-0">
              <button type="button" onClick={() => open(p.item)} className="text-left font-display text-[26px] leading-[1.15] decoration-accent underline-offset-4 hover:underline">
                {p.item.title ?? p.item.summary ?? p.item.url}
              </button>
              <p className="mt-1.5 text-[13px] text-hint">
                {p.item.site_name ?? p.item.domain ?? hostOf(p.item.url) ?? p.item.type} · saved {timeAgo(p.item.saved_at)}
              </p>
              <p className="mt-3 font-display text-lg italic text-muted">{p.reason}</p>
              <div className="mt-3 flex gap-1 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
                <button type="button" onClick={() => dismiss(p.item)} className="rounded-full px-3 py-1 text-[12px] text-muted hover:bg-card hover:text-ink">
                  Not now
                </button>
                <button
                  type="button"
                  onClick={() => {
                    recordEvent(p.item.id, "more_like_this", { surface: "digest" });
                    open(p.item);
                  }}
                  className="rounded-full px-3 py-1 text-[12px] text-muted hover:bg-card hover:text-ink"
                >
                  More like this
                </button>
              </div>
            </div>
            {p.item.lead_image ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={p.item.lead_thumb ?? p.item.lead_image} alt="" className="hidden h-24 w-32 rounded-xl object-cover shadow-[var(--shadow-card)] sm:block" />
            ) : (
              <span />
            )}
          </li>
        ))}
      </ol>
      {data && !items.length && <p className="mt-10 font-display text-2xl italic text-hint">Nothing yet. Things come back once they are a few days old.</p>}

      {onThisDay && onThisDay.items.length > 0 && (
        <section className="mt-20">
          <h2 className="label text-hint">On this day</h2>
          <ul className="mt-5 space-y-4">
            {onThisDay.items.map((p) => (
              <li key={p.item.id}>
                <button type="button" onClick={() => open(p.item)} className="text-left font-display text-2xl hover:underline">
                  {p.item.title ?? p.item.url}
                </button>
                <p className="text-[13px] text-hint">{p.reason}</p>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
