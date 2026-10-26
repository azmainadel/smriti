"use client";

import { motion } from "motion/react";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import type { ItemDetail } from "@/lib/api";
import { duration, hostOf, price, timeAgo } from "@/lib/format";
import { recordEvent, useDeleteItem, useItem, useRetry, useUpdateItem } from "@/lib/queries";
import { sanitize } from "@/lib/sanitize";
import { useHotkeys } from "@/lib/shortcuts";
import { ArchiveIcon, ArrowLeftIcon, CloseIcon, DownloadIcon, ExternalIcon, TrashIcon } from "./ui/icons";
import { toaster } from "./ui/toast";

type Meta = {
  author?: string;
  channel?: string;
  duration?: number;
  pages?: number;
  price?: string;
  currency?: string;
  colors?: string[];
  quote?: string;
  attribution?: string;
  video_id?: string;
  partial?: boolean;
  words?: number;
  tweet_text?: string;
};

type Props = {
  id: string;
  onClose: () => void;
  onNavigate?: (direction: 1 | -1) => void;
  onOpenItem?: (id: string) => void;
};

function Section({ label, children }: { label: string; children: ReactNode }) {
  return (
    <section className="border-t border-hairline px-7 py-6">
      <h3 className="label mb-3 text-muted">{label}</h3>
      {children}
    </section>
  );
}

function Notes({ item }: { item: ItemDetail }) {
  const [value, setValue] = useState(item.note ?? "");
  const update = useUpdateItem(item.id);
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    setValue(item.note ?? "");
  }, [item.note]);
  useHotkeys({ e: () => ref.current?.focus() });
  const save = () => {
    if (value.trim() !== (item.note ?? "")) update.mutate({ note: value });
  };
  return (
    <textarea
      ref={ref}
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onBlur={save}
      onKeyDown={(e) => {
        if (e.key === "Escape") (e.stopPropagation(), ref.current?.blur());
      }}
      rows={Math.min(10, Math.max(3, value.split("\n").length + 1))}
      placeholder="What did this make you think of?"
      aria-label="Note"
      className="w-full resize-none rounded-xl bg-well px-4 py-3 text-[14px] leading-relaxed text-ink outline-none placeholder:text-hint focus:bg-accent-wash"
    />
  );
}

function Tags({ item }: { item: ItemDetail }) {
  const update = useUpdateItem(item.id);
  const [draft, setDraft] = useState("");
  const set = (tags: string[]) => update.mutate({ tags });
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {item.tags.map((t) => (
        <span key={t} className="group/tag inline-flex items-center gap-1 rounded-full bg-accent-wash py-1 pl-3 pr-2 text-[12px] font-medium text-accent-ink">
          {t.replace(/-/g, " ")}
          <button
            type="button"
            aria-label={`Remove ${t}`}
            onClick={() => set(item.tags.filter((x) => x !== t))}
            className="opacity-40 hover:opacity-100"
          >
            <CloseIcon size={11} />
          </button>
        </span>
      ))}
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          e.stopPropagation();
          if (e.key === "Enter" && draft.trim()) {
            set([...item.tags, draft.trim()]);
            setDraft("");
          }
        }}
        placeholder="+ Add tag"
        aria-label="Add tag"
        className="w-24 rounded-full px-2 py-1 text-[12px] outline-none placeholder:text-hint focus:bg-well"
      />
    </div>
  );
}

