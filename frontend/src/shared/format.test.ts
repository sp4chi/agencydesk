import { describe, expect, it } from "vitest";

import { formatDate, formatMinutes, groupByStatus } from "./format";

describe("format helpers", () => {
  it("groups tasks into every status column, empty ones included", () => {
    const groups = groupByStatus([{ status: "done" as const }, { status: "todo" as const }, { status: "done" as const }]);
    expect(Object.fromEntries(Object.entries(groups).map(([k, v]) => [k, v.length]))).toEqual({
      todo: 1, in_progress: 0, in_review: 0, done: 2,
    });
  });

  it("formats minutes as hours and minutes", () => {
    expect([formatMinutes(45), formatMinutes(60), formatMinutes(180), formatMinutes(90)]).toEqual(["45m", "1h", "3h", "1h 30m"]);
  });

  it("keeps date-only values on the same calendar day in any timezone", () => {
    expect(formatDate("2026-11-03")).toContain("3");
    expect(formatDate(null)).toBe("");
  });
});
