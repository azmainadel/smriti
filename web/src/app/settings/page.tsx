"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { toaster } from "@/components/ui/toast";
import { api, call, downloadExport, importFile } from "@/lib/api";
import { setToken } from "@/lib/auth";
import { API_URL } from "@/lib/config";
import { timeAgo } from "@/lib/format";
import { keys } from "@/lib/queries";
import { type Theme, useTheme } from "@/lib/theme";

type Status = {
  queue: Record<string, Record<string, number>>;
  failed: { id: number; item_id: string; step: string; error: string; attempts: number; finished_at: string; title: string | null; source_url: string | null }[];
  enrichment: { step: string; runs: number; avg_ms: number; p95_ms: number; avg_tokens: number; total_cost: number; errors: number; model: string | null }[];
  pipeline: { step: string; runs: number; avg_ms: number; p95_ms: number }[];
  save_to_ready_s: { p50: number | null; p95: number | null };
  items: { type: string; status: string; count: number }[];
  resurfacing: { shown: number; opened: number; rate: number };
  capabilities: Record<string, string | boolean | string[] | null>;
};
type Models = {
  defaults: { provider: string; model: string };
  steps: string[];
  overrides: Record<string, { provider: string; model: string; price_per_1k?: number }>;
  embeddings: { provider: string; model: string; dim: number };
};

function Section({ title, children, description }: { title: string; description?: string; children: React.ReactNode }) {
  return (
    <section className="border-t border-hairline py-8">
      <h2 className="font-display text-2xl">{title}</h2>
      {description && <p className="mt-1 text-sm text-muted">{description}</p>}
      <div className="mt-5">{children}</div>
    </section>
  );
}

function ModelRow({ step, models }: { step: string; models: Models }) {
  const qc = useQueryClient();
  const current = models.overrides[step] ?? models.defaults;
  const [provider, setProvider] = useState(current.provider);
  const [model, setModel] = useState(current.model);
  const save = useMutation({
    mutationFn: () => call(api.PUT("/admin/settings/models/{step}", { params: { path: { step } }, body: { provider: provider as "none", model, price_per_1k: 0 } })),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: keys.models });
      toaster.create({ title: `${step} now uses ${provider}:${model}`, description: "New saves use it. Re-run the step to update old items.", duration: 3500 });
    },
  });
  const rerun = useMutation({
    mutationFn: () => call(api.POST("/admin/reindex", { body: { step, force: true } })),
    onSuccess: (r) => toaster.create({ title: `Queued ${r.enqueued} items for ${step}` }),
  });
  const external = provider === "openai";
  return (
    <tr className="border-t border-hairline">
      <td className="py-2 pr-3 font-medium">{step}</td>
      <td className="py-2 pr-3">
        <select value={provider} onChange={(e) => setProvider(e.target.value)} className="rounded-lg border border-hairline bg-card px-2 py-1" aria-label={`${step} provider`}>
          <option value="none">none (heuristics)</option>
          <option value="ollama">ollama (local)</option>
          <option value="openai">OpenAI-compatible API</option>
        </select>
      </td>
      <td className="py-2 pr-3">
        <input value={model} onChange={(e) => setModel(e.target.value)} className="w-48 rounded-lg border border-hairline bg-card px-2 py-1" aria-label={`${step} model`} />
      </td>
      <td className="py-2 pr-3">{external && <span className="rounded-full bg-accent-wash px-2 py-0.5 text-xs text-accent-ink">sends data off this machine</span>}</td>
      <td className="py-2 text-right">
        <Button onClick={() => save.mutate()} disabled={save.isPending}>Save</Button>{" "}
        {step !== "query" && step !== "caption" && <Button variant="quiet" onClick={() => rerun.mutate()}>Re-run all</Button>}
      </td>
    </tr>
  );
}

