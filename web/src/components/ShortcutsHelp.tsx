"use client";

import { SHORTCUTS } from "@/lib/shortcuts";
import { Modal } from "./ui/modal";

export function ShortcutsHelp({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  return (
    <Modal open={open} onOpenChange={onOpenChange} title="Keyboard shortcuts" className="max-w-md">
      <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 p-6 pt-4 text-sm">
        {SHORTCUTS.map((s) => (
          <div key={s.keys} className="contents">
            <dt>
              <kbd className="rounded border border-line bg-sunken px-1.5 py-0.5 font-mono text-xs">{s.keys}</kbd>
            </dt>
            <dd className="text-ink-soft">{s.action}</dd>
          </div>
        ))}
      </dl>
    </Modal>
  );
}
