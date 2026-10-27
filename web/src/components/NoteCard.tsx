"use client";

import { useRef, useState } from "react";
import { useSave } from "@/lib/queries";
import { toaster } from "./ui/toast";

const URL_RE = /^https?:\/\/\S+$/i;

/**
 * The first card in the grid is a blank note. Type and press ⌘↵ (or click away) to keep it.
 * A pasted link is saved as a link, not a note.
 */
export function NoteCard() {
  const [text, setText] = useState("");
  const [focused, setFocused] = useState(false);
  const { mutateAsync: save, isPending } = useSave();
  const ref = useRef<HTMLTextAreaElement>(null);

  const commit = async () => {
    const value = text.trim();
    if (!value || isPending) return;
    try {
      await save(URL_RE.test(value) ? { url: value, capture: "web" } : { text: value, capture: "web" });
      setText("");
    } catch (e) {
      toaster.create({ title: "Couldn't save that", description: String(e), type: "error" });
    }
  };

  return (
    <div
      className={`rounded-[var(--radius-card)] bg-card p-5 shadow-[var(--shadow-card)] transition-shadow duration-300 ${focused ? "shadow-[var(--shadow-hover)]" : ""}`}
    >
      <label htmlFor="new-note" className="label text-accent-ink">
        Jot something down
      </label>
      <textarea
        id="new-note"
        ref={ref}
        value={text}
        rows={focused || text ? 6 : 3}
        onChange={(e) => setText(e.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => {
          setFocused(false);
          void commit();
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            void commit();
          }
          if (e.key === "Escape") {
            setText("");
            ref.current?.blur();
          }
        }}
        placeholder="A thought, a quote, a few hex colors…"
        className="ruled mt-2 block w-full resize-none bg-transparent font-serif text-[16px] leading-[26px] text-ink outline-none placeholder:italic placeholder:text-hint"
      />
      <p className={`text-[11px] text-hint transition-opacity ${focused ? "opacity-100" : "opacity-0"}`}>
        ⌘↵ to keep · Esc to clear · paste a link to save it
      </p>
    </div>
  );
}
