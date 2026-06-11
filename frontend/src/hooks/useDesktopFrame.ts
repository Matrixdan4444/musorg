import { getRuntimeConfig } from "@/lib/runtime";

export function useDesktopFrame() {
  const runtime = getRuntimeConfig();

  return {
    host: runtime.hostKind,
    transport: "http",
    mode: runtime.mode,
  } as const;
}
