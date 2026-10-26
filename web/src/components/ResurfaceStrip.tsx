"use client";

import { useQueryClient } from "@tanstack/react-query";
import type { Item } from "@/lib/api";
import { keys, recordEvent, useResurface } from "@/lib/queries";
import { Card } from "./Card";

/** Three things from the past, re-scored on each visit, each saying why it came back. */
export function ResurfaceStrip({ onOpen, onDelete }: { onOpen: (item: Item) => void; onDelete: (item: Item) => void }) {
  const { data } = useResurface("home");
  const qc = useQueryClient();
  const items = data?.items ?? [];
  if (!items.length) return null;

  const dismiss = (item: Item) => {
    recordEvent(item.id, "dismiss", { surface: "home" });
    qc.setQueryData(keys.resurface("home"), { ...data, items: items.filter((p) => p.item.id !== item.id) });
  };

  return (
    <section aria-labelledby="past-heading" className="mb-14">
      <h2 id="past-heading" className="label mb-4 text-[17px] text-muted">
        Remember these?
      </h2>
      <div className="grid grid-cols-2 gap-6 md:grid-cols-3 xl:max-w-[60%]">
        {items.map((p) => (
          <Card
            key={p.item.id}
            item={p.item}
            reason={p.reason}
            onOpen={(item) => {
              recordEvent(item.id, "open", { from: "resurface", surface: "home" });
              onOpen(item);
            }}
            onDismiss={dismiss}
            onDelete={onDelete}
          />
        ))}
      </div>
    </section>
  );
}
