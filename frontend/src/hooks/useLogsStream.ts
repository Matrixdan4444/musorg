import { useEffect, useMemo, useSyncExternalStore } from "react";
import { logStreamStore } from "@/lib/log-stream-store";
import type { LogEntry, LogStep } from "@/types/music";

export function useLogsStream(developerMode: boolean, runId: string | null) {
  const snapshot = useSyncExternalStore(logStreamStore.subscribe, logStreamStore.getSnapshot);

  useEffect(() => {
    void logStreamStore.ensureConnected(developerMode);
  }, [developerMode]);

  const effectiveRunId = runId || snapshot.currentRunId || "latest";
  const runVersion = snapshot.runVersions[effectiveRunId] ?? 0;
  const logs = useMemo<LogEntry[]>(
    () => logStreamStore.getLogs(effectiveRunId),
    [effectiveRunId, runVersion],
  );
  const steps = useMemo<LogStep[]>(
    () => (runId && runId !== snapshot.currentRunId ? [] : snapshot.currentSteps),
    [runId, snapshot.currentRunId, snapshot.currentSteps],
  );

  return {
    status: snapshot.status,
    sessionState: snapshot.sessionState,
    paused: snapshot.paused,
    activeRunId: snapshot.activeRunId,
    logs,
    steps,
    runId: effectiveRunId,
    setPaused: (paused: boolean) => logStreamStore.setPaused(paused),
    clearVisible: () => logStreamStore.clearVisible(effectiveRunId),
  };
}
