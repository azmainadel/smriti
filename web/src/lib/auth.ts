"use client";

import { useSyncExternalStore } from "react";

const KEY = "smriti.token";
const listeners = new Set<() => void>();

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(KEY);
}

export function setToken(token: string | null): void {
  if (token) window.localStorage.setItem(KEY, token);
  else window.localStorage.removeItem(KEY);
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

/** `undefined` while rendering on the server, so the UI can wait instead of flashing login. */
export function useToken(): string | null | undefined {
  return useSyncExternalStore(subscribe, getToken, () => undefined);
}
