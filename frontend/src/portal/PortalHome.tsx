// Client portal home. Projects, tasks, comments and file approvals arrive in step 16.

import { useActiveSession } from "../auth/SessionProvider";
import { AppHeader } from "../shared/AppHeader";

export function PortalHome() {
  const { session } = useActiveSession();
  return (
    <>
      <AppHeader />
      <main className="page">
        <h1>Welcome, {session.me.user.name}</h1>
        <p className="muted">
          {session.me.client?.name} at {session.me.agency.name}
        </p>
      </main>
    </>
  );
}
