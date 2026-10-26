"use client";

import type { InfiniteData } from "@tanstack/react-query";
import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { Card } from "@/components/Card";
import { Button } from "@/components/ui/button";
import { ArrowLeftIcon, ExternalIcon, RetryIcon, TrashIcon } from "@/components/ui/icons";
import { toaster } from "@/components/ui/toast";
import type { ItemDetail, ItemPage } from "@/lib/api";
import { duration, price, timeAgo } from "@/lib/format";
import { keys, recordEvent, useDeleteItem, useItem, useRetry, useUpdateItem } from "@/lib/queries";
import { sanitize } from "@/lib/sanitize";
import { useHotkeys } from "@/lib/shortcuts";

function NoteEditor({ item, editing, setEditing }: { item: ItemDetail; editing: boolean; setEditing: (v: boolean) => void }) {
  const [value, setValue] = useState(item.note ?? "");
  const update = useUpdateItem(item.id);
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => setValue(item.note ?? ""), [item.note]);
  useEffect(() => {
    if (editing) ref.current?.focus();
  }, [editing]);

  const save = () => {
    setEditing(false);
    if ((item.note ?? "") !== value.trim()) update.mutate({ note: value });
  };

  if (!editing) {
    return (
      <button
        type="button"
        onClick={() => setEditing(true)}
        className="w-full rounded-xl border border-dashed border-line px-4 py-3 text-left text-[15px] hover:border-accent"
      >
        {item.note ? <span className="whitespace-pre-line italic text-ink-soft">{item.note}</span> : <span className="text-muted">Add a note… (E)</span>}
      </button>
    );
  }
  return (
    <textarea
      ref={ref}
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onBlur={save}
      onKeyDown={(e) => {
        if (e.key === "Escape" || (e.key === "Enter" && (e.metaKey || e.ctrlKey))) (e.preventDefault(), save());
      }}
      rows={4}
      aria-label="Note"
      className="w-full rounded-xl border border-accent bg-surface px-4 py-3 text-[15px] outline-none"
    />
  );
}

function TagEditor({ item }: { item: ItemDetail }) {
  const update = useUpdateItem(item.id);
  const [draft, setDraft] = useState("");
  const set = (tags: string[]) => update.mutate({ tags });
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {item.tags.map((t) => (
        <span key={t} className="group inline-flex items-center gap-1 rounded-full bg-sunken px-2.5 py-0.5 text-xs text-ink-soft">
          <Link href={`/?q=${encodeURIComponent(`#${t}`)}`} className="hover:underline">
            #{t}
          </Link>
          <button type="button" aria-label={`Remove tag ${t}`} onClick={() => set(item.tags.filter((x) => x !== t))} className="text-muted hover:text-danger">
            ×
          </button>
        </span>
      ))}
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && draft.trim()) {
            set([...item.tags, draft.trim()]);
            setDraft("");
          }
        }}
        placeholder="+ tag"
        aria-label="Add tag"
        className="w-20 bg-transparent text-xs outline-none placeholder:text-muted"
      />
    </div>
  );
}

function Media({ item }: { item: ItemDetail }) {
  const meta = item.meta as { video_id?: string; duration?: number; price?: string; currency?: string; colors?: string[] };
  if (item.type === "video" && meta.video_id) {
    return (
      <div className="aspect-video overflow-hidden rounded-xl bg-black">
        <iframe
          title={item.title ?? "Video"}
          src={`https://www.youtube-nocookie.com/embed/${meta.video_id}`}
          className="h-full w-full"
          allow="encrypted-media; picture-in-picture"
          allowFullScreen
          loading="lazy"
        />
      </div>
    );
  }
  if (item.type === "image" || item.type === "tweet") {
    return (
      <div className="space-y-3">
        {item.assets.map((a) => (
          // eslint-disable-next-line @next/next/no-img-element
          <img key={a.id} src={a.url} alt={a.caption ?? ""} className="mx-auto max-h-[80vh] rounded-xl" />
        ))}
      </div>
    );
  }
  if (item.type === "palette" && meta.colors) {
    return (
      <div className="flex h-48 overflow-hidden rounded-xl">
        {meta.colors.map((c) => (
          <button
            key={c}
            type="button"
            onClick={() => void navigator.clipboard.writeText(c).then(() => toaster.create({ title: `Copied ${c}`, duration: 1500 }))}
            className="flex flex-1 items-end p-2 font-mono text-xs text-white mix-blend-difference"
            style={{ background: c }}
          >
            {c}
          </button>
        ))}
      </div>
    );
  }
  if (item.type === "product") {
    return (
      <div className="flex items-center gap-6">
        {item.lead_image && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={item.lead_image} alt="" className="h-48 w-48 rounded-xl object-cover" />
        )}
        {meta.price && <p className="text-2xl font-medium">{price(meta.price, meta.currency)}</p>}
      </div>
    );
  }
  return null;
}

