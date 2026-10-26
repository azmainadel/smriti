"use client";

import { useQueryClient } from "@tanstack/react-query";
import type { Item } from "@/lib/api";
import { keys, recordEvent, useResurface } from "@/lib/queries";
import { Card } from "./Card";

/** "From your past": three items re-scored on each visit, each with its reason. */
export function ResurfaceStrip({ onDelete }: { onDelete: (item: Item) => void }) {
  const { data } = useResurface("home");
  const qc = useQueryClient();
  const items = data?.items ?? [];
  if (!items.length) return null;

  const dismiss = (item: Item) => {
    recordEvent(item.id, "dismiss", { surface: "home" });
    qc.setQueryData(keys.resurface("home"), { ...data, items: items.filter((p) => p.item.id !== item.id) });
  };

  return (
    <section aria-labelledby="past-heading" className="mb-10">
      <h2 id="past-heading" className="mb-3 font-serif text-lg text-ink-soft">
        From your past
      </h2>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((p) => (
          <div key={p.item.id} onClickCapture={() => recordEvent(p.item.id, "open", { from: "resurface", surface: "home" })}>
            <Card item={p.item} reason={p.reason} onDismiss={dismiss} onDelete={onDelete} />
          </div>
        ))}
      </div>
    </section>
  );
}
