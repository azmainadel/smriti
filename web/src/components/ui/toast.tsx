"use client";

import { Toast, Toaster, createToaster } from "@ark-ui/react/toast";
import { CloseIcon } from "./icons";

export const toaster = createToaster({ placement: "bottom-end", gap: 12, overlap: false, max: 4 });

export function Toasts() {
  return (
    <Toaster toaster={toaster}>
      {(t) => (
        <Toast.Root className="flex w-[min(20rem,calc(100vw-2rem))] items-start gap-3 rounded-xl border border-hairline bg-card px-4 py-3 shadow-[var(--shadow-panel)] transition-all data-[state=closed]:opacity-0">
          <div className="min-w-0 flex-1">
            <Toast.Title className="text-sm font-medium text-ink">{t.title}</Toast.Title>
            {t.description ? <Toast.Description className="mt-0.5 text-sm text-muted">{t.description}</Toast.Description> : null}
          </div>
          {t.action ? (
            <Toast.ActionTrigger className="text-sm font-medium text-accent-ink hover:underline">{t.action.label}</Toast.ActionTrigger>
          ) : null}
          <Toast.CloseTrigger aria-label="Dismiss" className="text-muted hover:text-ink">
            <CloseIcon size={16} />
          </Toast.CloseTrigger>
        </Toast.Root>
      )}
    </Toaster>
  );
}
