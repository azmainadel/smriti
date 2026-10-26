"use client";

import { useState } from "react";
import { useSave } from "@/lib/queries";
import { Button } from "./ui/button";
import { Modal } from "./ui/modal";
import { toaster } from "./ui/toast";

const URL_RE = /^https?:\/\/\S+$/i;

/** Paste a link or write a note. Enter in the link field saves; ⌘Enter saves a note. */
export function Composer({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const [text, setText] = useState("");
  const [note, setNote] = useState("");
  const save = useSave();
  const isUrl = URL_RE.test(text.trim());

  const submit = async () => {
    const value = text.trim();
    if (!value) return;
    try {
      await save.mutateAsync(isUrl ? { url: value, note: note || null, capture: "web" } : { text: value, note: note || null, capture: "web" });
      setText("");
      setNote("");
      onOpenChange(false);
    } catch (e) {
      toaster.create({ title: "Couldn't save", description: String(e), type: "error" });
    }
  };

  return (
    <Modal open={open} onOpenChange={onOpenChange} title="Save something" className="max-w-xl">
      <form
        className="space-y-3 p-6 pt-4"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) (e.preventDefault(), void submit());
        }}
      >
        <textarea
          autoFocus
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={isUrl ? 1 : 6}
          placeholder="Paste a link, or write a note, a quote, a list of hex colors…"
          className="w-full resize-none rounded-xl border border-line bg-paper p-3 font-serif text-lg outline-none focus:border-accent"
          aria-label="Link or note"
        />
        {isUrl && (
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Add a note (optional)"
            className="w-full rounded-xl border border-line bg-paper px-3 py-2 text-sm outline-none focus:border-accent"
            aria-label="Note"
          />
        )}
        <div className="flex items-center justify-between">
          <p className="text-xs text-muted">{isUrl ? "Enter to save" : "⌘ Enter to save"}</p>
          <Button type="submit" variant="primary" disabled={!text.trim() || save.isPending}>
            Save
          </Button>
        </div>
      </form>
    </Modal>
  );
}
