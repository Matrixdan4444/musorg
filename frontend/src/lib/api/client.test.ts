import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, getJson } from "@/lib/api/client";

function jsonResponse(body: unknown, init?: { ok?: boolean; status?: number }) {
  return {
    ok: init?.ok ?? true,
    status: init?.status ?? 200,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as Response;
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("getJson", () => {
  it("returns the parsed JSON body on success", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ value: 42 })));
    await expect(getJson<{ value: number }>("/thing")).resolves.toEqual({ value: 42 });
  });

  it("throws an ApiError carrying the status on a non-ok response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ detail: "nope" }, { ok: false, status: 404 })),
    );
    await expect(getJson("/missing")).rejects.toMatchObject({
      name: "ApiError",
      status: 404,
    });
  });

  it("aborts and throws a timeout ApiError when the request stalls", async () => {
    // fetch that rejects with AbortError once its signal fires.
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_input: RequestInfo, init?: RequestInit) =>
          new Promise((_resolve, reject) => {
            init?.signal?.addEventListener("abort", () => {
              reject(new DOMException("aborted", "AbortError"));
            });
          }),
      ),
    );

    const promise = getJson("/slow", { timeoutMs: 50 });
    const assertion = expect(promise).rejects.toBeInstanceOf(ApiError);
    await assertion;
  });
});
