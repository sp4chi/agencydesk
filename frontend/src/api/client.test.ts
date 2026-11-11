import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, authApi, createApi, request } from "./client";

function mockFetch(status: number, body: unknown) {
  // A fresh Response per call: a body can only be read once.
  const fetchMock = vi.fn().mockImplementation(async () =>
    new Response(body === undefined ? null : JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function sentRequest(fetchMock: ReturnType<typeof vi.fn>) {
  const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
  return { url, init, headers: init.headers as Record<string, string> };
}

afterEach(() => vi.unstubAllGlobals());

describe("request", () => {
  it("goes through the /api proxy, sends the bearer token and never sends cookies", async () => {
    const fetchMock = mockFetch(200, { ok: true });
    await request("/me", { token: "tok-123" });
    const { url, init, headers } = sentRequest(fetchMock);
    expect(url).toBe("/api/me");
    expect(headers["Authorization"]).toBe("Bearer tok-123");
    expect(init.credentials).toBe("omit");
  });

  it("sends no Authorization header without a token", async () => {
    const fetchMock = mockFetch(200, {});
    await request("/health");
    expect(sentRequest(fetchMock).headers["Authorization"]).toBeUndefined();
  });

  it("turns FastAPI errors into ApiError with the server's message", async () => {
    mockFetch(401, { detail: "Invalid email or password" });
    await expect(request("/auth/login", { method: "POST", body: {} })).rejects.toMatchObject({
      status: 401,
      message: "Invalid email or password",
    });
  });

  it("uses the first validation message for 422s", async () => {
    mockFetch(422, { detail: [{ msg: "Field required" }, { msg: "other" }] });
    await expect(request("/x")).rejects.toMatchObject({ status: 422, message: "Field required" });
  });

  it("hides server details on 500s", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("Traceback ...", { status: 500 })));
    const error = await request("/x").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).message).toBe("Something went wrong. Please try again.");
  });

  it("returns undefined for 204 No Content", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    await expect(request("/x", { method: "DELETE" })).resolves.toBeUndefined();
  });
});

describe("authApi", () => {
  it("uses the staff or portal login endpoint", async () => {
    const fetchMock = mockFetch(200, { identity_token: "id", memberships: [] });
    await authApi.login("staff", "a@b.test", "pw");
    await authApi.login("client", "a@b.test", "pw");
    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      "/api/auth/login",
      "/api/auth/portal/login",
    ]);
  });

  it("selects an agency with the identity token", async () => {
    const fetchMock = mockFetch(200, {});
    await authApi.startSession("identity-tok", "agency-1");
    const { url, init, headers } = sentRequest(fetchMock);
    expect(url).toBe("/api/auth/session");
    expect(headers["Authorization"]).toBe("Bearer identity-tok");
    expect(JSON.parse(init.body as string)).toEqual({ agency_id: "agency-1" });
  });
});

describe("createApi", () => {
  it("signs out on 401 (expired token or removed membership)", async () => {
    mockFetch(401, { detail: "Not authenticated" });
    const onUnauthorized = vi.fn();
    await expect(createApi("tok", onUnauthorized).me()).rejects.toBeInstanceOf(ApiError);
    expect(onUnauthorized).toHaveBeenCalledOnce();
  });

  it("does not sign out on 403 or 404", async () => {
    const onUnauthorized = vi.fn();
    for (const status of [403, 404]) {
      mockFetch(status, { detail: "nope" });
      await expect(createApi("tok", onUnauthorized).me()).rejects.toMatchObject({ status });
    }
    expect(onUnauthorized).not.toHaveBeenCalled();
  });
});
