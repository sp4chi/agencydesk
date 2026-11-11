// Tokens live in memory only. Any script running on the page can read
// localStorage, sessionStorage and non-httpOnly cookies, so the app must not
// use them. This fails if any source file starts to.

import { describe, expect, it } from "vitest";

const sources = import.meta.glob(["./**/*.{ts,tsx}", "!./**/*.test.{ts,tsx}"], {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

describe("token storage", () => {
  it("finds the source files", () => {
    expect(Object.keys(sources)).toContain("./api/client.ts");
  });

  // Matches actual use (localStorage.getItem, window["sessionStorage"], document.cookie = ...),
  // not the words appearing in a comment.
  it.each([
    ["localStorage", /\blocalStorage\s*[.[]|["']localStorage["']/],
    ["sessionStorage", /\bsessionStorage\s*[.[]|["']sessionStorage["']/],
    ["document.cookie", /\bdocument\s*\.\s*cookie\b/],
    ["indexedDB", /\bindexedDB\s*[.[]/],
  ])("no source file uses %s", (_name, pattern) => {
    const offenders = Object.entries(sources)
      .filter(([, code]) => pattern.test(code))
      .map(([path]) => path);
    expect(offenders).toEqual([]);
  });

  it("only api/client.ts calls fetch", () => {
    const offenders = Object.entries(sources)
      .filter(([path, code]) => path !== "./api/client.ts" && /\bfetch\(/.test(code))
      .map(([path]) => path);
    expect(offenders).toEqual([]);
  });

  it("portal code never imports staff code (separate route trees)", () => {
    const offenders = Object.entries(sources)
      .filter(([path, code]) => path.startsWith("./portal/") && /from\s+["']\.\.\/staff\//.test(code))
      .map(([path]) => path);
    expect(offenders).toEqual([]);
    expect(Object.keys(sources).some((path) => path.startsWith("./portal/"))).toBe(true);
  });

  it("portal code only uses the portal part of the API client", () => {
    const offenders = Object.entries(sources)
      .filter(([path, code]) => path.startsWith("./portal/") && /\bapi\.(?!portal\b)\w+/.test(code))
      .map(([path]) => path);
    expect(offenders).toEqual([]);
  });
});
