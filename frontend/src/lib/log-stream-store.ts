import { getLogs, logsWebSocketUrl } from "@/lib/api/music";
import { devLog } from "@/lib/dev-log";
import type { LogEntry, LogStep, RuntimeSessionState } from "@/types/music";

const MAX_LOGS_PER_RUN = 1000;
const LOG_SEGMENT_SIZE = 200;
const MATCHING_PROGRESS_EVENT_TYPES = new Set([
  "album_processing_started",
  "metadata_match",
  "provider_fallback",
  "fallback_triggered",
  "issue_detected",
  "metadata_resolved",
]);
const MATCHING_PHASE_STARTED = "matching_phase_started";
const MATCHING_PHASE_COMPLETED = "matching_phase_completed";

function shouldPromoteMatchingFromActivity(entry: LogEntry, stage: string) {
  if (entry.type === MATCHING_PHASE_STARTED) {
    return true;
  }
  if (stage === "metadata_stage" && MATCHING_PROGRESS_EVENT_TYPES.has(entry.type)) {
    return true;
  }
  if (entry.type !== "log" || entry.channel !== "activity") {
    return false;
  }
  if (entry.source === "Deezer" || entry.source === "MusicBrainz") {
    return true;
  }
  if (entry.source !== "Metadata") {
    return false;
  }
  return entry.message.startsWith("Matching album metadata");
}

function shouldIgnoreInternalStageTransition(currentSteps: LogStep[], entry: LogEntry, stage: string) {
  if (stage === "group_by_album" && (entry.type === "stage_started" || entry.type === "stage_completed" || entry.type === "stage_finished")) {
    return true;
  }
  if (
    stage === "metadata_stage"
    && entry.type === "stage_started"
    && currentSteps.some((step) => step.id === "group_by_album" && step.status === "Running")
  ) {
    return true;
  }
  if (stage === "metadata_stage" && (entry.type === "stage_completed" || entry.type === "stage_finished")) {
    return currentSteps.some((step) => step.id === "organize_stage" && (step.status === "Running" || step.status === "Complete"));
  }
  return false;
}

export type LogStreamStatus = "idle" | "connecting" | "connected" | "disconnected";

interface LogRunBuffer {
  segments: LogEntry[][];
  size: number;
  seenIds: Set<string>;
  lastEventId: string | null;
  version: number;
}

interface LogStreamState {
  status: LogStreamStatus;
  sessionState: RuntimeSessionState;
  currentRunId: string | null;
  activeRunId: string | null;
  lastCompletedRunId: string | null;
  currentSteps: LogStep[];
  runVersions: Record<string, number>;
  paused: boolean;
}

type Listener = () => void;
type EventListener = (event: LogEntry) => void;

function createRunBuffer(): LogRunBuffer {
  return {
    segments: [],
    size: 0,
    seenIds: new Set(),
    lastEventId: null,
    version: 0,
  };
}

function createEmptySteps(): LogStep[] {
  return [
    { id: "scan_stage", title: "Scanning", status: "Idle" },
    { id: "metadata_stage", title: "Reading Metadata", status: "Idle" },
    { id: "group_by_album", title: "Matching", status: "Idle" },
    { id: "organize_stage", title: "Organizing", status: "Idle" },
    { id: "done", title: "All done", status: "Idle" },
  ];
}

function createStartingSteps(): LogStep[] {
  return createEmptySteps().map((step) => (
    step.id === "scan_stage" ? { ...step, status: "Running" } : step
  ));
}

class LogStreamStore {
  private state: LogStreamState = {
    status: "idle",
    sessionState: "NO_ACTIVE_RUN",
    currentRunId: null,
    activeRunId: null,
    lastCompletedRunId: null,
    currentSteps: createEmptySteps(),
    runVersions: {},
    paused: false,
  };

  private listeners = new Set<Listener>();
  private eventListeners = new Set<EventListener>();
  private socket: WebSocket | null = null;
  private reconnectTimer: number | null = null;
  private developerMode = false;
  private bootstrapLoaded = false;
  private buffersByRun = new Map<string, LogRunBuffer>();
  private frozenBuffersByRun: Map<string, LogRunBuffer> | null = null;

  subscribe = (listener: Listener) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  subscribeToEvents = (listener: EventListener) => {
    this.eventListeners.add(listener);
    return () => this.eventListeners.delete(listener);
  };

