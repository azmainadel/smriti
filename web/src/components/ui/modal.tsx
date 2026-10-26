"use client";

import { Dialog } from "@ark-ui/react/dialog";
import { Portal } from "@ark-ui/react/portal";
import type { ReactNode } from "react";
import { CloseIcon } from "./icons";

type ModalProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  hideTitle?: boolean;
  children: ReactNode;
  className?: string;
  /** Top-aligned like a command palette, instead of centered. */
  top?: boolean;
};

export function Modal({ open, onOpenChange, title, hideTitle, children, className = "", top }: ModalProps) {
  return (
    <Dialog.Root open={open} onOpenChange={(d) => onOpenChange(d.open)} lazyMount unmountOnExit>
      <Portal>
        <Dialog.Backdrop className="fixed inset-0 z-40 bg-ink/25 backdrop-blur-[2px]" />
        <Dialog.Positioner className={`fixed inset-0 z-50 flex justify-center px-4 ${top ? "items-start pt-[12vh]" : "items-center"}`}>
          <Dialog.Content
            className={`relative max-h-[80vh] w-full overflow-auto rounded-2xl border border-line bg-surface shadow-[var(--shadow-lift)] outline-none ${className}`}
          >
            <Dialog.Title className={hideTitle ? "sr-only" : "px-6 pt-5 font-serif text-xl font-semibold"}>{title}</Dialog.Title>
            {!hideTitle && (
              <Dialog.CloseTrigger aria-label="Close" className="absolute right-4 top-4 rounded-md p-1 text-muted hover:text-ink">
                <CloseIcon />
              </Dialog.CloseTrigger>
            )}
            {children}
          </Dialog.Content>
        </Dialog.Positioner>
      </Portal>
    </Dialog.Root>
  );
}
