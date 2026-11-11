import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { StaffComment } from "../../api/types";
import { fakeApi, renderWithSession } from "../../test/fakeSession";
import { CommentsSection, commentBadge } from "./CommentsSection";

const comment = (over: Partial<StaffComment>): StaffComment => ({
  id: "c1", task_id: "t1", body: "hi", visibility: "internal", visible_to_client: false,
  author_user_id: "u", author_name: "Mark", created_at: "2026-11-10T10:00:00Z", ...over,
});

describe("commentBadge", () => {
  it("says exactly what the client sees", () => {
    expect(commentBadge(comment({ visibility: "client", visible_to_client: true })).label).toBe("Visible to client");
    expect(commentBadge(comment({ visibility: "client", visible_to_client: false })).label).toBe("Hidden: task is internal");
    expect(commentBadge(comment({ visibility: "internal" })).label).toBe("Internal note");
  });
});

describe("CommentsSection", () => {
  it("defaults new comments to internal and goes back to internal after posting", async () => {
    const api = fakeApi();
    renderWithSession(<CommentsSection taskId="t1" taskVisibility="client" />, api);
    const user = userEvent.setup();

    expect(screen.getByLabelText("Internal note")).toBeChecked();
    await user.type(screen.getByLabelText("Comment"), "note to self");
    await user.click(screen.getByRole("button", { name: "Post comment" }));
    expect(api.comments.create).toHaveBeenLastCalledWith("t1", "note to self", "internal");

    await user.click(screen.getByLabelText("Reply to client"));
    await user.type(screen.getByLabelText("Comment"), "v3 is ready");
    await user.click(screen.getByRole("button", { name: "Post comment" }));
    expect(api.comments.create).toHaveBeenLastCalledWith("t1", "v3 is ready", "client");
    await waitFor(() => expect(screen.getByLabelText("Internal note")).toBeChecked());
  });

  it("warns that a client reply on an internal task stays hidden", async () => {
    renderWithSession(<CommentsSection taskId="t1" taskVisibility="internal" />, fakeApi());
    await userEvent.setup().click(screen.getByLabelText("Reply to client"));
    expect(screen.getByText(/client won't see this comment/)).toBeInTheDocument();
  });
});
