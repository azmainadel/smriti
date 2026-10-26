"use client";

import { forwardRef } from "react";
import type { Chip } from "@/lib/api";
import { CloseIcon, SearchIcon } from "./ui/icons";

const CHIP_STYLE: Record<string, string> = {
  type: "bg-accent-soft text-accent",
  date: "bg-sunken text-ink-soft",
  source: "bg-sunken text-ink-soft",
  note: "bg-sunken text-ink-soft",
  tag: "bg-sunken text-ink-soft",
};

/** Remove a parsed filter by cutting its span out of the query text. */
export function removeChip(q: string, chip: Chip): string {
  return `${q.slice(0, chip.start)} ${q.slice(chip.end)}`.replace(/\s{2,}/g, " ").trim();
}

type Props = {
  value: string;
  onChange: (q: string) => void;
  chips?: Chip[];
  tookMs?: number;
  className?: string;
};

export const SearchBar = forwardRef<HTMLInputElement, Props>(function SearchBar({ value, onChange, chips = [], tookMs, className = "" }, ref) {
  return (
    <div className={className}>
      <label className="flex items-center gap-3 rounded-2xl border border-line bg-surface px-4 py-3 shadow-[var(--shadow-card)] focus-within:border-accent">
        <SearchIcon className="shrink-0 text-muted" />
        <input
          ref={ref}
          type="search"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => e.key === "Escape" && (e.currentTarget.blur(), onChange(""))}
          placeholder="Find anything… “that blue chart about retention”"
          aria-label="Search your library"
          className="min-w-0 flex-1 bg-transparent text-base outline-none placeholder:text-muted"
          autoComplete="off"
          spellCheck={false}
        />
        {value ? (
          <button type="button" aria-label="Clear search" onClick={() => onChange("")} className="text-muted hover:text-ink">
            <CloseIcon size={16} />
          </button>
        ) : (
          <kbd className="hidden rounded border border-line px-1.5 text-xs text-muted sm:block">/</kbd>
        )}
      </label>
      {chips.length > 0 && (
        <ul className="mt-2 flex flex-wrap items-center gap-2" aria-label="Filters from your query">
          {chips.map((chip) => (
            <li key={`${chip.kind}-${chip.start}`}>
              <button
                type="button"
                onClick={() => onChange(removeChip(value, chip))}
                className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ${CHIP_STYLE[chip.kind] ?? "bg-sunken"}`}
                aria-label={`Remove filter ${chip.label}`}
              >
                {chip.kind === "color" ? (
                  <span className="h-3 w-3 rounded-full border border-black/10" style={{ background: chip.value }} />
                ) : null}
                <span className="opacity-70">{chip.kind}</span> {chip.label}
                <CloseIcon size={12} />
              </button>
            </li>
          ))}
          {tookMs !== undefined && <li className="text-xs text-muted">{tookMs} ms</li>}
        </ul>
      )}
    </div>
  );
});
