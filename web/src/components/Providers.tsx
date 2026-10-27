"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { usePathname, useRouter } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";
import { useToken } from "@/lib/auth";
import { useLiveUpdates } from "@/lib/live";
import { Shell } from "./Shell";
import { Toasts } from "./ui/toast";

const PUBLIC = ["/login"];

function Gate({ children }: { children: ReactNode }) {
  const token = useToken();
  const pathname = usePathname();
  const router = useRouter();
  useLiveUpdates(token);

  useEffect(() => {
    if (token === null && !PUBLIC.includes(pathname)) {
      router.replace(`/login?next=${encodeURIComponent(location.pathname + location.search)}`);
    }
  }, [token, pathname, router]);

  if (PUBLIC.includes(pathname)) return <>{children}</>;
  if (!token) return null;
  return <Shell>{children}</Shell>;
}

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: false, retry: 1 } },
      }),
  );

  useEffect(() => {
    if ("serviceWorker" in navigator && process.env.NODE_ENV === "production") {
      void navigator.serviceWorker.register("/sw.js");
    }
  }, []);

  return (
    <QueryClientProvider client={client}>
      <Gate>{children}</Gate>
      <Toasts />
    </QueryClientProvider>
  );
}
