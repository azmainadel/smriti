"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { type Item, api, call } from "./api";
import { API_URL } from "./config";
import { keys, removeFromFeed, upsertInFeed } from "./queries";

type StatusEvent = { id: string; status: string; step?: string; error?: string };

// Steps after which a card has something new to show.
const VISIBLE_STEPS = new Set(["saved", "extract", "enrich", "index", "edited", "retry"]);

/** Keep cards live: the API pushes item status changes over server-sent events. */
export function useLiveUpdates(token: string | null | undefined) {
  const qc = useQueryClient();
  useEffect(() => {
    if (!token) return;
    const source = new EventSource(`${API_URL}/stream?token=${encodeURIComponent(token)}`);
    const pending = new Map<string, ReturnType<typeof setTimeout>>();

    const refresh = (id: string) => {
      // Coalesce bursts of events for one item into a single fetch.
      clearTimeout(pending.get(id));
      pending.set(
        id,
        setTimeout(async () => {
          pending.delete(id);
          try {
            const card = await call<Item>(api.GET("/items/{item_id}/card", { params: { path: { item_id: id } } }));
            upsertInFeed(qc, card);
            if (card.status !== "pending") {
              qc.invalidateQueries({ queryKey: keys.item(id) });
              qc.invalidateQueries({ queryKey: ["search"] });
            }
          } catch {
            /* deleted meanwhile */
          }
        }, 250),
      );
    };

    source.addEventListener("item", (e) => {
      const event = JSON.parse((e as MessageEvent<string>).data) as StatusEvent;
      if (event.status === "deleted") return removeFromFeed(qc, event.id);
      if (event.status !== "pending" || VISIBLE_STEPS.has(event.step ?? "")) refresh(event.id);
    });
    return () => {
      source.close();
      pending.forEach(clearTimeout);
    };
  }, [token, qc]);
}
