import type { Role } from "../api/types";

export const ROLE_LABELS: Record<Role, string> = {
  agency_admin: "Admin",
  agency_member: "Team member",
  client_user: "Client",
};
