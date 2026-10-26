"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useDebounced } from "@/lib/useDebounced";
import { useSearch } from "@/lib/queries";
import { SearchBar } from "./SearchBar";
import { Modal } from "./ui/modal";

/** Search from anywhere: ⌘K opens it, results update as you type, Enter opens the item. */
export function CommandK({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const [q, setQ] = useState("");
  const debounced = useDebounced(q, 120);
  const { data } = useSearch(debounced);
  const [active, setActive] = useState(0);
  const router = useRouter();
  const hits = data?.hits.slice(0, 8) ?? [];

  useEffect(() => setActive(0), [debounced]);

  const go = (id: string) => {
    onOpenChange(false);
    router.push(`/item/${id}`);
  };

  return (
    <Modal open={open} onOpenChange={onOpenChange} title="Search" hideTitle top className="max-w-2xl">
      <div
        className="p-3"
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") (e.preventDefault(), setActive((a) => Math.min(a + 1, hits.length - 1)));
          if (e.key === "ArrowUp") (e.preventDefault(), setActive((a) => Math.max(a - 1, 0)));
          if (e.key === "Enter" && hits[active]) (e.preventDefault(), go(hits[active].item.id));
        }}
      >
        <SearchBar value={q} onChange={setQ} chips={data?.chips} />
        <ul role="listbox" aria-label="Results" className="mt-2">
          {hits.map((hit, i) => (
            <li key={hit.item.id} role="option" aria-selected={i === active}>
              <button
                type="button"
                onMouseEnter={() => setActive(i)}
                onClick={() => go(hit.item.id)}
                className={`flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left ${i === active ? "bg-sunken" : ""}`}
              >
                {hit.item.lead_image ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={hit.item.lead_image} alt="" className="h-10 w-10 shrink-0 rounded-md object-cover" />
                ) : (
                  <span className="grid h-10 w-10 shrink-0 place-items-center rounded-md bg-sunken text-xs text-muted">{hit.item.type}</span>
                )}
                <span className="min-w-0">
                  <span className="block truncate font-serif text-[15px] font-medium">{hit.item.title ?? hit.item.summary ?? hit.item.url}</span>
                  <span className="block truncate text-xs text-muted">
                    {hit.item.type} · {hit.item.domain ?? "note"}
                  </span>
                </span>
              </button>
            </li>
          ))}
          {debounced && data && hits.length === 0 && <li className="px-3 py-6 text-center text-sm text-muted">Nothing yet. Try fewer words.</li>}
        </ul>
      </div>
    </Modal>
  );
}
