"use client";

import { Menu } from "@ark-ui/react/menu";
import { Portal } from "@ark-ui/react/portal";
import { motion } from "motion/react";
import Link from "next/link";
import { type KeyboardEvent, memo } from "react";
import type { Item } from "@/lib/api";
import { duration, hostOf, price, timeAgo } from "@/lib/format";
import { ClockIcon, ExternalIcon, MoreIcon, PlayIcon, RetryIcon, TrashIcon } from "./ui/icons";

type Meta = {
  author?: string;
  handle?: string;
  avatar?: string;
  posts?: number;
  tweet_text?: string;
  channel?: string;
  duration?: number;
  pages?: number;
  price?: string;
  currency?: string;
  colors?: string[];
  quote?: string;
  attribution?: string;
  description?: string;
  partial?: boolean;
};

export type CardProps = {
  item: Item;
  reason?: string;
  highlight?: string | null;
  tabIndex?: number;
  onFocusCard?: () => void;
  onKeyDown?: (e: KeyboardEvent<HTMLElement>) => void;
  onDelete?: (item: Item) => void;
  onRetry?: (item: Item) => void;
  onDismiss?: (item: Item) => void;
};

/** Rough rendered height per unit width, so the masonry can balance columns before layout. */
export function estimateHeight(item: Item, width: number): number {
  const meta = item.meta as Meta;
  const text = (s?: string | null, perLine = 42, lineH = 22) => Math.ceil((s?.length ?? 0) / perLine) * lineH;
  const image = item.lead_image ? width / Math.max(item.lead_aspect ?? 1.6, 0.4) : 0;
  switch (item.type) {
    case "image":
      return image || 200;
    case "quote":
    case "note":
      return 60 + Math.min(text(meta.quote ?? item.summary ?? item.title, 30, 30), 360);
    case "palette":
      return 150;
    case "tweet":
      return 90 + text(meta.tweet_text, 40) + (item.lead_image ? image * 0.8 : 0);
    default:
      return 96 + image + text(item.title, 30, 26) + (item.summary ? 44 : 0);
  }
}

function Swatches({ colors, big }: { colors: string[]; big?: boolean }) {
  return (
    <div className={`flex overflow-hidden ${big ? "h-28 rounded-t-[var(--radius-card)]" : "h-2 rounded-full"}`}>
      {colors.map((c) => (
        <div key={c} className="flex-1" style={{ background: c }} />
      ))}
    </div>
  );
}

function Lead({ item, children }: { item: Item; children?: React.ReactNode }) {
  if (!item.lead_image) return null;
  return (
    <div className="relative overflow-hidden bg-sunken" style={{ aspectRatio: `${Math.max(item.lead_aspect ?? 1.6, 0.4)}` }}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={item.lead_image} alt="" loading="lazy" decoding="async" className="h-full w-full object-cover" />
      {children}
    </div>
  );
}

function Pending({ item }: { item: Item }) {
  return (
    <div className="space-y-3 p-4">
      <div className="shimmer h-28 rounded-lg" />
      <p className="truncate text-sm text-muted">{item.title ?? item.url ?? "Saving…"}</p>
      <div className="shimmer h-3 w-2/3 rounded" />
    </div>
  );
}

