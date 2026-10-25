import { useEffect, useState } from "react";
import App from "./App";
import { fetchMe, setSignedOutHandler, signOut, type User } from "./api";
import { SignIn } from "./components/AuthScreens";

/** Sign-in gate: the landing / sign-in screen, or the coach. */
export default function Root() {
  const [user, setUser] = useState<User | null | undefined>(undefined);

  useEffect(() => {
    setSignedOutHandler(() => setUser(null));
    fetchMe().then((r) => setUser(r.user)).catch(() => setUser(null));
  }, []);

  if (user === undefined) return <div className="auth-page" />;
  if (user === null) return <SignIn onSignedIn={(u) => { window.location.hash = "today"; setUser(u); }} />;
  return <App key={user.id} user={user} onSignOut={() => signOut().finally(() => setUser(null))} />;
}
