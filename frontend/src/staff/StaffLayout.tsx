import { NavLink, Outlet } from "react-router-dom";

import { useActiveSession } from "../auth/SessionProvider";
import { AppHeader } from "../shared/AppHeader";

export function StaffLayout() {
  const { session } = useActiveSession();
  const isAdmin = session.me.role === "agency_admin";
  return (
    <>
      <AppHeader />
      <nav className="tabs page-nav" aria-label="Staff sections">
        <NavLink to="/" end>Projects</NavLink>
        {/* Hidden for non-admins as a convenience; the API refuses them anyway. */}
        {isAdmin && <NavLink to="/invites">Invites</NavLink>}
      </nav>
      <main className="page">
        <Outlet />
      </main>
    </>
  );
}