  getSnapshot = () => this.state;

  getLogs(runId: string): LogEntry[] {
    const source = this.state.paused && this.frozenBuffersByRun ? this.frozenBuffersByRun : this.buffersByRun;
    const buffer = source.get(runId);
    if (!buffer) {
      return [];
    }
    return buffer.segments.flat();
  }

  private emit() {
    for (const listener of this.listeners) {
      listener();
    }
  }

  private commitState() {
    this.state = {
      ...this.state,
      runVersions: { ...this.state.runVersions },
    };
    this.emit();
  }

  private setState(next: Partial<LogStreamState>) {
    this.state = { ...this.state, ...next };
    this.emit();
  }

  async ensureConnected(developerMode: boolean) {
    this.developerMode = developerMode;
    if (!this.bootstrapLoaded) {
      this.bootstrapLoaded = true;
      try {
        const payload = await getLogs();
        const bootstrapRunId = payload.activeRunId || null;
        if (bootstrapRunId) {
          this.replaceRunLogs(bootstrapRunId, payload.logs.slice(-MAX_LOGS_PER_RUN));
          this.state.currentRunId = bootstrapRunId;
          this.state.activeRunId = bootstrapRunId;
          this.state.sessionState = payload.sessionState;
          this.state.currentSteps = payload.steps.length > 0 ? payload.steps : createStartingSteps();
          this.state.runVersions[bootstrapRunId] = this.currentBuffer(bootstrapRunId).version;
        } else {
          this.state.currentRunId = null;
          this.state.activeRunId = null;
          this.state.sessionState = payload.sessionState;
          this.state.currentSteps = payload.steps.length > 0 ? payload.steps : createEmptySteps();
        }
        this.state.lastCompletedRunId = null;
        this.commitState();
      } catch {
        // best-effort bootstrap
      }
    }

    if (this.socket || this.state.status === "connecting") {
      return;
    }

    const runId = this.state.activeRunId;
    const lastEventId = runId ? this.currentBuffer(runId).lastEventId : null;

    this.setState({ status: "connecting" });
    const socket = new WebSocket(logsWebSocketUrl(runId, lastEventId));
    this.socket = socket;

    socket.onopen = () => {
      this.setState({ status: "connected" });
      devLog(this.developerMode, "WebSocket connected");
    };

    socket.onmessage = (event) => {
      let payload: LogEntry;
      try {
        payload = JSON.parse(event.data) as LogEntry;
      } catch (error) {
        // A single malformed frame must not tear down the whole stream.
        devLog(this.developerMode, "Failed to parse log stream message", { error: String(error) });
        return;
      }
      if (payload.type === "connection") {
        const connectionPayload = (payload.payload as {
          activeRunId?: string | null;
          sessionState?: RuntimeSessionState;
        } | null);
        const activeRunId = String(connectionPayload?.activeRunId || "") || null;
        const reportedSessionState = connectionPayload?.sessionState ?? (activeRunId ? "RUN_PROGRESS" : "NO_ACTIVE_RUN");
        const sessionState = !activeRunId && this.state.currentRunId && this.state.sessionState === "RUN_COMPLETE"
          ? "RUN_COMPLETE"
          : reportedSessionState;
        if (activeRunId && this.state.currentRunId !== activeRunId) {
          this.state.currentRunId = activeRunId;
          this.state.currentSteps = createStartingSteps();
          this.state.sessionState = sessionState;
        } else if (!activeRunId && !this.state.currentRunId) {
          this.state.currentSteps = createEmptySteps();
          this.state.sessionState = sessionState;
        }
        this.setState({ activeRunId, sessionState });
        devLog(this.developerMode, "Frontend received connection state", payload);
        return;
      }
      devLog(this.developerMode, payload.type === "log" ? "websocket_log_receive" : "websocket_receive", payload);
      for (const listener of this.eventListeners) {
        listener(payload);
      }
      this.appendLog(payload);
    };

    socket.onclose = () => {
      this.socket = null;
      this.setState({ status: "disconnected" });
      devLog(this.developerMode, "WebSocket disconnected");
      this.scheduleReconnect();
    };

    socket.onerror = () => {
      socket.close();
    };
  }

