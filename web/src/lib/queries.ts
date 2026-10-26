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
import { type Item, type ItemCreate, type ItemDetail, type ItemPage, api, call, uploadFile } from "./api";

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

export function useDeleteItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => call(api.DELETE("/items/{item_id}", { params: { path: { item_id: id } } })),
    onSuccess: (_, id) => {
      removeFromFeed(qc, id);
      qc.invalidateQueries({ queryKey: ["search"] });
      qc.invalidateQueries({ queryKey: ["resurface"] });
    },
  });
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
