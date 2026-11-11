// Two separate route trees: the staff app at / and the client portal at
// /portal. Each has its own login and agency picker, and RequireSession
// keeps a staff session out of portal pages and vice versa (UX only; the
// backend enforces the real rules). /invite is public.

import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { RequireSession } from "./auth/RequireSession";
import { SessionProvider } from "./auth/SessionProvider";
import { PortalHome } from "./portal/PortalHome";
import { AcceptInvitePage } from "./shared/AcceptInvitePage";
import { AgencyPicker } from "./shared/AgencyPicker";
import { LoginPage } from "./shared/LoginPage";
import { InvitesPage } from "./staff/InvitesPage";
import { ProjectPage } from "./staff/ProjectPage";
import { ProjectsPage } from "./staff/ProjectsPage";
import { StaffLayout } from "./staff/StaffLayout";

export function App() {
  return (
    <SessionProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/invite" element={<AcceptInvitePage />} />

          {/* Staff app */}
          <Route path="/login" element={<LoginPage kind="staff" />} />
          <Route path="/select-agency" element={<AgencyPicker kind="staff" />} />
          <Route path="/" element={<RequireSession kind="staff"><StaffLayout /></RequireSession>}>
            <Route index element={<ProjectsPage />} />
            <Route path="projects/:projectId" element={<ProjectPage />} />
            <Route path="invites" element={<InvitesPage />} />
          </Route>

          {/* Client portal */}
          <Route path="/portal/login" element={<LoginPage kind="client" />} />
          <Route path="/portal/select-agency" element={<AgencyPicker kind="client" />} />
          <Route path="/portal" element={<RequireSession kind="client"><PortalHome /></RequireSession>} />

          <Route path="/portal/*" element={<Navigate to="/portal" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </SessionProvider>
  );
}
