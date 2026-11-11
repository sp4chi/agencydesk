// Mirrors the backend's Pydantic response models (backend/app/schemas/).
// Staff and client shapes are separate types, like on the server.

export type Role = "agency_admin" | "agency_member" | "client_user";
export type LoginKind = "staff" | "client";

export interface MembershipOption {
  agency_id: string;
  agency_name: string;
  role: Role;
  client_name: string | null;
}

export interface LoginResponse {
  identity_token: string;
  memberships: MembershipOption[];
}

export interface SessionResponse {
  session_token: string;
  expires_in: number;
  membership: MembershipOption;
}

export interface Me {
  user: { id: string; email: string; name: string };
  agency: { id: string; name: string };
  role: Role;
  client: { id: string; name: string } | null;
}
