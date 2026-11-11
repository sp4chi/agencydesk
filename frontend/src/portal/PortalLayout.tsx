import { NavLink, Outlet } from "react-router-dom";

import { AppHeader } from "../shared/AppHeader";

export function PortalLayout() {
  return (
    <>
      <AppHeader />
      <nav className="tabs page-nav" aria-label="Portal sections">
        <NavLink to="/portal" end>Projects</NavLink>
      </nav>
      <main className="page">
        <Outlet />
      </main>
    </>
  );
}
