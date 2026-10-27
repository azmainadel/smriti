"use client";

import { useEffect, useState } from "react";
import { useSave } from "@/lib/queries";
import { UploadIcon } from "./ui/icons";
import { toaster } from "./ui/toast";

/** Drop files, links or text anywhere on the page to save them. */
export function DropZone() {
  const [over, setOver] = useState(false);
  const { mutateAsync: save } = useSave();

  useEffect(() => {
    let depth = 0;
    const enter = (e: DragEvent) => {
      if (!e.dataTransfer?.types.some((t) => ["Files", "text/uri-list", "text/plain"].includes(t))) return;
      depth += 1;
      setOver(true);
    };
    const leave = () => {
      depth = Math.max(0, depth - 1);
      if (!depth) setOver(false);
    };
    const over = (e: DragEvent) => e.preventDefault();
    const drop = async (e: DragEvent) => {
      e.preventDefault();
      depth = 0;
      setOver(false);
      const dt = e.dataTransfer;
      if (!dt) return;
      const files = Array.from(dt.files);
      const uri = dt.getData("text/uri-list").split("\n").find((l) => l && !l.startsWith("#"));
      const text = dt.getData("text/plain");
      try {
        if (files.length) await Promise.all(files.map((f) => save(f)));
        else if (uri) await save({ url: uri.trim(), capture: "web" });
        else if (text.trim()) await save(/^https?:\/\/\S+$/.test(text.trim()) ? { url: text.trim(), capture: "web" } : { text, capture: "web" });
        toaster.create({ title: files.length > 1 ? `Saved ${files.length} files` : "Saved", type: "success", duration: 2000 });
      } catch (err) {
        toaster.create({ title: "Couldn't save", description: String(err), type: "error" });
      }
    };
    window.addEventListener("dragenter", enter);
    window.addEventListener("dragleave", leave);
    window.addEventListener("dragover", over);
    window.addEventListener("drop", drop);
    return () => {
      window.removeEventListener("dragenter", enter);
      window.removeEventListener("dragleave", leave);
      window.removeEventListener("dragover", over);
      window.removeEventListener("drop", drop);
    };
  }, [save]);

  if (!over) return null;
  return (
    <div className="pointer-events-none fixed inset-3 z-50 grid place-items-center rounded-3xl border-2 border-dashed border-accent bg-canvas/85 backdrop-blur-sm">
      <div className="flex flex-col items-center gap-3 text-accent-ink">
        <UploadIcon size={36} />
        <p className="font-display text-4xl italic">Drop to save</p>
      </div>
    </div>
  );
}
