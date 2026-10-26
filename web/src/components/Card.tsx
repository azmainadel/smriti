"use client";

import { Menu } from "@ark-ui/react/menu";
import { Portal } from "@ark-ui/react/portal";
import { motion } from "motion/react";
import Link from "next/link";
import { type KeyboardEvent, type MouseEvent, memo } from "react";
import type { Item } from "@/lib/api";
import { duration, hostOf, price } from "@/lib/format";
import { MoreIcon } from "./ui/icons";

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
};

export type CardProps = {
  item: Item;
  reason?: string;
  highlight?: string | null;
  tabIndex?: number;
  onOpen?: (item: Item) => void;
  onFocusCard?: () => void;
  onKeyDown?: (e: KeyboardEvent<HTMLElement>) => void;
  onDelete?: (item: Item) => void;
  onRetry?: (item: Item) => void;
  onDismiss?: (item: Item) => void;
};

const CAPTIONED = new Set(["article", "link", "video", "audio", "pdf", "product"]);

/** Rendered height estimate, so the masonry can balance columns before layout. */
export function estimateHeight(item: Item, width: number, withReason = false): number {
  const meta = item.meta as Meta;
  const lines = (s: string | null | undefined, perLine: number, lineH: number, max: number) =>
    Math.min(Math.ceil((s?.length ?? 0) / perLine), max) * lineH;
  const image = item.lead_image ? width / Math.max(item.lead_aspect ?? 1.5, 0.45) : 0;
  const caption = CAPTIONED.has(item.type) && item.lead_image ? 52 : 0;
  const extra = (withReason ? 28 : 0) + caption + 20;
  switch (item.type) {
    case "image":
      return (image || 180) + extra;
    case "quote":
      return 70 + lines(meta.quote ?? item.summary, 28, 30, 8) + extra;
    case "note":
      return 40 + lines(item.summary ?? item.title, 34, 23, 10) + extra;
    case "palette":
      return 170 + extra;
    case "tweet":
      return 80 + lines(meta.tweet_text, 38, 22, 9) + (item.lead_image ? image * 0.85 : 0) + extra;
    default:
      return (image || 150 + lines(item.title, 22, 28, 4)) + extra;
  }
}

function Img({ src, aspect, contain }: { src: string; aspect?: number | null; contain?: boolean }) {
  return (
    <div className="relative w-full overflow-hidden" style={{ aspectRatio: `${Math.max(aspect ?? 1.5, 0.45)}` }}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={src}
        alt=""
        loading="lazy"
        decoding="async"
        draggable={false}
        className={`h-full w-full ${contain ? "object-contain p-6" : "object-cover"} transition-transform duration-700 ease-[var(--ease-out)] group-hover:scale-[1.015]`}
      />
    </div>
  );
}

/** Only <mark> from ts_headline survives; everything else is escaped. */
function marks(html: string): string {
  return html
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/&lt;mark&gt;/g, "<mark>")
    .replace(/&lt;\/mark&gt;/g, "</mark>");
}

