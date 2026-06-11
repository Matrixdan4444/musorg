import { AlertCircle, Check, Music2 } from "lucide-react";
import { cn } from "@/lib/cn";
import type { AlbumIssue, IssueSeverity } from "@/types/music";

const toneMap: Record<IssueSeverity, string> = {
  danger: "app-tonal-danger",
  warning: "app-tonal-warning",
  success: "app-tonal-success",
  neutral: "app-tonal-info",
};

function iconForSeverity(severity: IssueSeverity) {
  if (severity === "danger") {
    return AlertCircle;
  }
  if (severity === "warning") {
    return Music2;
  }
  if (severity === "success") {
    return Check;
  }
  return AlertCircle;
}

interface IssueBadgeProps {
  issue?: AlbumIssue;
  severity?: IssueSeverity;
  value?: string | number;
  compact?: boolean;
  className?: string;
}

export function IssueBadge({
  issue,
  severity = issue?.severity ?? "neutral",
  value,
  compact = false,
  className,
}: IssueBadgeProps) {
  const Icon = iconForSeverity(severity);

  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-1 text-[10px] font-medium leading-none",
        toneMap[severity],
        compact && "px-1.5 py-0.5 text-[9px]",
        className,
      )}
    >
      <Icon className={cn("h-3 w-3", compact && "h-2.5 w-2.5")} />
      {value ?? issue?.label}
    </span>
  );
}
