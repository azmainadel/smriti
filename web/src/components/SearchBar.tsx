"use client";

import { forwardRef } from "react";
import type { Chip } from "@/lib/api";
import { CloseIcon } from "./ui/icons";

/** Remove a parsed filter by cutting its span out of the query text. */
export function removeChip(q: string, chip: Chip): string {
  return `${q.slice(0, chip.start)} ${q.slice(chip.end)}`.replace(/\s{2,}/g, " ").trim();
}

const SUGGESTIONS = ["articles", "images", "videos", "notes", "quotes", "products", "pdfs", "palettes", "from last month", "blue"];

type Props = {
  value: string;
  onChange: (q: string) => void;
  chips?: Chip[];
  status?: string;
  size?: "hero" | "compact";
};

export const SearchBar = forwardRef<HTMLInputElement, Props>(function SearchBar({ value, onChange, chips = [], status, size = "hero" }, ref) {
  const hero = size === "hero";
  return (
    <div>
      <div className="flex items-center gap-3">
        <input
          ref={ref}
          type="search"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              onChange("");
              e.currentTarget.blur();
            }
          }}
          placeholder="What do you remember?"
          aria-label="Search your library"
          autoComplete="off"
          spellCheck={false}
          className={`min-w-0 flex-1 bg-transparent font-display tracking-[-0.015em] text-ink outline-none placeholder:italic placeholder:text-hint/70 ${hero ? "text-[40px] leading-tight sm:text-[64px]" : "text-[28px]"}`}
        />
        {value && (
          <button type="button" aria-label="Clear search" onClick={() => onChange("")} className="grid h-9 w-9 shrink-0 place-items-center rounded-full text-hint hover:bg-card hover:text-ink">
            <CloseIcon size={18} />
          </button>
        )}
      </div>
      <div className={`mt-3 flex min-h-8 items-center gap-1.5 ${value ? "flex-wrap" : "no-scrollbar -mx-1 overflow-x-auto sm:flex-wrap"}`}>
        {value ? (
          <>
            {chips.map((chip) => (
              <button
                key={`${chip.kind}-${chip.start}`}
                type="button"
                onClick={() => onChange(removeChip(value, chip))}
                aria-label={`Remove filter ${chip.label}`}
                className="group inline-flex items-center gap-1.5 rounded-full bg-accent-wash py-1 pl-2.5 pr-2 text-[12px] font-medium text-accent-ink transition-colors hover:bg-accent hover:text-white"
              >
                {chip.kind === "color" && <span className="h-2.5 w-2.5 rounded-full ring-1 ring-black/10" style={{ background: chip.value }} />}
                {chip.label}
                <CloseIcon size={11} className="opacity-50 group-hover:opacity-100" />
              </button>
            ))}
            {status && <span className="ml-1 text-[12px] text-hint">{status}</span>}
          </>
        ) : (
          SUGGESTIONS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => onChange(s)}
              className="shrink-0 rounded-full px-2.5 py-1 text-[12px] text-hint transition-colors hover:bg-card hover:text-ink"
            >
              {s}
            </button>
          ))
        )}
      </div>
    </div>
  );
});
