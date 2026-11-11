import type { ApprovalStatus, TaskPriority, TaskStatus } from "../api/types";

export const STATUSES: TaskStatus[] = ["todo", "in_progress", "in_review", "done"];
export const PRIORITIES: TaskPriority[] = ["low", "medium", "high", "urgent"];

export const STATUS_LABELS: Record<TaskStatus, string> = {
  todo: "To do",
  in_progress: "In progress",
  in_review: "In review",
  done: "Done",
};

export const PRIORITY_LABELS: Record<TaskPriority, string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
  urgent: "Urgent",
};

export const APPROVAL_LABELS: Record<ApprovalStatus, string> = {
  pending: "Awaiting client review",
  approved: "Approved by client",
  changes_requested: "Client requested changes",
};

export function formatDate(iso: string | null): string {
  if (!iso) return "";
  // Date-only values ("2026-11-03") must not shift a day with the timezone.
  const date = /^\d{4}-\d{2}-\d{2}$/.test(iso) ? new Date(`${iso}T00:00:00`) : new Date(iso);
  return date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatMinutes(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h === 0) return `${m}m`;
  return m === 0 ? `${h}h` : `${h}h ${m}m`;
}

export function groupByStatus<T extends { status: TaskStatus }>(items: T[]): Record<TaskStatus, T[]> {
  const groups: Record<TaskStatus, T[]> = { todo: [], in_progress: [], in_review: [], done: [] };
  for (const item of items) groups[item.status].push(item);
  return groups;
}