function Body({ item, highlight }: { item: Item; highlight?: string | null }) {
  const meta = item.meta as Meta;
  const site = item.site_name ?? item.domain ?? hostOf(item.url);
  const caption = (
    <>
      {highlight ? (
        // Highlights come from Postgres ts_headline with only <mark> tags around matched words.
        <p className="mt-2 line-clamp-3 text-sm text-ink-soft" dangerouslySetInnerHTML={{ __html: sanitizeMarks(highlight) }} />
      ) : item.summary ? (
        <p className="mt-2 line-clamp-2 text-sm text-ink-soft">{item.summary}</p>
      ) : null}
    </>
  );

  switch (item.type) {
    case "image":
      return item.lead_image ? (
        <Lead item={item} />
      ) : (
        <div className="p-4">
          <p className="font-serif text-base font-semibold leading-snug sm:text-lg line-clamp-2">{item.title ?? "Image"}</p>
          <p className="mt-1 truncate text-sm text-muted">{site || item.url}</p>
        </div>
      );
    case "quote":
      return (
        <figure className="p-4 sm:p-5">
          <blockquote className="font-serif text-lg leading-snug text-ink sm:text-xl">“{meta.quote ?? item.summary ?? item.title}”</blockquote>
          {(meta.attribution || site) && (
            <figcaption className="mt-3 text-sm text-muted">— {meta.attribution ?? site}</figcaption>
          )}
        </figure>
      );
    case "note":
      return (
        <div className="p-4 sm:p-5">
          <p className="whitespace-pre-line font-serif text-base leading-snug text-ink line-clamp-[12] sm:text-lg">
            {item.summary ?? item.title}
          </p>
        </div>
      );
    case "palette": {
      const colors = meta.colors ?? item.palette?.map((p) => String(p.hex)) ?? [];
      return (
        <div>
          <Swatches colors={colors} big />
          <div className="flex flex-wrap gap-x-3 gap-y-1 p-3 font-mono text-xs text-muted">
            {colors.map((c) => (
              <span key={c}>{c}</span>
            ))}
          </div>
        </div>
      );
    }
    case "tweet":
      return (
        <div className="p-4">
          <div className="flex items-center gap-2">
            {meta.avatar ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={meta.avatar} alt="" className="h-8 w-8 rounded-full" />
            ) : (
              <div className="h-8 w-8 rounded-full bg-sunken" />
            )}
            <div className="min-w-0 text-sm leading-tight">
              <div className="truncate font-medium">{meta.author}</div>
              <div className="truncate text-muted">@{meta.handle}</div>
            </div>
          </div>
          <p className="mt-3 whitespace-pre-line text-[15px] leading-snug line-clamp-[10]">{meta.tweet_text ?? item.title}</p>
          {meta.posts && meta.posts > 1 ? <p className="mt-2 text-xs text-muted">Thread · {meta.posts} posts</p> : null}
          {item.lead_image ? (
            <div className="mt-3 overflow-hidden rounded-lg">
              <Lead item={item} />
            </div>
          ) : null}
        </div>
      );
    case "video":
    case "audio":
      return (
        <div>
          <Lead item={item}>
            <span className="absolute inset-0 grid place-items-center">
              <span className="grid h-11 w-11 place-items-center rounded-full bg-black/55 text-white backdrop-blur-sm">
                <PlayIcon size={20} />
              </span>
            </span>
            {meta.duration ? (
              <span className="absolute bottom-2 right-2 rounded bg-black/70 px-1.5 py-0.5 font-mono text-xs text-white">
                {duration(meta.duration)}
              </span>
            ) : null}
          </Lead>
          <div className="p-4">
            <h3 className="font-serif text-base font-semibold leading-snug sm:text-lg line-clamp-3">{item.title}</h3>
            <p className="mt-1 text-sm text-muted">{meta.channel ?? site}</p>
            {caption}
          </div>
        </div>
      );
    case "pdf":
      return (
        <div>
          {item.lead_image ? (
            <div className="bg-sunken px-8 pt-6">
              <div className="overflow-hidden rounded-t-md shadow-[var(--shadow-card)]">
                <Lead item={item} />
              </div>
            </div>
          ) : null}
          <div className="p-4">
            <h3 className="font-serif text-base font-semibold leading-snug sm:text-lg line-clamp-3">{item.title}</h3>
            <p className="mt-1 text-sm text-muted">
              PDF{meta.pages ? ` · ${meta.pages} pages` : ""}
              {meta.author ? ` · ${meta.author}` : ""}
            </p>
            {caption}
          </div>
        </div>
      );
    case "product":
      return (
        <div>
          <Lead item={item} />
          <div className="p-4">
            <h3 className="font-serif text-base font-semibold leading-snug sm:text-lg line-clamp-2">{item.title}</h3>
            <p className="mt-1 flex items-center justify-between text-sm text-muted">
              <span>{site}</span>
              {meta.price ? <span className="font-medium text-ink">{price(meta.price, meta.currency)}</span> : null}
            </p>
          </div>
        </div>
      );
    default:
      return (
        <div>
          <Lead item={item} />
          <div className="p-4">
            <h3 className="font-serif text-base font-semibold leading-snug sm:text-lg line-clamp-4">{item.title ?? item.url}</h3>
            <p className="mt-1 text-sm text-muted">{site}</p>
            {caption}
          </div>
        </div>
      );
  }
}

/** Only <mark> survives; everything else in a highlight is escaped. */
function sanitizeMarks(html: string): string {
  return html
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/&lt;mark&gt;/g, "<mark>")
    .replace(/&lt;\/mark&gt;/g, "</mark>");
}

