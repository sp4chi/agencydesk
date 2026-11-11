// Staff app home. Projects, task board and the rest arrive in step 15.

import { useActiveSession } from "../auth/SessionProvider";
import { AppHeader } from "../shared/AppHeader";
import { ROLE_LABELS } from "../shared/labels";

export function StaffHome() {
  const { session } = useActiveSession();
  return (
    <>
      <AppHeader />
      <main className="page">
        <h1>Welcome, {session.me.user.name}</h1>
        <p className="muted">
          Signed in to {session.me.agency.name} as {ROLE_LABELS[session.me.role]}.
        </p>
      </main>
    </>
  );
}
