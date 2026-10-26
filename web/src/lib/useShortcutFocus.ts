"use client";

import type { RefObject } from "react";
import { useHotkeys } from "./shortcuts";

/** "/" focuses the page's search box. */
export function useShortcutFocus(ref: RefObject<HTMLInputElement | null>) {
  useHotkeys({ "/": () => ref.current?.focus() });
}
