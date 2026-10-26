"use client";

import { useRouter } from "next/navigation";
import { type KeyboardEvent, type ReactNode, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { Item } from "@/lib/api";
import { Card, type CardProps, estimateHeight } from "./Card";

type Entry = { item: Item; reason?: string; highlight?: string | null };
type Props = {
  entries: Entry[];
  /** A card-shaped element placed first, e.g. the inline note composer. */
  lead?: ReactNode;
  leadHeight?: number;
  minColumnWidth?: number;
  gap?: number;
  onEndReached?: () => void;
} & Pick<CardProps, "onDelete" | "onRetry" | "onDismiss" | "onOpen">;

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useLayoutEffect(() => {
    if (!ref.current) return;
    const observer = new ResizeObserver(([entry]) => entry && setWidth(entry.contentRect.width));
    observer.observe(ref.current);
    setWidth(ref.current.getBoundingClientRect().width);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

/**
 * Newest-first masonry. Items go to the shortest column by estimated height, so reading
 * order stays left-to-right, top-to-bottom (CSS columns would read top-to-bottom per column).
 */
export function Masonry({ entries, lead, leadHeight = 190, minColumnWidth = 236, gap = 26, onEndReached, ...actions }: Props) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const router = useRouter();
  const count = width ? Math.max(width < 640 ? 2 : 1, Math.floor((width + gap) / (minColumnWidth + gap))) : 0;
  const mobile = width > 0 && width < 640;
  const colWidth = count ? (width - gap * (count - 1)) / count : 0;

  const hasLead = !!lead;
  const columns = useMemo(() => {
    const cols: { entry: Entry; index: number }[][] = Array.from({ length: count }, () => []);
    const heights = new Array<number>(count).fill(0);
    if (hasLead && count) heights[0] = leadHeight + gap;
    entries.forEach((entry, index) => {
      const shortest = heights.indexOf(Math.min(...heights));
      cols[shortest]?.push({ entry, index });
      heights[shortest] = (heights[shortest] ?? 0) + estimateHeight(entry.item, colWidth, !!entry.reason) + gap;
    });
    return cols;
  }, [entries, count, colWidth, gap, hasLead, leadHeight]);

  // Where each item sits, for arrow-key navigation.
  const position = useMemo(() => {
    const map = new Map<number, [number, number]>();
    columns.forEach((col, c) => col.forEach(({ index }, r) => map.set(index, [c, r])));
    return map;
  }, [columns]);

  const [focused, setFocused] = useState(0);
  const focusIndex = useCallback((index: number) => {
    const id = entries[index]?.item.id;
    const el = id ? ref.current?.querySelector<HTMLElement>(`[data-card-id="${id}"] a`) : null;
    el?.focus();
    el?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [entries, ref]);

  const onKeyDown = useCallback(
    (index: number) => (e: KeyboardEvent<HTMLElement>) => {
      const [c, r] = position.get(index) ?? [0, 0];
      let target: number | undefined;
      if (e.key === "ArrowRight") target = index + 1;
      else if (e.key === "ArrowLeft") target = index - 1;
      else if (e.key === "ArrowDown") target = columns[c]?.[r + 1]?.index;
      else if (e.key === "ArrowUp") target = columns[c]?.[r - 1]?.index;
      else if (e.key === "Enter") {
        e.preventDefault();
        router.push(`/item/${entries[index]?.item.id}`);
        return;
      } else return;
      e.preventDefault();
      if (target !== undefined && target >= 0 && target < entries.length) focusIndex(target);
    },
    [position, columns, entries, focusIndex, router],
  );

  // Infinite scroll: load more when the shortest column's end comes into view.
  const sentinel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!onEndReached || !sentinel.current) return;
    const io = new IntersectionObserver(([e]) => e?.isIntersecting && onEndReached(), { rootMargin: "1200px" });
    io.observe(sentinel.current);
    return () => io.disconnect();
  }, [onEndReached]);

  return (
    <div ref={ref} className="w-full">
      <div className="flex items-start" style={{ gap: mobile ? 12 : gap }} role="feed" aria-busy={false}>
        {columns.map((col, c) => (
          <div key={c} className="flex min-w-0 flex-1 flex-col" style={{ gap: mobile ? 16 : gap }}>
            {c === 0 && lead}
            {col.map(({ entry, index }) => (
              <Card
                key={entry.item.id}
                item={entry.item}
                reason={entry.reason}
                highlight={entry.highlight}
                tabIndex={index === focused ? 0 : -1}
                onFocusCard={() => setFocused(index)}
                onKeyDown={onKeyDown(index)}
                {...actions}
              />
            ))}
          </div>
        ))}
      </div>
      <div ref={sentinel} aria-hidden className="h-px" />
    </div>
  );
}
