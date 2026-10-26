"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { EmptyState } from "@/components/EmptyState";
import { Masonry } from "@/components/Masonry";
import { NoteCard } from "@/components/NoteCard";
import { ResurfaceStrip } from "@/components/ResurfaceStrip";
import { SearchBar, removeChip } from "@/components/SearchBar";
import { useShell } from "@/components/Shell";
import { toaster } from "@/components/ui/toast";
import type { Item } from "@/lib/api";
import { useDeleteItem, useFeed, useRetry, useSearch } from "@/lib/queries";
import { useHotkeys } from "@/lib/shortcuts";
import { useDebounced } from "@/lib/useDebounced";

function Home() {
  const params = useSearchParams();
  const router = useRouter();
  const [q, setQ] = useState(params.get("q") ?? "");
  const debounced = useDebounced(q, 160);
  const searchRef = useRef<HTMLInputElement>(null);
  const { openComposer, openItem, setSequence } = useShell();

  useHotkeys({ "/": () => searchRef.current?.focus() });
  useEffect(() => {
    const focus = () => {
      searchRef.current?.focus();
      window.scrollTo({ top: 0, behavior: "smooth" });
    };
    window.addEventListener("smriti:focus-search", focus);
    if (params.get("focus")) focus();
    return () => window.removeEventListener("smriti:focus-search", focus);
  }, [params]);

  // The query lives in the URL so back/forward and reloads keep it; an open item stays open.
  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    if (debounced) p.set("q", debounced);
    else p.delete("q");
    p.delete("focus");
    const qs = p.toString();
    router.replace(qs ? `/?${qs}` : "/", { scroll: false });
  }, [debounced, router]);

  const feed = useFeed();
  const search = useSearch(debounced);
  const del = useDeleteItem();
  const retry = useRetry();

  const onDelete = useCallback(
    (item: Item) => del.mutate(item.id, { onSuccess: () => toaster.create({ title: "Deleted", duration: 1800 }) }),
    [del],
  );
  const onRetry = useCallback((item: Item) => retry.mutate(item.id), [retry]);
  const onOpen = useCallback((item: Item) => openItem(item.id), [openItem]);
  const loadMore = useCallback(() => {
    if (feed.hasNextPage && !feed.isFetchingNextPage) void feed.fetchNextPage();
  }, [feed]);

  const searching = debounced.trim().length > 0;
  const feedItems = useMemo(() => feed.data?.pages.flatMap((p) => p.items).map((item) => ({ item })) ?? [], [feed.data]);
  const hits = useMemo(() => search.data?.hits.map((h) => ({ item: h.item, highlight: h.highlight })) ?? [], [search.data]);
  const entries = searching ? hits : feedItems;

  useEffect(() => {
    setSequence(entries.map((e) => e.item.id));
  }, [entries, setSequence]);

  if (feed.isSuccess && !feedItems.length && !searching) return <EmptyState onCompose={openComposer} />;

  const status = search.data
    ? `${search.data.hits.length} ${search.data.hits.length === 1 ? "thing" : "things"} · ${search.data.took_ms} ms`
    : undefined;

  return (
    <div>
      <div className="pb-10 pt-6 sm:pb-14 sm:pt-12">
        <SearchBar ref={searchRef} value={q} onChange={setQ} chips={search.data?.chips} status={searching ? status : undefined} />
      </div>

      {searching ? (
        <>
          {search.data?.fallback && (
            <p className="mb-8 font-display text-xl italic text-muted">
              Nothing matched every filter, so here is what comes closest.{" "}
              {search.data.chips[0] && (
                <button type="button" className="not-italic text-accent-ink underline decoration-accent underline-offset-4" onClick={() => setQ(removeChip(q, search.data.chips[0]!))}>
                  Drop “{search.data.chips[0].label}”
                </button>
              )}
            </p>
          )}
          {search.isSuccess && !hits.length ? (
            <p className="py-24 text-center font-display text-3xl italic text-hint">Nothing comes to mind.</p>
          ) : (
            <Masonry entries={hits} onOpen={onOpen} onDelete={onDelete} onRetry={onRetry} />
          )}
        </>
      ) : (
        <>
          <ResurfaceStrip onOpen={onOpen} onDelete={onDelete} />
          {feed.isPending ? (
            <div className="grid grid-cols-2 gap-6 md:grid-cols-4 xl:grid-cols-6">
              {Array.from({ length: 12 }, (_, i) => (
                <div key={i} className="breathe rounded-[var(--radius-card)] bg-well" style={{ height: 140 + ((i * 53) % 160) }} />
              ))}
            </div>
          ) : (
            <Masonry entries={feedItems} lead={<NoteCard />} onOpen={onOpen} onDelete={onDelete} onRetry={onRetry} onEndReached={loadMore} />
          )}
          {feed.isFetchingNextPage && <p className="breathe py-10 text-center text-[13px] text-hint">Remembering more…</p>}
        </>
      )}
    </div>
  );
}

export default function HomePage() {
  return (
    <Suspense>
      <Home />
    </Suspense>
  );
}
