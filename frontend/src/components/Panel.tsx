import type { HTMLAttributes } from "react";
import { cn } from "@/lib/cn";

interface PanelProps extends HTMLAttributes<HTMLDivElement> {
  elevated?: boolean;
}

export function Panel({ className, elevated = false, ...props }: PanelProps) {
  return (
    <div
      className={cn(
        "surface-card rounded-[22px] p-4 text-sm text-[hsl(var(--text-base))]",
        elevated && "shadow-panel",
        className,
      )}
      {...props}
    />
  );
}
