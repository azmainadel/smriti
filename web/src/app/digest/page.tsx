"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import type { Item } from "@/lib/api";
import { keys, recordEvent, useResurface } from "@/lib/queries";
import { timeAgo } from "@/lib/format";

/** The weekly look back: 7 items, each with why it came back. */
export default function DigestPage() {
  const { data, isPending } = useResurface("digest");
  const { data: onThisDay } = useResurface("on-this-day");
  const qc = useQueryClient();

  const dismiss = (item: Item) => {
    recordEvent(item.id, "dismiss", { surface: "digest" });
    qc.setQueryData(keys.resurface("digest"), data && { ...data, items: data.items.filter((p) => p.item.id !== item.id) });
  };

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="font-serif text-4xl font-semibold">From your past</h1>
      <p className="mt-2 text-muted">Seven things worth another look this week.</p>
      {isPending && <div className="shimmer mt-10 h-64 rounded-xl" />}
      <ol className="mt-10 space-y-8">
        {data?.items.map((p, i) => (
          <li key={p.item.id} className="flex gap-5">
            <span className="w-6 shrink-0 pt-1 text-right font-serif text-xl text-muted">{i + 1}</span>
            <div className="min-w-0 flex-1">
              <Link
                href={`/item/${p.item.id}`}
                onClick={() => recordEvent(p.item.id, "open", { from: "resurface", surface: "digest" })}
                className="font-serif text-xl font-semibold leading-snug hover:underline"
              >
                {p.item.title ?? p.item.summary ?? p.item.url}
              </Link>
              <p className="mt-1 text-sm text-muted">
                {p.item.site_name ?? p.item.domain ?? p.item.type} · saved {timeAgo(p.item.saved_at)}
              </p>
              <p className="mt-2 text-[15px] text-ink-soft">{p.reason}</p>
              <div className="mt-2 flex gap-2">
                <Button variant="quiet" onClick={() => dismiss(p.item)}>
                  Not now
                </Button>
                <Link
                  href={`/item/${p.item.id}#related`}
                  onClick={() => recordEvent(p.item.id, "more_like_this", { surface: "digest" })}
                  className="rounded-lg px-3 py-1.5 text-sm font-medium text-muted hover:bg-sunken hover:text-ink"
                >
                  More like this
                </Link>
              </div>
            </div>
            {p.item.lead_image && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={p.item.lead_image} alt="" className="hidden h-20 w-28 shrink-0 rounded-lg object-cover sm:block" />
            )}
          </li>
        ))}
      </ol>
      {data && !data.items.length && <p className="mt-10 text-muted">Nothing yet. Items come back once they are a few days old.</p>}

      {onThisDay && onThisDay.items.length > 0 && (
        <section className="mt-16">
          <h2 className="font-serif text-2xl">On this day</h2>
          <ul className="mt-4 space-y-3">
            {onThisDay.items.map((p) => (
              <li key={p.item.id}>
                <Link href={`/item/${p.item.id}`} className="font-serif text-lg hover:underline">
                  {p.item.title ?? p.item.url}
                </Link>
                <span className="ml-2 text-sm text-muted">{p.reason}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
