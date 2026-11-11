import { describe, expect, it } from "vitest";

import type { StaffTask } from "../../api/types";
import { changedFields } from "./TaskDetails";

const task: StaffTask = {
  id: "t", project_id: "p", title: "Mockups", description: "", status: "todo", priority: "medium",
  visibility: "internal", assignee_user_id: "mark", assignee_name: "Mark", due_date: null,
  created_by: "alice", created_at: "", updated_at: "",
};

describe("changedFields", () => {
  it("sends nothing when nothing changed", () => {
    expect(changedFields(task, { ...task })).toEqual({});
  });

  it("sends only the changed fields, including an explicit unassign", () => {
    expect(changedFields(task, { ...task, status: "done", assignee_user_id: null })).toEqual({
      status: "done",
      assignee_user_id: null,
    });
  });
});