function CardMenu({ item, onDelete, onRetry, onDismiss }: Pick<CardProps, "item" | "onDelete" | "onRetry" | "onDismiss">) {
  return (
    <Menu.Root
      positioning={{ placement: "bottom-end" }}
      onSelect={({ value }) => {
        if (value === "open" && item.url) window.open(item.url, "_blank", "noopener");
        if (value === "copy" && item.url) void navigator.clipboard.writeText(item.url);
        if (value === "delete") onDelete?.(item);
        if (value === "retry") onRetry?.(item);
        if (value === "dismiss") onDismiss?.(item);
      }}
    >
      <Menu.Trigger
        aria-label="Item actions"
        className="grid h-8 w-8 place-items-center rounded-full bg-surface/90 text-ink-soft opacity-0 shadow-[var(--shadow-card)] backdrop-blur transition-opacity group-hover:opacity-100 group-focus-within:opacity-100 data-[state=open]:opacity-100"
        onClick={(e) => e.preventDefault()}
      >
        <MoreIcon />
      </Menu.Trigger>
      <Portal>
        <Menu.Positioner>
          <Menu.Content className="z-50 min-w-44 rounded-xl border border-line bg-surface p-1 text-sm shadow-[var(--shadow-lift)] outline-none">
            {item.url && (
              <Menu.Item value="open" className="flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 data-[highlighted]:bg-sunken">
                <ExternalIcon size={16} /> Open original
              </Menu.Item>
            )}
            {item.url && (
              <Menu.Item value="copy" className="flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 data-[highlighted]:bg-sunken">
                Copy link
              </Menu.Item>
            )}
            {item.status === "failed" && (
              <Menu.Item value="retry" className="flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 data-[highlighted]:bg-sunken">
                <RetryIcon size={16} /> Retry
              </Menu.Item>
            )}
            {onDismiss && (
              <Menu.Item value="dismiss" className="flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 data-[highlighted]:bg-sunken">
                Not now
              </Menu.Item>
            )}
            <Menu.Item value="delete" className="flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-danger data-[highlighted]:bg-sunken">
              <TrashIcon size={16} /> Delete
            </Menu.Item>
          </Menu.Content>
        </Menu.Positioner>
      </Portal>
    </Menu.Root>
  );
}

export const Card = memo(function Card({ item, reason, highlight, tabIndex = 0, onFocusCard, onKeyDown, ...actions }: CardProps) {
  const pending = item.status === "pending" && !item.title && !item.lead_image && item.type !== "note" && item.type !== "quote";
  const label = item.title ?? item.summary ?? item.url ?? item.type;
  return (
    <motion.article
      layout="position"
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: "easeOut" }}
      className="group relative"
      data-card-id={item.id}
    >
      <Link
        href={`/item/${item.id}`}
        tabIndex={tabIndex}
        onFocus={onFocusCard}
        onKeyDown={onKeyDown}
        aria-label={label}
        className="block overflow-hidden rounded-[var(--radius-card)] border border-line bg-surface shadow-[var(--shadow-card)] transition-shadow hover:shadow-[var(--shadow-lift)] focus-visible:shadow-[var(--shadow-lift)]"
      >
        {pending ? <Pending item={item} /> : <Body item={item} highlight={highlight} />}
        {item.note && item.type !== "note" ? (
          <p className="mx-4 mb-4 border-l-2 border-accent pl-3 text-sm italic text-ink-soft line-clamp-3">{item.note}</p>
        ) : null}
        {item.status === "failed" ? (
          <p className="flex items-center gap-1.5 border-t border-line px-4 py-2 text-xs text-danger">
            Couldn&apos;t finish saving. Use ··· to retry.
          </p>
        ) : null}
        {reason ? (
          <p className="flex items-center gap-1.5 border-t border-line bg-sunken/60 px-4 py-2 text-xs text-muted">
            <ClockIcon size={13} /> {reason}
          </p>
        ) : null}
      </Link>
      <div className="absolute right-2 top-2">
        <CardMenu item={item} {...actions} />
      </div>
      {!reason && item.type !== "image" && (
        <time className="sr-only" dateTime={item.saved_at}>
          Saved {timeAgo(item.saved_at)}
        </time>
      )}
    </motion.article>
  );
});
