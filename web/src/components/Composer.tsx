"use client";

import { useRef, useState } from "react";
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
  const picker = useRef<HTMLInputElement>(null);

  const saveFiles = async (files: FileList) => {
    onOpenChange(false);
    const results = await Promise.allSettled([...files].map((f) => save.mutateAsync(f)));
    const failed = results.filter((r) => r.status === "rejected").length;
    if (failed) toaster.create({ title: `Couldn't save ${failed} of ${results.length} files`, type: "error" });
  };

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
          data-autofocus
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={isUrl ? 1 : 6}
          placeholder="Paste a link, or write a note, a quote, a list of hex colors…"
          className="w-full resize-none rounded-xl bg-well p-4 font-display text-xl outline-none focus:ring-2 focus:ring-accent"
          aria-label="Link or note"
        />
        {isUrl && (
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Add a note (optional)"
            className="w-full rounded-xl border border-hairline bg-canvas px-3 py-2 text-sm outline-none focus:border-accent"
            aria-label="Note"
          />
        )}
        <div className="flex items-center gap-3">
          <Button type="button" variant="quiet" onClick={() => picker.current?.click()} className="-ml-3">
            Add a file
          </Button>
          <input ref={picker} type="file" multiple hidden onChange={(e) => e.target.files?.length && void saveFiles(e.target.files)} />
          <p className="ml-auto hidden text-xs text-muted sm:block">{isUrl ? "Enter to save" : "⌘ Enter to save"}</p>
          <Button type="submit" variant="primary" className="max-sm:ml-auto" disabled={!text.trim() || save.isPending}>
            Save
          </Button>
        </div>
      </form>
    </Modal>
  );
}
