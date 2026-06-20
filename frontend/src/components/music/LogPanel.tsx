import { AnimatePresence, motion } from "framer-motion";
import { memo, useEffect, useMemo, useRef, useState } from "react";
import { ModalPortal } from "@/components/ModalPortal";
import { Panel } from "@/components/Panel";
import { useLogsStream } from "@/hooks/useLogsStream";
import { useI18n } from "@/i18n/useI18n";
import { useAppMotion } from "@/lib/motion";
import { translateLogMessage, translateLogSource } from "@/lib/ui-copy";
import type { LogEntry, LogStep } from "@/types/music";

const ROW_HEIGHT = 38;

interface LogPanelProps {
  developerMode: boolean;
  open: boolean;
  onOpen: () => void;
  onClose: () => void;
}

export function LogPanel({ developerMode, open, onOpen, onClose }: LogPanelProps) {
  const { t } = useI18n();
  const appMotion = useAppMotion();
  const { logs, steps, status, sessionState, paused, activeRunId, setPaused, clearVisible } = useLogsStream(developerMode, null);
  const [severityFilter, setSeverityFilter] = useState("all");
  const [sourceFilter, setSourceFilter] = useState("all");
  const [channelFilter, setChannelFilter] = useState<"activity" | "all" | "diagnostic">("activity");

  const filteredLogs = useMemo(() => {
    return logs.filter((entry) => {
      if (channelFilter === "activity" && entry.channel !== "activity") {
        return false;
      }
      if (channelFilter === "diagnostic" && entry.channel !== "diagnostic") {
        return false;
      }
      if (severityFilter !== "all" && entry.severity !== severityFilter) {
        return false;
      }
      if (sourceFilter !== "all" && entry.source !== sourceFilter) {
        return false;
      }
      return true;
    });
  }, [logs, severityFilter, sourceFilter]);

  const sources = useMemo(() => {
    return Array.from(new Set(logs.map((entry) => entry.source))).sort();
  }, [logs]);

  return (
    <>
      <Panel className="flex h-full min-h-[240px] min-w-0 flex-col overflow-hidden px-4 py-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-[14px] font-semibold tracking-tight text-[hsl(var(--text-strong))]">
              {t("logs.title")}
            </p>
            <p className="mt-1 text-[12px] text-muted-foreground">
              {status === "connected"
                ? (
                  activeRunId
                    ? t("logs.streamingRun", { runId: activeRunId.slice(0, 8) })
                    : sessionState === "RUN_COMPLETE"
                      ? t("logs.completed")
                      : t("logs.noActiveRun")
                )
                : t("logs.waiting")}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              className="app-button-secondary rounded-xl px-3 py-2 text-[12px]"
              type="button"
              onClick={() => setPaused(!paused)}
            >
              {paused ? t("logs.resume") : t("logs.pause")}
            </button>
            <button
              className="app-button-secondary rounded-xl px-3 py-2 text-[12px]"
              type="button"
              onClick={() => clearVisible()}
            >
              {t("logs.clearVisible")}
            </button>
            <button
              className="app-button-secondary rounded-xl px-3 py-2 text-[12px]"
              type="button"
              onClick={onOpen}
            >
              {t("logs.viewFull")}
            </button>
          </div>
        </div>

        <div className="mt-4 grid gap-3 lg:grid-cols-5">
          {steps.map((step, index) => (
            <div key={step.id} className="min-w-0">
              <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-full border border-[hsl(var(--info-border)/0.48)] bg-info/65 text-[11px] text-info-foreground">
                  {index + 1}
                </div>
                <div className="min-w-0">
                  <p className="truncate text-[12px] font-medium text-[hsl(var(--text-strong))]">
                    {translateStepTitle(step, t)}
                  </p>
                  <p className="text-[12px] text-[hsl(var(--success-fg))]">{translateStepStatus(step.status, t)}</p>
                </div>
              </div>
            </div>
          ))}
        </div>

        <LogToolbar
          severityFilter={severityFilter}
          sourceFilter={sourceFilter}
          channelFilter={channelFilter}
          developerMode={developerMode}
          sources={sources}
          onSeverityFilterChange={setSeverityFilter}
          onSourceFilterChange={setSourceFilter}
          onChannelFilterChange={setChannelFilter}
          t={t}
        />

        <div className="mt-4 min-h-0 flex-1 overflow-hidden rounded-[18px] border border-border-soft/70 bg-surface-contrast/95">
          <VirtualizedLogList logs={filteredLogs} emptyLabel={t("logs.noLogs")} />
        </div>
      </Panel>

      <ModalPortal>
      <AnimatePresence>
      {open ? (
        <motion.div
          className="app-modal-overlay fixed inset-0 z-50 flex items-center justify-center px-4 py-6"
          variants={appMotion.overlayVariants}
          initial="hidden"
          animate="visible"
          exit="hidden"
          transition={appMotion.overlayTransition}
        >
          <motion.div
            className="flex h-[min(80vh,760px)] w-full max-w-[980px] min-h-0"
            variants={appMotion.modalVariants}
            initial="hidden"
            animate="visible"
            exit="hidden"
            transition={appMotion.modalTransition}
          >
          <Panel className="app-modal-panel glass-edge flex h-full w-full min-h-0 flex-col overflow-hidden p-0">
            <div className="flex items-center justify-between border-b border-border-soft/75 px-5 py-4">
              <div>
                <h2 className="text-[15px] font-semibold tracking-tight text-[hsl(var(--text-strong))]">
                  {t("logs.fullTitle")}
                </h2>
                <p className="mt-1 text-[12px] text-muted-foreground">
                  {t("logs.fullSubtitle")}
                </p>
              </div>
              <button
                className="inline-flex h-8 w-8 items-center justify-center rounded-full text-muted-foreground transition hover:bg-surface-subtle/75 hover:text-[hsl(var(--text-strong))]"
                type="button"
                onClick={onClose}
              >
                ×
              </button>
            </div>

            <div className="grid gap-4 border-b border-border-soft/75 px-5 py-4 md:grid-cols-5">
              {steps.map((step, index) => (
                <div key={step.id} className="min-w-0">
                  <div className="flex items-center gap-3">
                    <div className="flex h-9 w-9 items-center justify-center rounded-full border border-[hsl(var(--info-border)/0.48)] bg-info/65 text-[11px] text-info-foreground">
                      {index + 1}
                    </div>
                    <div className="min-w-0">
                      <p className="truncate text-[12px] font-medium text-[hsl(var(--text-strong))]">
                        {translateStepTitle(step, t)}
                      </p>
                      <p className="text-[12px] text-[hsl(var(--success-fg))]">{translateStepStatus(step.status, t)}</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <div className="px-5 py-4">
              <LogToolbar
                severityFilter={severityFilter}
                sourceFilter={sourceFilter}
                channelFilter={channelFilter}
                developerMode={developerMode}
                sources={sources}
                onSeverityFilterChange={setSeverityFilter}
                onSourceFilterChange={setSourceFilter}
                onChannelFilterChange={setChannelFilter}
                t={t}
              />
            </div>

            <div className="min-h-0 flex-1 overflow-hidden px-5 pb-5">
              <VirtualizedLogList logs={filteredLogs} emptyLabel={t("logs.noLogs")} />
            </div>
          </Panel>
          </motion.div>
        </motion.div>
      ) : null}
      </AnimatePresence>
      </ModalPortal>
    </>
  );
}

function LogToolbar({
  severityFilter,
  sourceFilter,
  channelFilter,
  developerMode,
  sources,
  onSeverityFilterChange,
  onSourceFilterChange,
  onChannelFilterChange,
  t,
}: {
  severityFilter: string;
  sourceFilter: string;
  channelFilter: "activity" | "all" | "diagnostic";
  developerMode: boolean;
  sources: string[];
  onSeverityFilterChange: (value: string) => void;
  onSourceFilterChange: (value: string) => void;
  onChannelFilterChange: (value: "activity" | "all" | "diagnostic") => void;
  t: (key: any, values?: Record<string, string | number>) => string;
}) {
  return (
    <div className="mt-4 flex flex-wrap items-center gap-2 text-[12px] text-muted-foreground">
      {developerMode ? (
        <select
          className="app-control rounded-xl px-2 py-2 text-[12px]"
          value={channelFilter}
          onChange={(event) => onChannelFilterChange(event.target.value as "activity" | "all" | "diagnostic")}
        >
          <option value="activity">{t("logs.filters.activityFeed")}</option>
          <option value="activity">{t("logs.filters.activityFeed")}</option>
          <option value="all">{t("logs.filters.activityAndDiagnostics")}</option>
          <option value="diagnostic">{t("logs.filters.developerDiagnostics")}</option>
        </select>
      ) : null}
      <select
        className="app-control rounded-xl px-2 py-2 text-[12px]"
        value={severityFilter}
        onChange={(event) => onSeverityFilterChange(event.target.value)}
      >
        <option value="all">{t("logs.filters.allSeverities")}</option>
        <option value="info">{t("logs.filters.info")}</option>
        <option value="success">{t("logs.filters.success")}</option>
        <option value="warning">{t("logs.filters.warnings")}</option>
        <option value="error">{t("logs.filters.errors")}</option>
      </select>
      <select
        className="app-control rounded-xl px-2 py-2 text-[12px]"
        value={sourceFilter}
        onChange={(event) => onSourceFilterChange(event.target.value)}
      >
        <option value="all">{t("logs.filters.allCategories")}</option>
        {sources.map((source) => (
          <option key={source} value={source}>{translateLogSource(source, t)}</option>
        ))}
      </select>
    </div>
  );
}

function VirtualizedLogList({ logs, emptyLabel }: { logs: LogEntry[]; emptyLabel: string }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [height, setHeight] = useState(240);
  const [stickToBottom, setStickToBottom] = useState(true);

  useEffect(() => {
    const element = containerRef.current;
    if (!element) {
      return;
    }

    const resizeObserver = new ResizeObserver(() => {
      setHeight(element.clientHeight);
    });
    resizeObserver.observe(element);
    setHeight(element.clientHeight);
    return () => resizeObserver.disconnect();
  }, []);

  useEffect(() => {
    const element = containerRef.current;
    if (!element || !stickToBottom) {
      return;
    }
    element.scrollTop = element.scrollHeight;
  }, [logs, stickToBottom]);

  const visibleCount = Math.ceil(height / ROW_HEIGHT) + 8;
  const startIndex = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - 4);
  const visibleLogs = logs.slice(startIndex, startIndex + visibleCount);
  const offsetY = startIndex * ROW_HEIGHT;

  return (
    <div
      ref={containerRef}
      className="h-full overflow-y-auto overflow-x-hidden px-4 py-3"
      onScroll={(event) => {
        const element = event.currentTarget;
        setScrollTop(element.scrollTop);
        setStickToBottom(element.scrollHeight - element.scrollTop - element.clientHeight < 48);
      }}
    >
      {logs.length === 0 ? (
        <div className="flex h-full items-center justify-center text-[12px] text-muted-foreground">
          {emptyLabel}
        </div>
      ) : (
        <div style={{ height: logs.length * ROW_HEIGHT, position: "relative" }}>
          <div style={{ transform: `translateY(${offsetY}px)` }} className="space-y-2 font-mono text-[12px] leading-6 text-[hsl(var(--text-base))]">
            {visibleLogs.map((log) => <LogRow key={log.id} log={log} />)}
          </div>
        </div>
      )}
    </div>
  );
}

const LogRow = memo(function LogRow({ log }: { log: LogEntry }) {
  const { t } = useI18n();
  const emoji = typeof log.payload?.emoji === "string" ? log.payload.emoji : "";
  return (
    <div className="flex h-[30px] items-center gap-4 border-b border-border-soft/60 pb-2 last:border-b-0">
      <span className="shrink-0 text-[hsl(var(--accent))]">{log.timestamp.slice(11, 19) || log.timestamp}</span>
      <span className={`shrink-0 ${severityClassName(log.severity)}`}>{log.severity.toUpperCase()}</span>
      <span className="shrink-0 text-muted-foreground">{translateLogSource(log.source, t)}:</span>
      <span className="min-w-0 truncate">{emoji ? `${emoji} ` : ""}{translateLogMessage(log, t)}</span>
    </div>
  );
});

function translateStepTitle(step: LogStep, t: (key: any, values?: Record<string, string | number>) => string) {
  const translated = t(`logs.steps.${step.id}` as never);
  return translated.startsWith("logs.steps.") ? step.title : translated;
}

function translateStepStatus(status: string, t: (key: any, values?: Record<string, string | number>) => string) {
  const translated = t(`logs.stepStatus.${status.toLowerCase()}` as never);
  return translated.startsWith("logs.stepStatus.") ? status : translated;
}

function severityClassName(severity: LogEntry["severity"]) {
  if (severity === "error") {
    return "text-[hsl(var(--danger-fg))]";
  }
  if (severity === "warning") {
    return "text-[hsl(var(--warning-fg))]";
  }
  if (severity === "success") {
    return "text-[hsl(var(--success-fg))]";
  }
  return "text-[hsl(var(--accent))]";
}