function Tokens() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: keys.tokens, queryFn: () => call(api.GET("/auth/tokens")) });
  const [created, setCreated] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [secret, setSecret] = useState("");
  const revoke = useMutation({
    mutationFn: (id: string) => call(api.DELETE("/auth/tokens/{token_id}", { params: { path: { token_id: id } } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.tokens }),
  });
  const create = useMutation({
    mutationFn: () => call(api.POST("/auth/tokens", { body: { name, secret } })),
    onSuccess: (t) => {
      setCreated(t.token);
      setSecret("");
      void qc.invalidateQueries({ queryKey: keys.tokens });
    },
    onError: () => toaster.create({ title: "Wrong owner secret", type: "error" }),
  });
  return (
    <div className="space-y-4">
      <ul className="divide-y divide-hairline rounded-xl border border-hairline">
        {data?.map((t) => (
          <li key={t.id} className="flex items-center gap-3 px-4 py-2.5 text-sm">
            <span className="font-medium">{t.name}</span>
            <span className="text-muted">{t.revoked_at ? "revoked" : t.last_used_at ? `used ${timeAgo(t.last_used_at)}` : "never used"}</span>
            {!t.revoked_at && (
              <Button variant="quiet" className="ml-auto" onClick={() => revoke.mutate(t.id)}>
                Revoke
              </Button>
            )}
          </li>
        ))}
      </ul>
      <form
        className="flex flex-wrap gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Device name, e.g. Firefox laptop" className="flex-1 rounded-lg border border-hairline bg-card px-3 py-1.5 text-sm" aria-label="Device name" />
        <input value={secret} onChange={(e) => setSecret(e.target.value)} type="password" placeholder="Owner secret" className="w-40 rounded-lg border border-hairline bg-card px-3 py-1.5 text-sm" aria-label="Owner secret" />
        <Button type="submit" disabled={!name || !secret}>New token</Button>
      </form>
      {created && (
        <div className="rounded-xl bg-accent-wash p-4 text-sm">
          <p className="font-medium">Copy this token now. It is not shown again.</p>
          <code className="mt-2 block break-all font-mono text-xs">{created}</code>
          <p className="mt-2 text-muted">API URL: <code>{API_URL}</code></p>
        </div>
      )}
    </div>
  );
}

