import { getRuntimeConfig } from "@/lib/runtime";

const API_BASE_URL = getRuntimeConfig().apiBaseUrl;


export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}


// Default per-request timeout. Without this a stalled backend would hang the
// request (and any UI waiting on it) indefinitely.
const DEFAULT_TIMEOUT_MS = 30_000;

export interface RequestOptions {
  /** Caller-supplied abort signal; composed with the internal timeout. */
  signal?: AbortSignal;
  /** Override the default request timeout (ms). Pass 0 to disable. */
  timeoutMs?: number;
}

async function request<T>(path: string, init: RequestInit, options: RequestOptions = {}): Promise<T> {
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const timeoutController = timeoutMs > 0 ? new AbortController() : null;
  const timeoutId = timeoutController
    ? window.setTimeout(() => timeoutController.abort(), timeoutMs)
    : null;

  // Abort if either the caller's signal or our timeout fires.
  const signal = composeSignals(options.signal, timeoutController?.signal);

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, { ...init, signal: signal ?? null });
    if (!response.ok) {
      const message = await readErrorMessage(response);
      throw new ApiError(message || `Request failed: ${response.status}`, response.status);
    }
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError" && timeoutController?.signal.aborted) {
      throw new ApiError(`Request timed out after ${timeoutMs}ms`, 0);
    }
    throw error;
  } finally {
    if (timeoutId !== null) {
      window.clearTimeout(timeoutId);
    }
  }
}

function composeSignals(...signals: Array<AbortSignal | undefined>): AbortSignal | undefined {
  const present = signals.filter((value): value is AbortSignal => Boolean(value));
  if (present.length === 0) {
    return undefined;
  }
  if (present.length === 1) {
    return present[0];
  }
  const controller = new AbortController();
  for (const signal of present) {
    if (signal.aborted) {
      controller.abort();
      break;
    }
    signal.addEventListener("abort", () => controller.abort(), { once: true });
  }
  return controller.signal;
}

export async function getJson<T>(path: string, options?: RequestOptions): Promise<T> {
  return request<T>(path, { headers: { Accept: "application/json" } }, options);
}


export async function postJson<TResponse, TBody>(path: string, body?: TBody, options?: RequestOptions): Promise<TResponse> {
  return request<TResponse>(
    path,
    {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: body === undefined ? null : JSON.stringify(body),
    },
    options,
  );
}


export async function putJson<TResponse, TBody>(path: string, body?: TBody, options?: RequestOptions): Promise<TResponse> {
  return request<TResponse>(
    path,
    {
      method: "PUT",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: body === undefined ? null : JSON.stringify(body),
    },
    options,
  );
}


export function resolveApiUrl(path: string) {
  if (!path) {
    return "";
  }
  if (path.startsWith("http://") || path.startsWith("https://") || path.startsWith("data:")) {
    return path;
  }
  return `${API_BASE_URL}${path}`;
}


async function readErrorMessage(response: Response) {
  const text = await response.text();
  if (!text) {
    return "";
  }

  try {
    const payload = JSON.parse(text) as { detail?: string };
    return payload.detail || text;
  } catch {
    return text;
  }
}


export { API_BASE_URL };
