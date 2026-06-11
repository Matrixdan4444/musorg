import { useEffect, useState } from "react";
import { FolderOutput, FolderSearch, X } from "lucide-react";
import { Panel } from "@/components/Panel";
import { useI18n } from "@/i18n/useI18n";
import { cn } from "@/lib/cn";

interface LibraryPickerDialogProps {
  open: boolean;
  libraryPath: string;
  outputPath: string;
  isAvailable: boolean;
  isConfigured: boolean;
  error?: string | null;
  pickerAvailable: boolean;
  busy: boolean;
  onClose: () => void;
  onPickLibrary: () => Promise<string | null>;
  onPickOutput: () => Promise<string | null>;
  onSave: (libraryPath: string, outputPath: string) => Promise<boolean>;
}

export function LibraryPickerDialog({
  open,
  libraryPath,
  outputPath,
  isAvailable,
  isConfigured,
  error,
  pickerAvailable,
  busy,
  onClose,
  onPickLibrary,
  onPickOutput,
  onSave,
}: LibraryPickerDialogProps) {
  const { t } = useI18n();
  const [draftLibraryPath, setDraftLibraryPath] = useState(libraryPath);
  const [draftOutputPath, setDraftOutputPath] = useState(outputPath);
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setDraftLibraryPath(libraryPath);
      setDraftOutputPath(outputPath);
      setLocalError(null);
    }
  }, [libraryPath, open, outputPath]);

  if (!open) {
    return null;
  }

  const statusTone = isAvailable ? "text-[hsl(var(--success-fg))]" : "text-[hsl(var(--warning-fg))]";
  const statusLabel = !isConfigured
    ? t("libraryPicker.noLibrarySelected")
    : isAvailable
      ? t("libraryPicker.connected")
      : t("libraryPicker.disconnected");

  async function handlePickLibrary() {
    const pickedPath = await onPickLibrary();
    if (pickedPath) {
      setDraftLibraryPath(pickedPath);
      setLocalError(null);
    }
  }

  async function handlePickOutput() {
    const pickedPath = await onPickOutput();
    if (pickedPath) {
      setDraftOutputPath(pickedPath);
      setLocalError(null);
    }
  }

  async function handleSave() {
    const trimmedLibrary = draftLibraryPath.trim();
    const trimmedOutput = draftOutputPath.trim();

    if (!trimmedLibrary) {
      setLocalError(t("libraryPicker.errors.enterLibrary"));
      return;
    }

    if (!trimmedOutput) {
      setLocalError(t("libraryPicker.errors.enterOutput"));
      return;
    }

    const saved = await onSave(trimmedLibrary, trimmedOutput);
    if (saved) {
      onClose();
    }
  }

  return (
    <div className="app-modal-overlay fixed inset-0 z-50 flex items-center justify-center px-4 py-6">
      <Panel className="app-modal-panel w-full max-w-[840px] p-0">
        <div className="flex items-center justify-between border-b border-border-soft/75 px-5 py-4">
          <div>
            <h2 className="text-[15px] font-semibold tracking-tight text-[hsl(var(--text-strong))]">
              {t("libraryPicker.title")}
            </h2>
            <p className="mt-1 text-[12px] text-muted-foreground">
              {t("libraryPicker.subtitle")}
            </p>
          </div>
          <button
            className="inline-flex h-8 w-8 items-center justify-center rounded-full text-muted-foreground transition hover:bg-surface-subtle/75 hover:text-[hsl(var(--text-strong))]"
            type="button"
            onClick={onClose}
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-4 px-5 py-5">
          <div className="flex items-center justify-between rounded-2xl border border-border-soft/75 bg-surface-subtle/85 px-4 py-3">
            <div className="min-w-0">
              <p className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">{t("libraryPicker.status")}</p>
              <p className={cn("mt-1 text-[13px] font-medium", statusTone)}>{statusLabel}</p>
            </div>
            <div className="min-w-0 text-right text-[12px] text-muted-foreground">
              {error ?? t("libraryPicker.fallbackStatusDetail")}
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <label className="block">
              <span className="mb-2 block text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
                {t("libraryPicker.inputLabel")}
              </span>
              <input
                className="app-control h-12 w-full rounded-2xl px-4 text-[13px] transition"
                placeholder={t("libraryPicker.inputPlaceholder")}
                value={draftLibraryPath}
                onChange={(event) => setDraftLibraryPath(event.target.value)}
              />
              <button
                className="app-button-secondary mt-3 inline-flex h-11 items-center justify-center gap-2 rounded-2xl px-4 text-[13px] transition disabled:cursor-not-allowed disabled:opacity-50"
                disabled={!pickerAvailable || busy}
                type="button"
                onClick={() => void handlePickLibrary()}
              >
                <FolderSearch className="h-4 w-4" />
                {t("libraryPicker.chooseMusicFolder")}
              </button>
            </label>

            <label className="block">
              <span className="mb-2 block text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
                {t("libraryPicker.outputLabel")}
              </span>
              <input
                className="app-control h-12 w-full rounded-2xl px-4 text-[13px] transition"
                placeholder={t("libraryPicker.outputPlaceholder")}
                value={draftOutputPath}
                onChange={(event) => setDraftOutputPath(event.target.value)}
              />
              <button
                className="app-button-secondary mt-3 inline-flex h-11 items-center justify-center gap-2 rounded-2xl px-4 text-[13px] transition disabled:cursor-not-allowed disabled:opacity-50"
                disabled={!pickerAvailable || busy}
                type="button"
                onClick={() => void handlePickOutput()}
              >
                <FolderOutput className="h-4 w-4" />
                {t("libraryPicker.chooseOutputFolder")}
              </button>
            </label>
          </div>

          {localError ? <p className="text-[12px] text-[hsl(var(--danger-fg))]">{localError}</p> : null}

          <div className="flex flex-wrap items-center gap-3">
            <button
              className="app-button-primary inline-flex h-11 items-center justify-center rounded-2xl px-5 text-[13px] font-semibold transition disabled:cursor-not-allowed disabled:opacity-50"
              disabled={busy}
              type="button"
              onClick={() => void handleSave()}
            >
              {t("libraryPicker.applyFolders")}
            </button>
            <button
              className="app-button-secondary inline-flex h-11 items-center justify-center rounded-2xl px-4 text-[13px] transition"
              type="button"
              onClick={onClose}
            >
              {t("common.cancel")}
            </button>
          </div>
        </div>
      </Panel>
    </div>
  );
}