function Stage({ item }: { item: ItemDetail }) {
  const meta = item.meta as Meta;
  const html = useMemo(() => (item.content_html ? sanitize(item.content_html) : ""), [item.content_html]);
  const site = item.site_name ?? item.domain ?? hostOf(item.url);

  if (item.type === "image") {
    return (
      <div className="flex min-h-full items-center justify-center p-6 sm:p-12">
        {item.assets[0] && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={item.assets[0].url} alt={item.assets[0].caption ?? ""} className="max-h-[86vh] max-w-full rounded-xl shadow-[var(--shadow-panel)]" />
        )}
      </div>
    );
  }

  if (item.type === "quote") {
    return (
      <div className="flex min-h-full items-center justify-center p-8 sm:p-16">
        <figure className="max-w-3xl">
          <span aria-hidden className="block font-display text-8xl leading-none text-accent">“</span>
          <blockquote className="-mt-6 font-display text-4xl leading-[1.18] sm:text-5xl">{meta.quote ?? item.summary}</blockquote>
          {meta.attribution && <figcaption className="label mt-8 text-muted">{meta.attribution}</figcaption>}
        </figure>
      </div>
    );
  }

  if (item.type === "palette" && meta.colors) {
    return (
      <div className="flex min-h-full items-center justify-center p-8 sm:p-16">
        <div className="flex h-[60vh] w-full max-w-4xl overflow-hidden rounded-2xl shadow-[var(--shadow-panel)]">
          {meta.colors.map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => void navigator.clipboard.writeText(c).then(() => toaster.create({ title: `Copied ${c}`, duration: 1400 }))}
              className="group/sw flex flex-1 items-end justify-center pb-6 transition-[flex] duration-500 ease-[var(--ease-out)] hover:flex-[1.6]"
              style={{ background: c }}
            >
              <span className="font-mono text-sm uppercase text-white mix-blend-difference">{c}</span>
            </button>
          ))}
        </div>
      </div>
    );
  }

  if (item.type === "note") {
    return (
      <div className="mx-auto max-w-2xl px-6 py-16 sm:py-24">
        <p className="whitespace-pre-line font-serif text-2xl leading-relaxed">{item.summary ?? item.title}</p>
      </div>
    );
  }

  return (
    <article className="mx-auto max-w-[44rem] px-6 pb-24 pt-14 sm:px-10 sm:pt-20">
      <p className="label text-hint">
        {[site, meta.author ?? meta.channel, meta.duration && duration(meta.duration), meta.pages && `${meta.pages} pages`].filter(Boolean).join("  ·  ")}
      </p>
      <h1 className="mt-4 font-display text-[40px] leading-[1.08] tracking-[-0.01em] sm:text-[52px]">{item.title ?? item.url}</h1>

      {item.type === "video" && meta.video_id ? (
        <div className="mt-10 aspect-video overflow-hidden rounded-2xl bg-black shadow-[var(--shadow-panel)]">
          <iframe
            title={item.title ?? "Video"}
            src={`https://www.youtube-nocookie.com/embed/${meta.video_id}`}
            className="h-full w-full"
            allow="encrypted-media; picture-in-picture"
            allowFullScreen
          />
        </div>
      ) : item.type === "product" ? (
        <div className="mt-10 flex flex-col items-start gap-6 sm:flex-row sm:items-center">
          {item.lead_image && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={item.lead_image} alt="" className="h-64 w-64 rounded-2xl bg-white object-contain p-6 shadow-[var(--shadow-card)]" />
          )}
          {meta.price && <p className="font-display text-5xl">{price(meta.price, meta.currency)}</p>}
        </div>
      ) : item.lead_image && item.type !== "tweet" ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={item.lead_image} alt="" className="mt-10 w-full rounded-2xl shadow-[var(--shadow-card)]" />
      ) : null}

      {item.type === "tweet" &&
        item.assets.map((a) => (
          // eslint-disable-next-line @next/next/no-img-element
          <img key={a.id} src={a.url} alt={a.caption ?? ""} className="mt-6 w-full rounded-2xl" />
        ))}

      {item.status === "pending" && !html ? (
        <div className="breathe mt-12 space-y-3">
          <div className="h-3 rounded bg-well" />
          <div className="h-3 w-11/12 rounded bg-well" />
          <div className="h-3 w-4/6 rounded bg-well" />
        </div>
      ) : html ? (
        <div className="prose-reader mt-12" dangerouslySetInnerHTML={{ __html: html }} />
      ) : null}

      {meta.partial && (
        <p className="mt-10 rounded-xl bg-well px-5 py-4 text-[14px] text-muted">
          Only part of this page was readable, likely a paywall. Saving it with the browser extension captures what you see.
        </p>
      )}
    </article>
  );
}

