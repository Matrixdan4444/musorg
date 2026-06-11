import { FieldHelp } from "@/components/FieldHelp";

export function BulkFieldLabel({
  label,
  helpText,
}: {
  label: string;
  helpText?: string | undefined;
}) {
  return (
    <span className="flex items-center gap-1.5 text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
      <span>{label}</span>
      {helpText ? <FieldHelp label={`${label} help`} description={helpText} /> : null}
    </span>
  );
}
