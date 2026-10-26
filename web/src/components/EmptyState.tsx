"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { importFile } from "@/lib/api";
import { keys } from "@/lib/queries";
import { Button } from "./ui/button";
import { toaster } from "./ui/toast";

const SOURCES = [
  { name: "Browser bookmarks", hint: "Chrome, Firefox or Safari: export bookmarks as HTML", accept: ".html,.htm" },
  { name: "Pocket", hint: "getpocket.com/export gives an HTML or CSV file", accept: ".html,.htm,.csv" },
  { name: "Raindrop", hint: "Settings → Backups → export CSV", accept: ".csv" },
];

/** First launch: offer imports instead of a blank page. */
export function EmptyState({ onCompose }: { onCompose: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const qc = useQueryClient();

  const onFile = async (file: File) => {
    setBusy(true);
    try {
      const r = await importFile(file);
      toaster.create({ title: `Imported ${r.created} items`, description: r.skipped ? `${r.skipped} were already saved` : undefined, type: "success" });
      await qc.invalidateQueries({ queryKey: keys.feed });
    } catch (e) {
      toaster.create({ title: "Import failed", description: String(e), type: "error" });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl py-20 text-center">
      <h1 className="font-display text-5xl leading-[1.05] sm:text-6xl">A quiet place for everything you save</h1>
      <p className="mx-auto mt-5 max-w-md text-[15px] text-muted">
        Bring in what you already have. Smriti reads every page, so you can find it later by what it was about.
      </p>
      <div className="mt-10 grid gap-3 text-left sm:grid-cols-3">
        {SOURCES.map((s) => (
          <button
            key={s.name}
            type="button"
            disabled={busy}
            onClick={() => {
              if (input.current) {
                input.current.accept = s.accept;
                input.current.click();
              }
            }}
            className="rounded-[var(--radius-card)] bg-card p-5 text-left shadow-[var(--shadow-card)] transition-[transform,box-shadow] duration-300 hover:-translate-y-0.5 hover:shadow-[var(--shadow-hover)]"
          >
            <span className="block font-display text-xl">{s.name}</span>
            <span className="mt-1 block text-sm text-muted">{s.hint}</span>
          </button>
        ))}
      </div>
      <input ref={input} type="file" hidden onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])} />
      <p className="mt-10 text-muted">
        Or <Button variant="quiet" onClick={onCompose}>save your first link or note</Button>, drop a file anywhere, or install the browser extension.
      </p>
    </div>
  );
}