function Tile({ item }: { item: Item }) {
  const meta = item.meta as Meta;
  const site = item.site_name ?? item.domain ?? hostOf(item.url);

  if (item.status === "pending" && !item.lead_image && !item.title && !["note", "quote", "palette"].includes(item.type)) {
    return (
      <div className="breathe flex aspect-[4/3] flex-col justify-end bg-well p-4">
        <span className="label text-hint">Reading</span>
        <span className="mt-2 truncate text-sm text-muted">{hostOf(item.url) || item.url}</span>
      </div>
    );
  }

  switch (item.type) {
    case "image":
      return item.lead_image ? (
        <Img src={item.lead_thumb ?? item.lead_image} aspect={item.lead_aspect} />
      ) : (
        <div className="flex aspect-[4/3] flex-col justify-end bg-well p-4">
          <span className="label text-hint">Image</span>
          <span className="mt-2 truncate text-sm text-muted">{item.title ?? hostOf(item.url)}</span>
        </div>
      );

    case "quote":
      return (
        <figure className="px-6 pb-6 pt-5">
          <span aria-hidden className="block font-display text-5xl leading-none text-accent">“</span>
          <blockquote className="-mt-3 font-display text-[22px] leading-[1.28] text-ink">{meta.quote ?? item.summary ?? item.title}</blockquote>
          {(meta.attribution || site) && <figcaption className="label mt-4 text-hint">{meta.attribution ?? site}</figcaption>}
        </figure>
      );

    case "note":
      return (
        <div className="ruled px-5 pb-[18px] pt-[14px]">
          <p className="line-clamp-[10] whitespace-pre-line font-serif text-[16px] leading-[26px] text-ink">{item.summary ?? item.title}</p>
        </div>
      );

    case "palette": {
      const colors = meta.colors ?? item.palette?.map((p) => String(p.hex)) ?? [];
      return (
        <div className="flex h-[170px]">
          {colors.map((c) => (
            <div key={c} className="flex flex-1 items-end justify-center pb-3" style={{ background: c }}>
              <span className="rotate-180 font-mono text-[10px] uppercase tracking-wider text-white/80 mix-blend-difference [writing-mode:vertical-rl]">
                {c.replace("#", "")}
              </span>
            </div>
          ))}
        </div>
      );
    }

    case "tweet":
      return (
        <div className="p-5">
          <div className="flex items-center gap-2.5">
            {meta.avatar ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={meta.avatar} alt="" className="h-7 w-7 rounded-full" />
            ) : (
              <span className="h-7 w-7 rounded-full bg-well" />
            )}
            <span className="min-w-0 truncate text-[13px] font-medium">{meta.author}</span>
            <span className="truncate text-[13px] text-hint">@{meta.handle}</span>
          </div>
          <p className="mt-3 line-clamp-[9] whitespace-pre-line text-[15px] leading-[1.5]">{meta.tweet_text ?? item.title}</p>
          {item.lead_image && (
            <div className="mt-3 overflow-hidden rounded-lg">
              <Img src={item.lead_thumb ?? item.lead_image} aspect={item.lead_aspect} />
            </div>
          )}
          {meta.posts && meta.posts > 1 ? <p className="label mt-3 text-hint">Thread · {meta.posts}</p> : null}
        </div>
      );

    case "video":
    case "audio":
      return item.lead_image ? (
        <div className="relative">
          <Img src={item.lead_thumb ?? item.lead_image} aspect={item.lead_aspect} />
          {meta.duration ? (
            <span className="absolute bottom-2.5 left-2.5 rounded-md bg-black/60 px-1.5 py-0.5 font-mono text-[11px] text-white backdrop-blur-sm">
              {duration(meta.duration)}
            </span>
          ) : null}
        </div>
      ) : (
        <TextTile kicker={item.type} title={item.title} site={meta.channel ?? site} />
      );

    case "pdf":
      return item.lead_image ? (
        <div className="bg-well px-9 pt-7">
          <div className="overflow-hidden rounded-t-[3px] bg-white shadow-[0_4px_18px_rgb(0_0_0/0.12)]">
            <Img src={item.lead_thumb ?? item.lead_image} aspect={item.lead_aspect} />
          </div>
        </div>
      ) : (
        <TextTile kicker="PDF" title={item.title} site={site} />
      );

    case "product":
      return item.lead_image ? (
        <div className="relative bg-white">
          <Img src={item.lead_thumb ?? item.lead_image} aspect={1} contain />
          {meta.price && (
            <span className="absolute left-3 top-3 rounded-full bg-ink px-2.5 py-1 text-[12px] font-medium text-canvas">
              {price(meta.price, meta.currency)}
            </span>
          )}
        </div>
      ) : (
        <TextTile kicker={meta.price ? price(meta.price, meta.currency) : "Product"} title={item.title} site={site} />
      );

    default:
      return item.lead_image ? (
        <Img src={item.lead_thumb ?? item.lead_image} aspect={item.lead_aspect} />
      ) : (
        <TextTile kicker={site} title={item.title ?? item.url} site={null} summary={item.summary} />
      );
  }
}

/** A page with no image: its title becomes the picture. */
function TextTile({ kicker, title, site, summary }: { kicker?: string | null; title?: string | null; site?: string | null; summary?: string | null }) {
  return (
    <div className="flex min-h-[150px] flex-col p-5">
      {kicker && <span className="label truncate text-hint">{kicker}</span>}
      <p className="mt-3 line-clamp-4 font-display text-[24px] leading-[1.15] text-ink">{title}</p>
      {summary && <p className="mt-3 line-clamp-2 text-[13px] leading-snug text-muted">{summary}</p>}
      {site && <span className="mt-auto pt-4 text-[12px] text-hint">{site}</span>}
    </div>
  );
}

