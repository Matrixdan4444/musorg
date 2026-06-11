import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

interface MetadataPillProps {
  label: string;
  value: string;
  icon?: ReactNode;
  className?: string;
}

export function MetadataPill({ label, value, icon, className }: MetadataPillProps) {
  return (
    <div
      className={cn(
        "flex min-w-0 items-center gap-2 rounded-2xl border border-border-soft/75 bg-surface-subtle/85 px-3 py-2.5",
        className,
      )}
    >
      {icon ? <span className="text-muted-foreground">{icon}</span> : null}
      <div className="min-w-0">
        <p className="truncate text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
          {label}
        </p>
        <p className="overflow-hidden break-words text-sm font-medium leading-5 text-[hsl(var(--text-strong))]">
          {value}
        </p>
      </div>
    </div>
  );
}
