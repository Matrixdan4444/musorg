import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";

interface SectionTitleProps extends HTMLAttributes<HTMLDivElement> {
  title: string;
  subtitle?: string;
  action?: ReactNode;
}

export function SectionTitle({
  title,
  subtitle,
  action,
  className,
  ...props
}: SectionTitleProps) {
  return (
    <div
      className={cn("flex items-start justify-between gap-3", className)}
      {...props}
    >
      <div className="space-y-1">
        <h2 className="text-[15px] font-semibold tracking-tight text-[hsl(var(--text-strong))]">
          {title}
        </h2>
        {subtitle ? (
          <p className="text-[12px] text-muted-foreground">{subtitle}</p>
        ) : null}
      </div>
      {action}
    </div>
  );
}
