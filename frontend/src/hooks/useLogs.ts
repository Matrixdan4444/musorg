import { useEffect, useState } from "react";
import { getLogs } from "@/lib/api/music";
import type { LogsPayload } from "@/types/music";


const emptyLogs: LogsPayload = {
  activeRunId: null,
  sessionState: "NO_ACTIVE_RUN",
  steps: [
    { id: "scan_stage", title: "Scanning", status: "Idle" },
    { id: "metadata_stage", title: "Reading Metadata", status: "Idle" },
    { id: "group_by_album", title: "Matching", status: "Idle" },
    { id: "organize_stage", title: "Organizing", status: "Idle" },
    { id: "done", title: "All done", status: "Idle" },
  ],
  logs: [],
};


export function useLogs(refreshKey = 0) {
  const [data, setData] = useState<LogsPayload>(emptyLogs);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setLoading(true);
        setError(null);
        const payload = await getLogs();
        if (!cancelled) {
          setData(payload);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load logs.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void load();

    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  return { data, loading, error };
}
