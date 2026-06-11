export type RuntimeMode = "dev" | "embedded" | "browser";
export type HostKind = "pywebview" | "browser";

export interface RuntimeConfig {
  mode: RuntimeMode;
  hostKind: HostKind;
  apiBaseUrl: string;
  frontendOrigin: string;
}


function readQueryConfig() {
  const params = new URLSearchParams(window.location.search);
  const apiOrigin = params.get("api_origin")?.trim() ?? "";
  const runtimeMode = params.get("runtime_mode")?.trim() ?? "";
  const hostKind = params.get("host_kind")?.trim() ?? "";

  return {
    apiOrigin,
    runtimeMode,
    hostKind,
  };
}


function resolveFrontendOrigin() {
  return window.location.origin === "null" ? "" : window.location.origin;
}


export function getRuntimeConfig(): RuntimeConfig {
  const query = readQueryConfig();
  const envApiBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim() ?? "";
  const frontendOrigin = resolveFrontendOrigin();
  const apiBaseUrl = query.apiOrigin || envApiBaseUrl || frontendOrigin || "http://127.0.0.1:8000";

  return {
    mode: query.runtimeMode === "embedded" || query.runtimeMode === "dev" ? query.runtimeMode : "browser",
    hostKind: query.hostKind === "pywebview" ? "pywebview" : "browser",
    apiBaseUrl,
    frontendOrigin,
  };
}
