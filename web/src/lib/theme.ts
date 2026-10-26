"use client";

import { useCallback, useEffect, useState } from "react";

export type Theme = "light" | "dark" | "system";
const KEY = "smriti.theme";

function apply(theme: Theme) {
  const dark = theme === "dark" || (theme === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
}

/** Inline script for <head>: sets the theme before first paint, so there is no flash. */
export const themeScript = `(()=>{try{const t=localStorage.getItem("${KEY}")||"system";const d=t==="dark"||(t==="system"&&matchMedia("(prefers-color-scheme: dark)").matches);document.documentElement.dataset.theme=d?"dark":"light"}catch{}})()`;

export function useTheme(): [Theme, (t: Theme) => void] {
  const [theme, setTheme] = useState<Theme>("system");
  useEffect(() => {
    const stored = (localStorage.getItem(KEY) as Theme | null) ?? "system";
    setTheme(stored);
    const media = matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => apply((localStorage.getItem(KEY) as Theme | null) ?? "system");
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);
  const update = useCallback((t: Theme) => {
    localStorage.setItem(KEY, t);
    setTheme(t);
    apply(t);
  }, []);
  return [theme, update];
}
