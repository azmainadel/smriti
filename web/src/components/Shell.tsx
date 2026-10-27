"use client";

import { AnimatePresence } from "motion/react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { type ReactNode, Suspense, createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useSave } from "@/lib/queries";
import { useHotkeys } from "@/lib/shortcuts";
import { useTheme } from "@/lib/theme";
import dynamic from "next/dynamic";
import { DropZone } from "./DropZone";

// Loaded on first use: none of these are needed to paint the grid.
const ItemView = dynamic(() => import("./ItemView").then((m) => m.ItemView), { ssr: false });
const Composer = dynamic(() => import("./Composer").then((m) => m.Composer), { ssr: false });
const ShortcutsHelp = dynamic(() => import("./ShortcutsHelp").then((m) => m.ShortcutsHelp), { ssr: false });
import { MoonIcon, PlusIcon, SettingsIcon, SunIcon } from "./ui/icons";
import { LogoMark } from "./ui/Logo";
import { toaster } from "./ui/toast";

type ShellApi = {
  openItem: (id: string) => void;
  openComposer: () => void;
  /** Pages register the order of what they show, so ← → in the item view walk it. */
  setSequence: (ids: string[]) => void;
};
const ShellContext = createContext<ShellApi>({ openItem: () => {}, openComposer: () => {}, setSequence: () => {} });
export const useShell = () => useContext(ShellContext);

const NAV = [
  { href: "/", label: "Everything" },
  { href: "/wander", label: "Wander" },
  { href: "/digest", label: "Look back" },
];

function Overlay({ sequence }: { sequence: React.RefObject<string[]> }) {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const id = params.get("item");

  const withItem = useCallback(
    (next: string | null) => {
      const p = new URLSearchParams(params.toString());
      if (next) p.set("item", next);
      else p.delete("item");
      const qs = p.toString();
      return qs ? `${pathname}?${qs}` : pathname;
    },
    [params, pathname],
  );

  useEffect(() => {
    document.body.style.overflow = id ? "hidden" : "";
  }, [id]);

  return (
    <AnimatePresence>
      {id && (
        <ItemView
          key="item"
          id={id}
          onClose={() => router.replace(withItem(null), { scroll: false })}
          onOpenItem={(next) => router.replace(withItem(next), { scroll: false })}
          onNavigate={(dir) => {
            const ids = sequence.current ?? [];
            const next = ids[ids.indexOf(id) + dir];
            if (next) router.replace(withItem(next), { scroll: false });
          }}
        />
      )}
    </AnimatePresence>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const [composerOpen, setComposerOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [theme, setTheme] = useTheme();
  const [dark, setDark] = useState(false);
  const pathname = usePathname();
  const router = useRouter();
  const sequence = useRef<string[]>([]);
  const { mutateAsync: save } = useSave();

  useEffect(() => {
    setDark(document.documentElement.dataset.theme === "dark");
  }, [theme]);

  const openItem = useCallback(
    (id: string) => {
      const p = new URLSearchParams(window.location.search);
      p.set("item", id);
      router.push(`${pathname}?${p}`, { scroll: false });
    },
    [pathname, router],
  );

  useHotkeys({
    "mod+k": () => (pathname === "/" ? window.dispatchEvent(new Event("smriti:focus-search")) : router.push("/?focus=1")),
    n: () => setComposerOpen(true),
    "?": () => setHelpOpen(true),
  });

  // Paste anywhere (outside a text field) to save a link or a snippet.
  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && (el.isContentEditable || ["INPUT", "TEXTAREA"].includes(el.tagName))) return;
      const file = e.clipboardData?.files[0];
      const text = e.clipboardData?.getData("text/plain").trim();
      if (!file && !text) return;
      e.preventDefault();
      const input = file ?? (/^https?:\/\/\S+$/.test(text!) ? { url: text!, capture: "web" as const } : { text: text!, capture: "web" as const });
      save(input)
        .then(() => toaster.create({ title: "Saved", duration: 1500 }))
        .catch((err) => toaster.create({ title: "Couldn't save", description: String(err), type: "error" }));
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [save]);

  const api = useMemo<ShellApi>(
    () => ({ openItem, openComposer: () => setComposerOpen(true), setSequence: (ids) => {
        sequence.current = ids;
      },
    }),
    [openItem],
  );

  const iconBtn = "grid h-9 w-9 place-items-center rounded-full text-hint transition-colors hover:bg-card hover:text-ink";

  return (
    <ShellContext.Provider value={api}>
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-full focus:bg-card focus:px-4 focus:py-2">
        Skip to content
      </a>
      <header className="mx-auto flex max-w-[1680px] flex-wrap items-center gap-x-3 gap-y-1 px-4 pt-3 sm:h-16 sm:flex-nowrap sm:px-8 sm:pt-0">
        <Link href="/" className="group flex items-center gap-2" aria-label="Smriti, everything">
          <LogoMark className="h-[26px] w-auto text-brand transition-transform duration-500 ease-[var(--ease-out)] group-hover:-translate-y-0.5" />
          <span className="flex items-baseline gap-2">
            <span className="font-display text-[25px] font-medium leading-none tracking-[-0.02em]">smriti</span>
            <span lang="bn" className="text-[16px] leading-none text-accent">
              স্মৃতি
            </span>
          </span>
        </Link>
        <nav className="no-scrollbar order-last -mx-1 flex w-full gap-1 overflow-x-auto sm:order-none sm:mx-auto sm:w-auto" aria-label="Views">
          {NAV.map((n) => {
            const active = pathname === n.href;
            return (
              <Link
                key={n.href}
                href={n.href}
                aria-current={active ? "page" : undefined}
                className={`whitespace-nowrap rounded-full px-3.5 py-1.5 text-[13px] transition-colors ${active ? "bg-card font-medium text-ink shadow-[var(--shadow-card)]" : "text-muted hover:text-ink"}`}
              >
                {n.label}
              </Link>
            );
          })}
        </nav>
        <div className="ml-auto flex items-center sm:ml-0">
          <button type="button" aria-label="Save a link or note (N)" title="Save a link or note (N)" onClick={() => setComposerOpen(true)} className={iconBtn}>
            <PlusIcon size={17} />
          </button>
          <button type="button" aria-label="Toggle theme" title="Toggle theme" onClick={() => setTheme(dark ? "light" : "dark")} className={iconBtn}>
            {dark ? <SunIcon size={17} /> : <MoonIcon size={17} />}
          </button>
          <Link href="/settings" aria-label="Settings" title="Settings" className={iconBtn}>
            <SettingsIcon size={17} />
          </Link>
        </div>
      </header>
      <main id="main" className="mx-auto max-w-[1680px] px-4 pb-24 sm:px-8">
        {children}
      </main>
      <Suspense>
        <Overlay sequence={sequence} />
      </Suspense>
      {composerOpen && <Composer open onOpenChange={setComposerOpen} />}
      {helpOpen && <ShortcutsHelp open onOpenChange={setHelpOpen} />}
      <DropZone />
    </ShellContext.Provider>
  );
}
