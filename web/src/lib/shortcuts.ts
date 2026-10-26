"use client";

import { useEffect, useRef } from "react";

export const SHORTCUTS: { keys: string; action: string }[] = [
  { keys: "⌘K / Ctrl K", action: "Search from anywhere" },
  { keys: "/", action: "Focus the search box" },
  { keys: "N", action: "New note" },
  { keys: "← → ↑ ↓", action: "Move between cards" },
  { keys: "Enter", action: "Open the focused card" },
  { keys: "J / K", action: "Next / previous item in the reader" },
  { keys: "E", action: "Edit the note in the reader" },
  { keys: "O", action: "Open the original page" },
  { keys: "Esc", action: "Back to the grid" },
  { keys: "?", action: "Show shortcuts" },
];

function typing(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  return !!el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName));
}

/** Single-key shortcuts that stay quiet while the user types in a field. */
export function useHotkeys(map: Record<string, (e: KeyboardEvent) => void>, enabled = true) {
  const ref = useRef(map);
  ref.current = map;
  useEffect(() => {
    if (!enabled) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey) {
        const handler = ref.current[`mod+${e.key.toLowerCase()}`];
        if (handler) {
          e.preventDefault();
          handler(e);
        }
        return;
      }
      // Ark dialogs and open menus own their keys (Escape closes them, it should not also navigate).
      if (e.altKey || typing(e.target) || document.querySelector('[data-scope="dialog"][role="dialog"], [data-scope="menu"][data-state="open"]')) return;
      const handler = ref.current[e.key];
      if (handler) {
        e.preventDefault();
        handler(e);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [enabled]);
}
