"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { CheckIcon } from "@/components/ui/icons";
import { useSave } from "@/lib/queries";

const URL_RE = /https?:\/\/\S+/i;
const SHARE_CACHE = "smriti-share";

/** The PWA share target and the capture panel: preview, note, save. Closes itself after 1 s. */
function Share() {
  const params = useSearchParams();
  const router = useRouter();
  const { mutateAsync: save } = useSave();
  const [note, setNote] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [done, setDone] = useState(false);
  const loaded = useRef(false);

  const title = params.get("title") ?? "";
  const text = params.get("text") ?? "";
  // Android puts the URL in `text` as often as in `url`.
  const url = params.get("url") || text.match(URL_RE)?.[0] || "";
  const body = url ? text.replace(url, "").trim() : text;

  useEffect(() => {
    // Files shared to the PWA were stashed by the service worker.
    if (loaded.current || !params.get("files")) return;
    loaded.current = true;
    void caches.open(SHARE_CACHE).then(async (cache) => {
      const out: File[] = [];
      for (const req of await cache.keys()) {
        const res = await cache.match(req);
        if (res) out.push(new File([await res.blob()], decodeURIComponent(new URL(req.url).pathname.split("/").pop() ?? "file"), { type: res.headers.get("content-type") ?? "" }));
        await cache.delete(req);
      }
      setFiles(out);
    });
  }, [params]);

  const submit = async () => {
    if (files.length) await Promise.all(files.map((f) => save(f)));
    else if (url) await save({ url, title: title || null, note: [note, body].filter(Boolean).join("\n\n") || null, capture: "share" });
    else await save({ text: [title, body].filter(Boolean).join("\n\n"), note: note || null, capture: "share" });
    setDone(true);
    setTimeout(() => (window.history.length > 1 ? router.back() : router.replace("/")), 1000);
  };

  if (done) {
    return (
      <div className="grid min-h-[60vh] place-items-center text-accent-ink">
        <div className="flex flex-col items-center gap-2">
          <CheckIcon size={36} />
          <p className="font-display text-4xl italic">Saved</p>
        </div>
      </div>
    );
  }

  return (
    <form
      className="mx-auto max-w-lg space-y-4 pt-6"
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <div className="rounded-[var(--radius-card)] border border-hairline bg-card p-4">
        <p className="font-display text-2xl">{title || url || files[0]?.name || "Shared text"}</p>
        {url && <p className="mt-1 truncate text-sm text-muted">{url}</p>}
        {body && <p className="mt-2 line-clamp-4 text-sm text-ink-2">{body}</p>}
        {files.length > 0 && <p className="mt-2 text-sm text-muted">{files.length} file(s)</p>}
      </div>
      <textarea
        autoFocus
        value={note}
        onChange={(e) => setNote(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), void submit())}
        placeholder="Add a note (Enter to save)"
        rows={3}
        className="w-full rounded-xl border border-hairline bg-card p-3 outline-none focus:border-accent"
      />
      <Button type="submit" variant="primary" className="w-full py-2.5" disabled={!url && !text && !title && !files.length}>
        Save
      </Button>
    </form>
  );
}

export default function SharePage() {
  return (
    <Suspense>
      <Share />
    </Suspense>
  );
}
