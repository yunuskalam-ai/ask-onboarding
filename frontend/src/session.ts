// The signed-in user, as seen by any component (useAuth), plus small role
// helpers. The provider that fills this in lives in auth.tsx.

import { createContext, useContext } from "react";
import type { Role, User } from "./api";

export type AuthState = {
  user: User | null | undefined; // undefined while checking the session on page load
  signIn: (email: string) => Promise<User>;
  signOut: () => Promise<void>;
  refresh: () => Promise<void>; // re-read the user, e.g. after their role changed
};

export const AuthContext = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const state = useContext(AuthContext);
  if (!state) throw new Error("useAuth must be used inside <AuthProvider>");
  return state;
}

export const ROLE_LABEL: Record<Role, string> = { employee: "Employee", manager: "Manager", admin: "Admin" };

export const isStaff = (user: User | null | undefined) => user?.role === "manager" || user?.role === "admin";

export const isAdmin = (user: User | null | undefined) => user?.role === "admin";

/** "Sam Rivera" -> "SR", for avatars. */
export const initials = (name: string) =>
  name
    .split(/\s+/)
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
