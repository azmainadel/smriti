"use client";

import {
  type InfiniteData,
  type QueryClient,
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useCallback } from "react";
import { toaster } from "@/components/ui/toast";
import { type Item, type ItemCreate, type ItemDetail, type ItemPage, type SearchOut, api, call, uploadFile } from "./api";

export const keys = {
  feed: ["feed"] as const,
  item: (id: string) => ["item", id] as const,
  search: (q: string) => ["search", q] as const,
  resurface: (surface: string) => ["resurface", surface] as const,
  status: ["status"] as const,
  models: ["models"] as const,
  tokens: ["tokens"] as const,
  digest: ["digest-settings"] as const,
};

export function useFeed() {
  return useInfiniteQuery({
    queryKey: keys.feed,
    queryFn: ({ pageParam }) =>
      call<ItemPage>(api.GET("/items", { params: { query: { limit: 40, cursor: pageParam ?? undefined } } })),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  });
}

export function useSearch(q: string) {
  return useQuery({
    queryKey: keys.search(q),
    queryFn: ({ signal }) => call(api.GET("/search", { params: { query: { q, limit: 60 } }, signal })),
    enabled: q.trim().length > 0,
    placeholderData: keepPreviousData,
    staleTime: 10_000,
  });
}

export function useItem(id: string) {
  return useQuery({ queryKey: keys.item(id), queryFn: () => call(api.GET("/items/{item_id}", { params: { path: { item_id: id } } })) });
}

export function useResurface(surface: "home" | "digest" | "on-this-day" | "serendipity") {
  return useQuery({
    queryKey: keys.resurface(surface),
    queryFn: () => call(api.GET("/resurface", { params: { query: { surface } } })),
    staleTime: 5 * 60_000,
  });
}

/** Put a fresh or updated item at the right place in the cached feed. */
export function upsertInFeed(qc: QueryClient, item: Item) {
  qc.setQueryData<InfiniteData<ItemPage>>(keys.feed, (data) => {
    if (!data) return data;
    const exists = data.pages.some((p) => p.items.some((i) => i.id === item.id));
    const pages = data.pages.map((p) => ({ ...p, items: p.items.map((i) => (i.id === item.id ? item : i)) }));
    if (!exists && pages[0]) pages[0] = { ...pages[0], items: [item, ...pages[0].items] };
    return { ...data, pages };
  });
}

export function removeFromFeed(qc: QueryClient, id: string) {
  qc.setQueryData<InfiniteData<ItemPage>>(keys.feed, (data) =>
    data ? { ...data, pages: data.pages.map((p) => ({ ...p, items: p.items.filter((i) => i.id !== id) })) } : data,
  );
}

export function useSave() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: ItemCreate | File) =>
      input instanceof File ? uploadFile(input) : call<Item>(api.POST("/items", { body: input })),
    onSuccess: (item) => upsertInFeed(qc, item),
  });
}

export function useUpdateItem(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: { title?: string | null; note?: string | null; tags?: string[] | null }) =>
      call(api.PATCH("/items/{item_id}", { params: { path: { item_id: id } }, body: patch })),
    onSuccess: (item) => {
      upsertInFeed(qc, item);
      qc.setQueryData<ItemDetail>(keys.item(id), (d) => (d ? { ...d, ...item } : d));
      qc.invalidateQueries({ queryKey: ["search"] });
    },
  });
}

/**
 * Delete with a grace period: the item leaves the page at once, and the server delete runs
 * only after the undo window closes. Undo puts the feed back as it was. Closing the page inside
 * the window keeps the item: browsers drop cross-origin DELETEs sent while a page unloads.
 */
export function useDeleteItem() {
  const qc = useQueryClient();
  return useCallback(
    (id: string) => {
      const before = [...qc.getQueriesData({ queryKey: keys.feed }), ...qc.getQueriesData({ queryKey: ["search"] })];
      const restore = () => before.forEach(([key, data]) => qc.setQueryData(key, data));
      removeFromFeed(qc, id);
      qc.setQueriesData<SearchOut>({ queryKey: ["search"] }, (data) =>
        data ? { ...data, hits: data.hits.filter((h) => h.item.id !== id) } : data,
      );
      let undone = false;
      const commit = () => {
        if (undone) return;
        void call(api.DELETE("/items/{item_id}", { params: { path: { item_id: id } } }))
          .then(() => {
            qc.invalidateQueries({ queryKey: ["search"] });
            qc.invalidateQueries({ queryKey: ["resurface"] });
          })
          .catch((err) => {
            restore();
            toaster.create({ title: "Couldn't delete", description: String(err), type: "error" });
          });
      };
      toaster.create({
        title: "Deleted",
        duration: 5000,
        action: {
          label: "Undo",
          onClick: () => {
            undone = true;
            restore();
          },
        },
        onStatusChange: ({ status }) => status === "unmounted" && commit(),
      });
    },
    [qc],
  );
}

export function useRetry() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => call(api.POST("/items/{item_id}/retry", { params: { path: { item_id: id } } })),
    onSuccess: (item) => upsertInFeed(qc, item),
  });
}

export function recordEvent(item_id: string, kind: "open" | "dismiss" | "more_like_this", context: Record<string, unknown> = {}) {
  // Fire and forget: events never block the UI.
  void api.POST("/events", { body: { item_id, kind, context } });
}