function Reader() {
  const { id } = useParams<{ id: string }>();
  const { data: item, isError } = useItem(id);
  const router = useRouter();
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const del = useDeleteItem();
  const retry = useRetry();
  const content = useMemo(() => (item?.content_html ? sanitize(item.content_html) : ""), [item?.content_html]);

  useEffect(() => recordEvent(id, "open", { from: "reader" }), [id]);

  // j/k walk the feed in grid order.
  const neighbours = () => {
    const feed = qc.getQueryData<InfiniteData<ItemPage>>(keys.feed);
    const ids = feed?.pages.flatMap((p) => p.items.map((i) => i.id)) ?? [];
    const i = ids.indexOf(id);
    return { next: i >= 0 ? ids[i + 1] : undefined, prev: i > 0 ? ids[i - 1] : undefined };
  };
  useHotkeys({
    j: () => {
      const { next } = neighbours();
      if (next) router.push(`/item/${next}`);
    },
    k: () => {
      const { prev } = neighbours();
      if (prev) router.push(`/item/${prev}`);
    },
    e: () => setEditing(true),
    o: () => item?.url && window.open(item.url, "_blank", "noopener"),
    Escape: () => router.push("/"),
  });

  if (isError) return <p className="py-20 text-center text-muted">This item is gone.</p>;
  if (!item) return <div className="mx-auto mt-10 max-w-3xl space-y-4"><div className="shimmer h-10 rounded" /><div className="shimmer h-80 rounded-xl" /></div>;

  const meta = item.meta as { author?: string; channel?: string; duration?: number; pages?: number; published?: string; partial?: boolean; quote?: string; attribution?: string };
  const remove = () =>
    del.mutate(item.id, {
      onSuccess: () => {
        toaster.create({ title: "Deleted", duration: 2000 });
        router.push("/");
      },
    });

  return (
    <div className="mx-auto grid max-w-6xl gap-12 lg:grid-cols-[minmax(0,1fr)_300px]">
      <article className="min-w-0">
        <Link href="/" className="mb-6 inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink">
          <ArrowLeftIcon size={16} /> Library
        </Link>
        <header className="mb-8">
          <p className="mb-2 text-sm text-muted">
            {[item.site_name ?? item.domain, meta.author ?? meta.channel, meta.duration ? duration(meta.duration) : null, meta.pages ? `${meta.pages} pages` : null]
              .filter(Boolean)
              .join(" · ")}
          </p>
          {item.type === "quote" ? (
            <blockquote className="font-serif text-3xl leading-snug">“{meta.quote ?? item.summary}”{meta.attribution && <footer className="mt-3 text-lg text-muted">— {meta.attribution}</footer>}</blockquote>
          ) : (
            <h1 className="font-serif text-3xl font-semibold leading-tight sm:text-4xl">{item.title ?? item.url}</h1>
          )}
          <div className="mt-4 flex flex-wrap items-center gap-2">
            {item.url && (
              <a href={item.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-sm hover:bg-sunken">
                <ExternalIcon size={15} /> Original
              </a>
            )}
            {item.archive_url && (
              <a href={item.archive_url} target="_blank" rel="noopener noreferrer" className="rounded-lg border border-line px-3 py-1.5 text-sm hover:bg-sunken">
                Archived copy
              </a>
            )}
            {item.original_url && (
              <a href={item.original_url} target="_blank" rel="noopener noreferrer" className="rounded-lg border border-line px-3 py-1.5 text-sm hover:bg-sunken">
                File
              </a>
            )}
            {item.status === "failed" && (
              <Button onClick={() => retry.mutate(item.id)}>
                <RetryIcon size={15} /> Retry
              </Button>
            )}
            <Button variant="quiet" onClick={remove} aria-label="Delete item">
              <TrashIcon size={15} />
            </Button>
            <span className="ml-auto text-xs text-muted">Saved {timeAgo(item.saved_at)}</span>
          </div>
        </header>

        <div className="mb-8 space-y-4">
          <NoteEditor item={item} editing={editing} setEditing={setEditing} />
          <TagEditor item={item} />
        </div>

        {(item.summary || item.key_points.length > 0) && item.type !== "note" && item.type !== "quote" && (
          <section className="mb-10 rounded-2xl bg-sunken px-5 py-4" aria-label="Summary">
            {item.summary && <p className="text-[15px] text-ink-soft">{item.summary}</p>}
            {item.key_points.length > 0 && (
              <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-ink-soft">
                {item.key_points.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            )}
          </section>
        )}

        <div className="mb-10">
          <Media item={item} />
        </div>

        {item.status === "pending" && !content ? (
          <div className="space-y-3">
            <div className="shimmer h-4 w-full rounded" />
            <div className="shimmer h-4 w-5/6 rounded" />
            <div className="shimmer h-4 w-4/6 rounded" />
          </div>
        ) : content && item.type !== "quote" ? (
          <div className="prose-reader" dangerouslySetInnerHTML={{ __html: content }} />
        ) : null}
        {meta.partial && (
          <p className="mt-6 rounded-xl bg-sunken px-4 py-3 text-sm text-muted">
            Only part of this page could be read (paywall or cookie wall). Save it with the browser extension to capture what you see.
          </p>
        )}
      </article>

      <aside className="space-y-8 lg:pt-12" aria-label="Related">
        {item.related.length > 0 && (
          <section>
            <h2 className="mb-3 font-serif text-lg text-ink-soft">Related</h2>
            <div className="space-y-4">
              {item.related.map((r) => (
                <div key={r.item.id} onClickCapture={() => recordEvent(r.item.id, "open", { from: "related", source: item.id })}>
                  <Card item={r.item} reason={r.reason} />
                </div>
              ))}
            </div>
          </section>
        )}
        {item.entities.length > 0 && (
          <section>
            <h2 className="mb-2 text-sm font-medium text-muted">Mentions</h2>
            <div className="flex flex-wrap gap-1.5">
              {item.entities.map((e) => (
                <Link key={`${e.kind}-${e.name}`} href={`/?q=${encodeURIComponent(e.name)}`} className="rounded-full border border-line px-2.5 py-0.5 text-xs hover:bg-sunken">
                  {e.name}
                </Link>
              ))}
            </div>
          </section>
        )}
        {item.screenshot_url && (
          <section>
            <h2 className="mb-2 text-sm font-medium text-muted">Snapshot</h2>
            <a href={item.screenshot_url} target="_blank" rel="noopener noreferrer">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={item.screenshot_url} alt="Full-page screenshot" className="max-h-96 w-full rounded-lg border border-line object-cover object-top" />
            </a>
          </section>
        )}
        <details className="text-xs text-muted">
          <summary className="cursor-pointer">How this was processed</summary>
          <table className="mt-2 w-full">
            <tbody>
              {item.enrichments.map((e) => (
                <tr key={e.step} className="border-t border-line">
                  <td className="py-1 pr-2">{e.step} v{e.version}</td>
                  <td className="py-1 pr-2">{e.model ?? "-"}</td>
                  <td className="py-1 text-right">{e.ms} ms</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      </aside>
    </div>
  );
}

export default function ItemPage() {
  return <Reader />;
}
