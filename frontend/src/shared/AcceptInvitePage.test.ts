import { describe, expect, it } from "vitest";

import { inviteTokenFromHash } from "./AcceptInvitePage";
import { safeReturnTo } from "./LoginPage";

describe("invite links", () => {
  it("reads the token from the URL fragment", () => {
    expect(inviteTokenFromHash("#token=abcdefghijklmnop")).toBe("abcdefghijklmnop");
    expect(inviteTokenFromHash("")).toBeNull();
    expect(inviteTokenFromHash("#token=short")).toBeNull();
  });
});

describe("safeReturnTo", () => {
  it("only allows returning to an invite link (no open redirect)", () => {
    expect(safeReturnTo({ returnTo: "/invite#token=abc" })).toBe("/invite#token=abc");
    for (const bad of ["https://evil.example", "//evil.example", "/", "/projects/1", 42]) {
      expect(safeReturnTo({ returnTo: bad })).toBeNull();
    }
    expect(safeReturnTo(null)).toBeNull();
  });
});
