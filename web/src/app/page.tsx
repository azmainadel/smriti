"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { EmptyState } from "@/components/EmptyState";
import { Masonry } from "@/components/Masonry";
import { ResurfaceStrip } from "@/components/ResurfaceStrip";
import { SearchBar, removeChip } from "@/components/SearchBar";
import { useShell } from "@/components/Shell";
import { toaster } from "@/components/ui/toast";
import type { Item } from "@/lib/api";
import { useShortcutFocus } from "@/lib/useShortcutFocus";
import { useDebounced } from "@/lib/useDebounced";
import { useDeleteItem, useFeed, useRetry, useSearch } from "@/lib/queries";

function Home() {
  const params = useSearchParams();
  const router = useRouter();
  const [q, setQ] = useState(params.get("q") ?? "");
  const debounced = useDebounced(q, 150);
  const searchRef = useRef<HTMLInputElement>(null);
  const { openComposer } = useShell();
  useShortcutFocus(searchRef);

  // Keep the query in the URL so back/forward and reloads keep the search.
  useEffect(() => {
    const url = debounced ? `/?q=${encodeURIComponent(debounced)}` : "/";
    router.replace(url, { scroll: false });
  }, [debounced, router]);

  const feed = useFeed();
  const search = useSearch(debounced);
  const del = useDeleteItem();
  const retry = useRetry();

  const onDelete = useCallback(
    (item: Item) =>
      del.mutate(item.id, {
        onSuccess: () => toaster.create({ title: "Deleted", description: item.title ?? undefined, duration: 2500 }),
      }),
    [del],
  );
  const onRetry = useCallback((item: Item) => retry.mutate(item.id), [retry]);
  const loadMore = useCallback(() => {
    if (feed.hasNextPage && !feed.isFetchingNextPage) void feed.fetchNextPage();
  }, [feed]);

  const searching = debounced.trim().length > 0;
  const feedItems = useMemo(() => feed.data?.pages.flatMap((p) => p.items).map((item) => ({ item })) ?? [], [feed.data]);
  const hits = useMemo(() => search.data?.hits.map((h) => ({ item: h.item, highlight: h.highlight })) ?? [], [search.data]);

  if (feed.isSuccess && !feedItems.length && !searching) return <EmptyState onCompose={openComposer} />;

  return (
    <div>
      <div className="mx-auto mb-8 max-w-2xl">
        <SearchBar ref={searchRef} value={q} onChange={setQ} chips={searching ? search.data?.chips : []} tookMs={searching ? search.data?.took_ms : undefined} />
      </div>

      {searching ? (
        <>
          {search.data?.fallback && (
            <div className="mx-auto mb-6 max-w-2xl rounded-xl bg-sunken px-4 py-3 text-sm text-ink-soft">
              Nothing matched every filter. Here are the closest matches without them.
              {search.data.chips[0] && (
                <button type="button" className="ml-2 font-medium text-accent hover:underline" onClick={() => setQ(removeChip(q, search.data.chips[0]!))}>
                  Drop “{search.data.chips[0].label}”
                </button>
              )}
            </div>
          )}
          {search.isSuccess && !hits.length ? (
            <p className="py-20 text-center text-muted">No matches. Try fewer or different words.</p>
          ) : (
            <Masonry entries={hits} onDelete={onDelete} onRetry={onRetry} />
          )}
        </>
      ) : (
        <>
          <ResurfaceStrip onDelete={onDelete} />
          {feed.isPending ? (
            <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
              {Array.from({ length: 8 }, (_, i) => (
                <div key={i} className="shimmer h-56 rounded-[var(--radius-card)]" />
              ))}
            </div>
          ) : (
            <Masonry entries={feedItems} onDelete={onDelete} onRetry={onRetry} onEndReached={loadMore} />
          )}
          {feed.isFetchingNextPage && <p className="py-8 text-center text-sm text-muted">Loading…</p>}
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
