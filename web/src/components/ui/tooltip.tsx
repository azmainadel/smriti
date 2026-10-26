"use client";

import { Portal } from "@ark-ui/react/portal";
import { Tooltip } from "@ark-ui/react/tooltip";
import type { ReactElement } from "react";

export function Tip({ label, children }: { label: string; children: ReactElement }) {
  return (
    <Tooltip.Root openDelay={400} closeDelay={50}>
      <Tooltip.Trigger asChild>{children}</Tooltip.Trigger>
      <Portal>
        <Tooltip.Positioner>
          <Tooltip.Content className="z-50 rounded-md bg-ink px-2 py-1 text-xs text-paper shadow">{label}</Tooltip.Content>
        </Tooltip.Positioner>
      </Portal>
    </Tooltip.Root>
  );
}