function Caption({ item, highlight }: { item: Item; highlight?: string | null }) {
  const meta = item.meta as Meta;
  const showTitle = CAPTIONED.has(item.type) && !!item.lead_image;
  const site =
    item.type === "video" || item.type === "audio"
      ? meta.channel ?? item.site_name
      : item.type === "pdf"
        ? ["PDF", meta.pages && `${meta.pages} pages`].filter(Boolean).join(" · ")
        : item.type === "product" && meta.price
          ? null
          : item.site_name ?? item.domain;
  if (!showTitle && !highlight?.includes("<mark>") && !(item.note && item.type !== "note") && item.status !== "failed") return null;
  return (
    <div className="px-1 pt-2.5">
      {showTitle && (
        <>
          <p className="line-clamp-2 text-[13px] font-medium leading-snug text-ink-2">{item.title}</p>
          {site && <p className="mt-0.5 truncate text-[12px] text-hint">{site}</p>}
        </>
      )}
      {highlight?.includes("<mark>") && (
        <p className="mt-1 line-clamp-2 text-[12px] leading-snug text-muted" dangerouslySetInnerHTML={{ __html: marks(highlight) }} />
      )}
      {item.note && item.type !== "note" && (
        <p className="mt-1 line-clamp-1 text-[12px] italic text-muted">
          <span className="not-italic text-accent">✎</span> {item.note}
        </p>
      )}
      {item.status === "failed" && <p className="mt-1 text-[12px] text-danger">Couldn&apos;t finish reading this. Retry from ···</p>}
    </div>
  );
}

function CardMenu({ item, onDelete, onRetry, onDismiss }: Pick<CardProps, "item" | "onDelete" | "onRetry" | "onDismiss">) {
  const itemClass = "flex cursor-pointer items-center rounded-lg px-3 py-2 data-[highlighted]:bg-well";
  return (
    <Menu.Root
      positioning={{ placement: "bottom-end", gutter: 6 }}
      onSelect={({ value }) => {
        if (value === "open" && item.url) window.open(item.url, "_blank", "noopener");
        if (value === "copy" && item.url) void navigator.clipboard.writeText(item.url);
        if (value === "delete") onDelete?.(item);
        if (value === "retry") onRetry?.(item);
        if (value === "dismiss") onDismiss?.(item);
      }}
    >
      <Menu.Trigger
        aria-label="More"
        onClick={(e) => e.stopPropagation()}
        className="grid h-7 w-7 place-items-center rounded-full bg-card/90 text-ink-2 opacity-0 shadow-[var(--shadow-card)] backdrop-blur transition-opacity duration-200 group-hover:opacity-100 group-focus-within:opacity-100 data-[state=open]:opacity-100"
      >
        <MoreIcon size={15} />
      </Menu.Trigger>
      <Portal>
        <Menu.Positioner>
          <Menu.Content className="z-50 min-w-40 rounded-xl bg-card p-1 text-[13px] shadow-[var(--shadow-panel)] outline-none">
            {item.url && <Menu.Item value="open" className={itemClass}>Open original</Menu.Item>}
            {item.url && <Menu.Item value="copy" className={itemClass}>Copy link</Menu.Item>}
            {item.status === "failed" && <Menu.Item value="retry" className={itemClass}>Try again</Menu.Item>}
            {onDismiss && <Menu.Item value="dismiss" className={itemClass}>Not now</Menu.Item>}
            <Menu.Item value="delete" className={`${itemClass} text-danger`}>Delete</Menu.Item>
          </Menu.Content>
        </Menu.Positioner>
      </Portal>
    </Menu.Root>
  );
}

export const Card = memo(function Card({ item, reason, highlight, tabIndex = 0, onOpen, onFocusCard, onKeyDown, ...actions }: CardProps) {
  const label = item.title ?? item.summary ?? item.url ?? item.type;
  const open = (e: MouseEvent<HTMLAnchorElement>) => {
    // Plain clicks open the item over the grid; modified clicks keep browser behaviour.
    if (!onOpen || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    e.preventDefault();
    onOpen(item);
  };
  return (
    <motion.article
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      className="group relative"
      data-card-id={item.id}
    >
      <Link
        href={`/item/${item.id}`}
        tabIndex={tabIndex}
        onClick={open}
        onFocus={onFocusCard}
        onKeyDown={onKeyDown}
        aria-label={label}
        className="block rounded-[var(--radius-card)] outline-offset-4"
      >
        <div className="overflow-hidden rounded-[var(--radius-card)] bg-card shadow-[var(--shadow-card)] transition-[transform,box-shadow] duration-300 ease-[var(--ease-out)] group-hover:-translate-y-0.5 group-hover:shadow-[var(--shadow-hover)]">
          <Tile item={item} />
        </div>
        <Caption item={item} highlight={highlight} />
        {reason && <p className="px-1 pt-2 font-display text-[15px] italic leading-snug text-muted">{reason}</p>}
      </Link>
      <div className="absolute right-2.5 top-2.5">
        <CardMenu item={item} {...actions} />
      </div>
    </motion.article>
  );
});
