import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { ClientFile } from "../api/types";
import { fakeApi, renderWithSession } from "../test/fakeSession";
import { PortalComments, PortalFiles } from "./PortalTaskPanel";

const file = (over: Partial<ClientFile> = {}): ClientFile => ({
  id: "f1", task_id: "t1", filename: "homepage-v2.fig", content_type: "application/octet-stream",
  size_bytes: 1024, approval_status: "pending", reviewed_at: null, created_at: "2026-11-10T10:00:00Z", ...over,
});

describe("PortalFiles", () => {
  it("lets the client approve or request changes, then refreshes", async () => {
    const api = fakeApi();
    api.portal.files.list.mockResolvedValueOnce([file()]).mockResolvedValue([file({ approval_status: "approved" })]);
    const onReviewed = vi.fn();
    renderWithSession(<PortalFiles taskId="t1" onReviewed={onReviewed} />, api, "client_user");
    const user = userEvent.setup();

    expect(await screen.findByText("Waiting for your review")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Approve" }));
    expect(api.portal.files.review).toHaveBeenCalledWith("f1", "approved");
    expect(await screen.findByText("You approved this")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve" })).toBeDisabled();
    expect(onReviewed).toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Request changes" }));
    expect(api.portal.files.review).toHaveBeenLastCalledWith("f1", "changes_requested");
  });

  it("shows the server's message when a review is refused", async () => {
    const api = fakeApi();
    api.portal.files.list.mockResolvedValue([file()]);
    const { ApiError } = await import("../api/client");
    api.portal.files.review.mockRejectedValue(new ApiError(404, "Not found"));
    renderWithSession(<PortalFiles taskId="t1" onReviewed={vi.fn()} />, api, "client_user");
    await userEvent.setup().click(await screen.findByRole("button", { name: "Approve" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Not found");
  });
});

describe("PortalComments", () => {
  it("has no visibility choice: a client's message always goes to the agency", async () => {
    const api = fakeApi();
    renderWithSession(<PortalComments taskId="t1" />, api, "client_user");
    const user = userEvent.setup();
    expect(screen.queryByRole("radio")).toBeNull();
    expect(screen.queryByText(/internal/i)).toBeNull();
    await user.type(screen.getByRole("textbox", { name: "Message" }), "Looks great");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(api.portal.comments.create).toHaveBeenCalledWith("t1", "Looks great"));
  });
});