  private scheduleReconnect() {
    if (this.reconnectTimer !== null) {
      return;
    }
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      devLog(this.developerMode, "Reconnected to log stream");
      void this.ensureConnected(this.developerMode);
    }, 1500);
  }

  /**
   * Tear down the live connection: cancel any pending reconnect and close the
   * socket without triggering the auto-reconnect path. Safe to call repeatedly.
   */
  disconnect() {
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    const socket = this.socket;
    if (socket) {
      this.socket = null;
      // Detach handlers first so onclose does not schedule a reconnect.
      socket.onopen = null;
      socket.onmessage = null;
      socket.onclose = null;
      socket.onerror = null;
      socket.close();
    }
    this.setState({ status: "idle" });
  }

  setPaused(paused: boolean) {
    this.state.paused = paused;
    this.frozenBuffersByRun = paused ? new Map(this.buffersByRun) : null;
    this.commitState();
  }

  clearVisible(runId: string | null) {
    const targetRunId = runId || this.state.currentRunId;
    if (!targetRunId) {
      this.state.sessionState = "RUN_CLEARED";
      this.state.currentSteps = createEmptySteps();
      this.commitState();
      return;
    }
    this.replaceRunLogs(targetRunId, []);
    if (targetRunId === this.state.currentRunId) {
      this.state.currentRunId = null;
      this.state.activeRunId = null;
      this.state.sessionState = "RUN_CLEARED";
      this.state.currentSteps = createEmptySteps();
    }
    this.commitState();
  }

  private currentBuffer(runId: string): LogRunBuffer {
    let buffer = this.buffersByRun.get(runId);
    if (!buffer) {
      buffer = createRunBuffer();
      this.buffersByRun.set(runId, buffer);
    }
    return buffer;
  }

  private replaceRunLogs(runId: string, logs: LogEntry[]) {
    const buffer = createRunBuffer();
    for (const entry of logs) {
      this.pushEntry(buffer, entry);
    }
    this.buffersByRun.set(runId, buffer);
    this.state.runVersions[runId] = buffer.version;
  }

  private appendLog(entry: LogEntry) {
    const runId = entry.runId || this.state.activeRunId || "latest";
    const isVisibleFeedEntry = entry.channel === "activity" || entry.channel === "diagnostic";
    if (entry.type === "run_started" && runId && this.state.currentRunId !== runId) {
      this.state.currentRunId = runId;
      this.state.activeRunId = runId;
      this.state.sessionState = "RUN_START";
      this.state.currentSteps = createStartingSteps();
    }

    if (isVisibleFeedEntry) {
      const buffer = this.currentBuffer(runId);
      if (buffer.seenIds.has(entry.id)) {
        return;
      }
      this.pushEntry(buffer, entry);
      this.state.runVersions[runId] = buffer.version;
    }

    if (runId && runId === this.state.currentRunId) {
      this.state.sessionState = nextSessionStateForEvent(this.state.sessionState, entry);
      this.state.currentSteps = nextStepsForEvent(this.state.currentSteps, entry);
    }
    if (entry.type === "pipeline_completed" || entry.type === "run_completed" || entry.type === "run_failed" || entry.type === "run_finished") {
      this.state.lastCompletedRunId = runId;
      if (runId === this.state.activeRunId) {
        this.state.activeRunId = null;
      }
    }
    if (isVisibleFeedEntry) {
      devLog(this.developerMode, entry.type === "log" ? "websocket_log_append" : "frontend_append", {
        runId,
        eventType: entry.type,
        source: entry.source,
        message: entry.message,
      });
    }
    this.commitState();
  }

  private pushEntry(buffer: LogRunBuffer, entry: LogEntry) {
    const lastSegment = buffer.segments[buffer.segments.length - 1];
    if (!lastSegment || lastSegment.length >= LOG_SEGMENT_SIZE) {
      buffer.segments.push([entry]);
    } else {
      lastSegment.push(entry);
    }
    buffer.size += 1;
    buffer.seenIds.add(entry.id);
    buffer.lastEventId = entry.id;
    while (buffer.size > MAX_LOGS_PER_RUN && buffer.segments.length > 0) {
      const oldestSegment = buffer.segments[0];
      if (!oldestSegment) {
        break;
      }
      const removed = oldestSegment.shift();
      if (removed) {
        buffer.size -= 1;
        buffer.seenIds.delete(removed.id);
      }
      if (oldestSegment.length === 0) {
        buffer.segments.shift();
      }
    }
    buffer.version += 1;
  }
}