function IconButton({ label, onClick, href, children, danger }: { label: string; onClick?: () => void; href?: string | null; children: ReactNode; danger?: boolean }) {
  const cls = `grid h-10 w-10 place-items-center rounded-full bg-well transition-colors ${danger ? "text-danger hover:bg-danger hover:text-white" : "text-ink-2 hover:bg-ink hover:text-canvas"}`;
  if (href) {
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" aria-label={label} title={label} className={cls}>
        {children}
      </a>
    );
  }
  return (
    <button type="button" aria-label={label} title={label} onClick={onClick} className={cls}>
      {children}
    </button>
  );
}

function Panel({ item, onClose, onOpenItem }: { item: ItemDetail; onClose: () => void; onOpenItem?: (id: string) => void }) {
  const del = useDeleteItem();
  const retry = useRetry();
  const meta = item.meta as Meta;
  const remove = () =>
    del.mutate(item.id, {
      onSuccess: () => {
        toaster.create({ title: "Deleted", duration: 1800 });
        onClose();
      },
    });

  return (
    <aside className="flex w-full flex-col bg-card lg:h-full lg:w-[380px] lg:shrink-0 lg:overflow-y-auto lg:rounded-l-[22px] lg:shadow-[var(--shadow-panel)]">
      <div className="px-7 pb-6 pt-7">
        <p className="font-display text-[26px] leading-[1.15]">{item.title ?? (item.type === "note" ? "Note" : item.url)}</p>
        {item.url && (
          <a href={item.url} target="_blank" rel="noopener noreferrer" className="mt-2 inline-flex items-center gap-1.5 text-[13px] text-muted hover:text-accent-ink">
            {hostOf(item.url)} <ExternalIcon size={12} />
          </a>
        )}
        {item.status === "failed" && (
          <button type="button" onClick={() => retry.mutate(item.id)} className="mt-3 block text-[13px] font-medium text-danger hover:underline">
            Reading failed. Try again
          </button>
        )}
      </div>

      {(item.summary || item.key_points.length > 0) && !["note", "quote"].includes(item.type) && (
        <Section label="In short">
          {item.summary && <p className="text-[14px] leading-relaxed text-ink-2">{item.summary}</p>}
          {item.key_points.length > 0 && (
            <ul className="mt-3 space-y-2">
              {item.key_points.map((p) => (
                <li key={p} className="relative pl-4 text-[13px] leading-relaxed text-muted before:absolute before:left-0 before:top-[0.6em] before:h-1 before:w-1 before:rounded-full before:bg-accent">
                  {p}
                </li>
              ))}
            </ul>
          )}
        </Section>
      )}

      <Section label="Tags">
        <Tags item={item} />
      </Section>

      <Section label="Your note">
        <Notes item={item} />
      </Section>

      {item.related.length > 0 && (
        <Section label="Connected">
          <ul className="-mx-2 space-y-0.5">
            {item.related.map((r) => (
              <li key={r.item.id}>
                <button
                  type="button"
                  onClick={() => {
                    recordEvent(r.item.id, "open", { from: "related", source: item.id });
                    onOpenItem?.(r.item.id);
                  }}
                  className="flex w-full items-center gap-3 rounded-xl px-2 py-2 text-left hover:bg-well"
                >
                  {r.item.lead_image ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={r.item.lead_image} alt="" className="h-11 w-11 shrink-0 rounded-lg object-cover" />
                  ) : (
                    <span className="grid h-11 w-11 shrink-0 place-items-center rounded-lg bg-well font-display text-lg text-hint">
                      {(r.item.title ?? r.item.summary ?? "?").slice(0, 1)}
                    </span>
                  )}
                  <span className="min-w-0">
                    <span className="line-clamp-2 text-[13px] font-medium leading-snug">{r.item.title ?? r.item.summary}</span>
                    <span className="block truncate text-[12px] text-hint">{r.reason}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </Section>
      )}

      <Section label="About">
        <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1.5 text-[13px]">
          <dt className="text-hint">Saved</dt>
          <dd className="text-ink-2">{timeAgo(item.saved_at)}</dd>
          <dt className="text-hint">Type</dt>
          <dd className="capitalize text-ink-2">{item.type}</dd>
          {meta.words ? (
            <>
              <dt className="text-hint">Length</dt>
              <dd className="text-ink-2">{Math.max(1, Math.round(meta.words / 230))} min read</dd>
            </>
          ) : null}
          {item.open_count > 0 && (
            <>
              <dt className="text-hint">Opened</dt>
              <dd className="text-ink-2">{item.open_count}×</dd>
            </>
          )}
        </dl>
        {item.entities.length > 0 && <p className="mt-4 text-[12px] leading-relaxed text-hint">Mentions {item.entities.map((e) => e.name).join(", ")}</p>}
      </Section>

      <div className="mt-auto flex items-center gap-2 border-t border-hairline px-7 py-5">
        {item.url && (
          <IconButton label="Open original" href={item.url}>
            <ExternalIcon size={16} />
          </IconButton>
        )}
        {item.archive_url && (
          <IconButton label="Archived copy" href={item.archive_url}>
            <ArchiveIcon size={16} />
          </IconButton>
        )}
        {item.original_url && (
          <IconButton label="Download file" href={item.original_url}>
            <DownloadIcon size={16} />
          </IconButton>
        )}
        <span className="flex-1" />
        <IconButton label="Delete" onClick={remove} danger>
          <TrashIcon size={16} />
        </IconButton>
      </div>
    </aside>
  );
}

/** The item, full screen: content on the stage, everything about it in the panel. */
export function ItemView({ id, onClose, onNavigate, onOpenItem }: Props) {
  const { data: item, isError } = useItem(id);
  const stage = useRef<HTMLDivElement>(null);

  useEffect(() => {
    recordEvent(id, "open", { from: "item" });
  }, [id]);
  useEffect(() => {
    stage.current?.scrollTo({ top: 0 });
  }, [id]);
  useHotkeys({
    Escape: onClose,
    j: () => onNavigate?.(1),
    k: () => onNavigate?.(-1),
    ArrowRight: () => onNavigate?.(1),
    ArrowLeft: () => onNavigate?.(-1),
    o: () => item?.url && window.open(item.url, "_blank", "noopener"),
  });

  return (
    <motion.div
      role="dialog"
      aria-modal="true"
      aria-label={item?.title ?? "Item"}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.25 }}
      className="fixed inset-0 z-40 bg-canvas/85 backdrop-blur-2xl"
    >
      <div className="flex h-full flex-col overflow-y-auto lg:flex-row lg:overflow-hidden">
        <div ref={stage} className="relative lg:min-h-0 lg:flex-1 lg:overflow-y-auto">
          <div className="sticky top-0 z-10 flex items-center justify-between p-4">
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="grid h-10 w-10 place-items-center rounded-full bg-card text-ink-2 shadow-[var(--shadow-card)] hover:text-ink"
            >
              <CloseIcon size={18} />
            </button>
            {onNavigate && (
              <div className="flex gap-2">
                <button type="button" aria-label="Previous" onClick={() => onNavigate(-1)} className="grid h-10 w-10 place-items-center rounded-full bg-card text-ink-2 shadow-[var(--shadow-card)] hover:text-ink">
                  <ArrowLeftIcon size={16} />
                </button>
                <button type="button" aria-label="Next" onClick={() => onNavigate(1)} className="grid h-10 w-10 rotate-180 place-items-center rounded-full bg-card text-ink-2 shadow-[var(--shadow-card)] hover:text-ink">
                  <ArrowLeftIcon size={16} />
                </button>
              </div>
            )}
          </div>
          <motion.div key={id} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }} className="-mt-[72px] min-h-full">
            {isError ? (
              <p className="pt-40 text-center text-muted">This item is gone.</p>
            ) : item ? (
              <Stage item={item} />
            ) : (
              <div className="breathe mx-auto mt-40 h-80 max-w-2xl rounded-2xl bg-well" />
            )}
          </motion.div>
        </div>
        {item && (
          <motion.div
            initial={{ x: 40, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
            className="lg:h-full"
          >
            <Panel item={item} onClose={onClose} onOpenItem={onOpenItem} />
          </motion.div>
        )}
      </div>
    </motion.div>
  );
}