function Health() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: keys.status, queryFn: () => call(api.GET("/admin/status")) as Promise<Status>, refetchInterval: 5000 });
  const retryAll = useMutation({
    mutationFn: () => call(api.POST("/admin/retry-failed")),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.status }),
  });
  if (!data) return <div className="shimmer h-40 rounded-xl" />;
  const queued = Object.values(data.queue).reduce((n, s) => n + (s.queued ?? 0) + (s.running ?? 0), 0);
  const total = data.items.reduce((n, r) => n + r.count, 0);
  const fmt = (s: number | null) => (s == null ? "–" : `${s.toFixed(1)} s`);
  return (
    <div className="space-y-6 text-sm">
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          ["Items", total],
          ["In queue", queued],
          ["Save → ready p95", fmt(data.save_to_ready_s.p95)],
          ["Resurfaced opened", data.resurfacing.shown ? `${Math.round(data.resurfacing.rate * 100)}% of ${data.resurfacing.shown}` : "–"],
        ].map(([k, v]) => (
          <div key={k as string} className="rounded-xl bg-well px-4 py-3">
            <dt className="text-xs text-muted">{k}</dt>
            <dd className="mt-1 text-lg font-medium">{v}</dd>
          </div>
        ))}
      </dl>
      <div>
        <h3 className="mb-2 font-medium">Enrichment, last 30 days</h3>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="text-left text-xs text-muted">
              <tr><th className="py-1">Step</th><th>Model</th><th className="text-right">Runs</th><th className="text-right">Avg</th><th className="text-right">p95</th><th className="text-right">Tokens</th><th className="text-right">Cost</th><th className="text-right">Errors</th></tr>
            </thead>
            <tbody>
              {data.enrichment.map((r) => (
                <tr key={r.step} className="border-t border-hairline">
                  <td className="py-1.5">{r.step}</td><td className="text-muted">{r.model ?? "–"}</td><td className="text-right">{r.runs}</td><td className="text-right">{r.avg_ms} ms</td><td className="text-right">{Math.round(r.p95_ms)} ms</td><td className="text-right">{r.avg_tokens}</td><td className="text-right">${r.total_cost.toFixed(4)}</td><td className="text-right">{r.errors}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div>
        <div className="mb-2 flex items-center justify-between">
          <h3 className="font-medium">Failed steps</h3>
          {data.failed.length > 0 && <Button onClick={() => retryAll.mutate()}>Retry all</Button>}
        </div>
        {data.failed.length === 0 ? (
          <p className="text-muted">Nothing failed.</p>
        ) : (
          <ul className="divide-y divide-hairline rounded-xl border border-hairline">
            {data.failed.map((f) => (
              <li key={f.id} className="px-4 py-2.5">
                <a href={`/?item=${f.item_id}`} className="block truncate font-medium hover:underline">{f.title ?? f.source_url ?? f.item_id}</a>
                <p className="mt-0.5 line-clamp-2 break-all font-mono text-xs text-danger">{f.step}: {f.error}</p>
              </li>
            ))}
          </ul>
        )}
      </div>
      <p className="text-xs text-muted">
        {Object.entries(data.capabilities)
          .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(", ") || "none" : v === true ? "on" : v || "off"}`)
          .join(" · ")}
      </p>
    </div>
  );
}

export default function SettingsPage() {
  const [theme, setTheme] = useTheme();
  const qc = useQueryClient();
  const models = useQuery({ queryKey: keys.models, queryFn: () => call(api.GET("/admin/settings/models")) as Promise<Models> });
  const digest = useQuery({ queryKey: keys.digest, queryFn: () => call(api.GET("/admin/settings/digest")) });
  const setDigest = useMutation({
    mutationFn: (email: boolean) => call(api.PUT("/admin/settings/digest", { body: { email, web_url: location.origin } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.digest }),
  });
  const file = useRef<HTMLInputElement>(null);

  return (
    <div className="mx-auto max-w-4xl pb-16 pt-8 sm:pt-14">
      <h1 className="font-display text-5xl">Settings</h1>

      <Section title="Appearance">
        <div className="flex gap-2">
          {(["system", "light", "dark"] as Theme[]).map((t) => (
            <Button key={t} variant={theme === t ? "primary" : "ghost"} onClick={() => setTheme(t)}>
              {t[0]?.toUpperCase() + t.slice(1)}
            </Button>
          ))}
        </div>
      </Section>

      <Section title="Models" description="Each step runs on a local model, an API, or plain heuristics. Nothing leaves this machine unless a step points at an external API.">
        {models.data && (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <tbody>
                  {models.data.steps.map((s) => (
                    <ModelRow key={s} step={s} models={models.data} />
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-3 text-xs text-muted">
              Embeddings: {models.data.embeddings.provider}:{models.data.embeddings.model} ({models.data.embeddings.dim} dims), fixed per install.
            </p>
          </>
        )}
      </Section>

      <Section title="Queue and health">
        <Health />
      </Section>

      <Section title="Devices" description="Every browser, phone and script gets its own token, so you can revoke one without touching the rest.">
        <Tokens />
      </Section>

      <Section title="Capture">
        <ul className="space-y-3 text-sm text-ink-2">
          <li><strong className="text-ink">Browser extension:</strong> load <code>extension/</code> in Chrome or Firefox, then paste the API URL and a token in its options.</li>
          <li><strong className="text-ink">Android:</strong> install this site as an app (browser menu → Install). It then appears in the share sheet.</li>
          <li><strong className="text-ink">iPhone:</strong> make a Shortcut that runs “Get Contents of URL” with POST <code>{API_URL}/items</code>, header <code>Authorization: Bearer &lt;token&gt;</code>, JSON body <code>{"{"}&quot;url&quot;: Shortcut Input{"}"}</code>, and enable it in the share sheet.</li>
          <li><strong className="text-ink">Email:</strong> point your mail provider&apos;s inbound webhook at <code>{API_URL}/inbound/email/&lt;SMRITI_INBOUND_EMAIL_SECRET&gt;</code>.</li>
        </ul>
      </Section>

      <Section title="Weekly digest">
        <label className="flex items-center gap-3 text-sm">
          <input type="checkbox" checked={digest.data?.email ?? false} onChange={(e) => setDigest.mutate(e.target.checked)} className="h-4 w-4 accent-[var(--color-accent)]" />
          Email me 7 items from my past every week (needs SMTP settings on the server). The digest is always at <a className="text-accent-ink underline" href="/digest">/digest</a>.
        </label>
      </Section>

      <Section title="Import and export" description="Bring in bookmarks, Pocket or Raindrop. Export everything as JSON plus files whenever you like.">
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => file.current?.click()}>Import a file…</Button>
          <Button onClick={() => void downloadExport().catch((e) => toaster.create({ title: "Export failed", description: String(e), type: "error" }))}>Export everything</Button>
          <input
            ref={file}
            type="file"
            accept=".html,.htm,.csv"
            hidden
            onChange={async (e) => {
              const f = e.target.files?.[0];
              if (!f) return;
              const r = await importFile(f);
              toaster.create({ title: `Imported ${r.created} of ${r.found}`, description: r.skipped ? `${r.skipped} were already saved` : undefined, type: "success" });
              void qc.invalidateQueries({ queryKey: keys.feed });
            }}
          />
        </div>
      </Section>

      <Section title="This device">
        <Button variant="ghost" onClick={() => setToken(null)}>Sign out</Button>
      </Section>
    </div>
  );
}