function nextStepsForEvent(currentSteps: LogStep[], entry: LogEntry): LogStep[] {
  if (entry.channel === "diagnostic") {
    return currentSteps;
  }
  const stage = String(entry.stage || (entry.payload as { stage?: string } | null)?.stage || "");
  const next = currentSteps.map((step) => ({ ...step }));
  const orderedStages = ["scan_stage", "metadata_stage", "group_by_album", "organize_stage"];

  if (entry.type === "run_started") {
    return createStartingSteps();
  }
  if (entry.type === "pipeline_completed" || entry.type === "run_completed" || entry.type === "run_finished") {
    return next.map((step) => (
      step.id === "done"
        ? { ...step, status: "Complete" }
        : orderedStages.includes(step.id)
          ? { ...step, status: "Complete" }
          : step
    ));
  }
  if (entry.type === "run_failed") {
    return next.map((step) => (
      step.id === "done"
        ? { ...step, status: "Failed" }
        : step.status === "Running"
          ? { ...step, status: "Complete" }
          : step
    ));
  }
  if (shouldPromoteMatchingFromActivity(entry, stage)) {
    for (const step of next) {
      if (step.id === "scan_stage" || step.id === "metadata_stage") {
        step.status = "Complete";
      } else if (step.id === "group_by_album") {
        step.status = "Running";
      } else if (step.id === "organize_stage" || step.id === "done") {
        step.status = "Idle";
      }
    }
    return next;
  }

  if (entry.type === MATCHING_PHASE_COMPLETED) {
    for (const step of next) {
      if (step.id === "scan_stage" || step.id === "metadata_stage" || step.id === "group_by_album") {
        step.status = "Complete";
      } else if (step.id === "organize_stage") {
        step.status = "Running";
      } else if (step.id === "done") {
        step.status = "Idle";
      }
    }
    return next;
  }

  if (!stage) {
    return next;
  }

  if (shouldIgnoreInternalStageTransition(currentSteps, entry, stage)) {
    return next;
  }

  const stageIndex = next.findIndex((step) => step.id === stage);
  if (stageIndex === -1) {
    return next;
  }

  if (entry.type === "stage_started") {
    for (let index = 0; index < next.length; index += 1) {
      const step = next[index];
      if (!step) continue;
      if (index < stageIndex && step.id !== "done") {
        step.status = "Complete";
      } else if (index === stageIndex) {
        step.status = "Running";
      } else if (index > stageIndex && step.id !== "done") {
        step.status = "Idle";
      }
    }
    return next;
  }

  if (entry.type === "stage_completed" || entry.type === "stage_finished") {
    const step = next[stageIndex];
    if (step) {
      step.status = "Complete";
    }
    const nextStage = orderedStages[orderedStages.indexOf(stage) + 1];
    if (nextStage) {
      const nextStageEntry = next.find((candidate) => candidate.id === nextStage);
      if (nextStageEntry) {
        nextStageEntry.status = "Running";
      }
    } else {
      const done = next.find((candidate) => candidate.id === "done");
      if (done) {
        done.status = "Complete";
      }
    }
    return next;
  }

  return next;
}

function nextSessionStateForEvent(currentState: RuntimeSessionState, entry: LogEntry): RuntimeSessionState {
  if (entry.type === "run_started") {
    return "RUN_START";
  }
  if (
    entry.type === "stage_started"
    || entry.type === "stage_completed"
    || entry.type === "stage_finished"
    || entry.type === MATCHING_PHASE_STARTED
    || entry.type === MATCHING_PHASE_COMPLETED
  ) {
    return "RUN_PROGRESS";
  }
  if (entry.type === "pipeline_completed" || entry.type === "run_completed" || entry.type === "run_finished" || entry.type === "run_failed") {
    return "RUN_COMPLETE";
  }
  return currentState;
}

export const logStreamStore = new LogStreamStore();

if (typeof window !== "undefined") {
  // Release the socket and any pending reconnect timer when the page unloads
  // (e.g. the ErrorBoundary's reload) instead of leaking them.
  window.addEventListener("pagehide", () => logStreamStore.disconnect());
}
