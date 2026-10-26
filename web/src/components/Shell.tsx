"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type ReactNode, createContext, useContext, useEffect, useMemo, useState } from "react";
import { useHotkeys } from "@/lib/shortcuts";
import { useTheme } from "@/lib/theme";
import { CommandK } from "./CommandK";
import { Composer } from "./Composer";
import { DropZone } from "./DropZone";
import { ShortcutsHelp } from "./ShortcutsHelp";
import { MoonIcon, PlusIcon, SearchIcon, SettingsIcon, SunIcon } from "./ui/icons";
import { Tip } from "./ui/tooltip";

type ShellApi = { openSearch: () => void; openComposer: () => void };
const ShellContext = createContext<ShellApi>({ openSearch: () => {}, openComposer: () => {} });
export const useShell = () => useContext(ShellContext);

export function Shell({ children }: { children: ReactNode }) {
  const [searchOpen, setSearchOpen] = useState(false);
  const [composerOpen, setComposerOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [theme, setTheme] = useTheme();
  const pathname = usePathname();
  const router = useRouter();

  useHotkeys({
    "mod+k": () => setSearchOpen(true),
    n: () => setComposerOpen(true),
    "?": () => setHelpOpen(true),
    g: () => router.push("/"),
  });

  const api = useMemo(() => ({ openSearch: () => setSearchOpen(true), openComposer: () => setComposerOpen(true) }), []);
  // Read the applied theme after mount; the server cannot know the system preference.
  const [dark, setDark] = useState(false);
  useEffect(() => setDark(document.documentElement.dataset.theme === "dark"), [theme]);

  return (
    <ShellContext.Provider value={api}>
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-surface focus:px-3 focus:py-2">
        Skip to content
      </a>
      <header className="sticky top-0 z-30 border-b border-transparent bg-paper/85 backdrop-blur supports-[backdrop-filter]:bg-paper/70">
        <div className="mx-auto flex h-14 max-w-[1600px] items-center gap-2 px-4 sm:px-6">
          <Link href="/" className="mr-auto flex items-baseline gap-2" aria-label="Smriti home">
            <span className="font-serif text-xl font-semibold">স্মৃতি</span>
            <span className="text-sm text-muted">smriti</span>
          </Link>
          <nav className="flex items-center gap-1 text-sm">
            <Link href="/digest" className={`hidden rounded-lg px-3 py-1.5 sm:block ${pathname === "/digest" ? "bg-sunken" : "text-muted hover:text-ink"}`}>
              Digest
            </Link>
            <Tip label="Search (⌘K)">
              <button type="button" aria-label="Search" onClick={() => setSearchOpen(true)} className="hidden rounded-lg p-2 text-muted hover:bg-sunken hover:text-ink sm:block">
                <SearchIcon />
              </button>
            </Tip>
            <Tip label="Save something (N)">
              <button type="button" aria-label="Save something" onClick={() => setComposerOpen(true)} className="rounded-lg p-2 text-muted hover:bg-sunken hover:text-ink">
                <PlusIcon />
              </button>
            </Tip>
            <Tip label={dark ? "Light theme" : "Dark theme"}>
              <button type="button" aria-label="Toggle theme" onClick={() => setTheme(dark ? "light" : "dark")} className="rounded-lg p-2 text-muted hover:bg-sunken hover:text-ink">
                {dark ? <SunIcon /> : <MoonIcon />}
              </button>
            </Tip>
            <Tip label="Settings">
              <Link href="/settings" aria-label="Settings" className="rounded-lg p-2 text-muted hover:bg-sunken hover:text-ink">
                <SettingsIcon />
              </Link>
            </Tip>
          </nav>
        </div>
      </header>
      <main id="main" className="mx-auto max-w-[1600px] px-3 pb-28 pt-4 sm:px-6 sm:pb-16">
        {children}
      </main>
      {/* Mobile: search within thumb reach. */}
      <div className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-paper/95 p-3 backdrop-blur sm:hidden">
        <button
          type="button"
          onClick={() => setSearchOpen(true)}
          className="flex w-full items-center gap-3 rounded-2xl border border-line bg-surface px-4 py-3 text-left text-muted"
        >
          <SearchIcon /> Search your library
        </button>
      </div>
      <CommandK open={searchOpen} onOpenChange={setSearchOpen} />
      <Composer open={composerOpen} onOpenChange={setComposerOpen} />
      <ShortcutsHelp open={helpOpen} onOpenChange={setHelpOpen} />
      <DropZone />
    </ShellContext.Provider>
  );
}
