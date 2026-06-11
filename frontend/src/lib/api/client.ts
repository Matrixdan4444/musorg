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


export async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    const message = await readErrorMessage(response);
    throw new ApiError(message || `Request failed: ${response.status}`, response.status);
  }

  return (await response.json()) as T;
}


export async function postJson<TResponse, TBody>(path: string, body?: TBody): Promise<TResponse> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: body === undefined ? null : JSON.stringify(body),
  });

  if (!response.ok) {
    const message = await readErrorMessage(response);
    throw new ApiError(message || `Request failed: ${response.status}`, response.status);
  }

  return (await response.json()) as TResponse;
}


export async function putJson<TResponse, TBody>(path: string, body?: TBody): Promise<TResponse> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "PUT",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: body === undefined ? null : JSON.stringify(body),
  });

  if (!response.ok) {
    const message = await readErrorMessage(response);
    throw new ApiError(message || `Request failed: ${response.status}`, response.status);
  }

  return (await response.json()) as TResponse;
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
