"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { LogoMark } from "@/components/ui/Logo";
import { Button } from "@/components/ui/button";
import { setToken } from "@/lib/auth";
import { API_URL } from "@/lib/config";

function Login() {
  const [secret, setSecret] = useState("");
  const [device, setDevice] = useState("web");
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const next = useSearchParams().get("next") || "/";

  const submit = async () => {
    setError(null);
    const res = await fetch(`${API_URL}/auth/tokens`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: device, secret }),
    }).catch(() => null);
    if (!res?.ok) {
      setError(res?.status === 401 ? "That secret didn't match." : `Can't reach the API at ${API_URL}.`);
      return;
    }
    setToken((await res.json()).token);
    router.replace(next.startsWith("/") ? next : "/");
  };

  return (
    <main className="grid min-h-dvh place-items-center px-4">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
        className="w-full max-w-sm"
      >
        <LogoMark className="mb-6 h-14 w-auto text-brand" />
        <h1 className="flex items-baseline gap-3 font-display text-5xl font-medium tracking-[-0.02em]">smriti<span lang="bn" className="text-xl font-normal text-accent">স্মৃতি</span></h1>
        <p className="mt-2 text-muted">Enter the owner secret from your server&apos;s .env. This device gets its own token, revocable from Settings.</p>
        <label className="mt-8 block text-sm font-medium" htmlFor="secret">
          Owner secret
        </label>
        <input
          id="secret"
          type="password"
          autoFocus
          value={secret}
          onChange={(e) => setSecret(e.target.value)}
          className="mt-1 w-full rounded-xl bg-card px-4 py-2.5 shadow-[var(--shadow-card)] outline-none focus:ring-2 focus:ring-accent"
        />
        <label className="mt-4 block text-sm font-medium" htmlFor="device">
          Device name
        </label>
        <input
          id="device"
          value={device}
          onChange={(e) => setDevice(e.target.value)}
          className="mt-1 w-full rounded-xl bg-card px-4 py-2.5 shadow-[var(--shadow-card)] outline-none focus:ring-2 focus:ring-accent"
        />
        {error && <p className="mt-3 text-sm text-danger" role="alert">{error}</p>}
        <Button type="submit" variant="primary" className="mt-6 w-full py-2.5" disabled={!secret}>
          Continue
        </Button>
      </form>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <Login />
    </Suspense>
  );
}
