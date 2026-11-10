import { useEffect, useRef, useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { ROLE_LABEL, initials, isAdmin, isStaff, useAuth } from "../session";
import { THEMES, applyTheme, savedTheme, type Theme } from "../theme";
import NotificationBell from "./NotificationBell";

const THEME_ICON: Record<Theme, string> = { light: "☀", dark: "☾", system: "◐" };
const THEME_LABEL: Record<Theme, string> = { light: "Light", dark: "Dark", system: "System" };

function ThemeSwitch() {
  const [theme, setTheme] = useState<Theme>(savedTheme);
  function choose(next: Theme) {
    setTheme(next);
    applyTheme(next);
  }
  return (
    <div className="theme-switch" role="radiogroup" aria-label="Colour theme">
      {THEMES.map((t) => (
        <button
          key={t}
          role="radio"
          aria-checked={theme === t}
          title={`${THEME_LABEL[t]} theme`}
          className={theme === t ? "on" : ""}
          onClick={() => choose(t)}
        >
          <span aria-hidden="true">{THEME_ICON[t]}</span>
          <span className="sr-only">{THEME_LABEL[t]}</span>
        </button>
      ))}
    </div>
  );
}

function UserMenu() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const menu = useRef<HTMLDivElement>(null);

  // Close when clicking elsewhere or pressing Escape.
  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (!menu.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!user) return null;

  async function onSignOut() {
    setOpen(false);
    await signOut();
    navigate("/");
  }

  return (
    <div className="user-menu" ref={menu}>
      <button className="avatar-button" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <span className={`avatar role-${user.role}`}>{initials(user.name)}</span>
        <span className="user-name">{user.name}</span>
      </button>
      {open && (
        <div className="menu" role="menu">
          <div className="menu-who">
            <strong>{user.name}</strong>
            <span className="muted small">{user.email}</span>
            <span className={`role-pill role-${user.role}`}>{ROLE_LABEL[user.role]}</span>
          </div>
          <div className="menu-row">
            <span>Theme</span>
            <ThemeSwitch />
          </div>
          <button role="menuitem" onClick={onSignOut}>
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

export default function AppHeader() {
  const { user } = useAuth();
  return (
    <header className="topbar">
      <Link to="/" className="brand">
        <span className="brand-mark" aria-hidden="true">
          ?
        </span>
        Ask Onboarding
      </Link>
      {user && (
        <nav>
          <NavLink to="/chat">Chat</NavLink>
          {isStaff(user) && <NavLink to="/documents">Documents</NavLink>}
          <NavLink to="/tickets">Tickets</NavLink>
          {isAdmin(user) && <NavLink to="/overview">Overview</NavLink>}
          {isAdmin(user) && <NavLink to="/people">People</NavLink>}
          {isAdmin(user) && <NavLink to="/project-docs">Docs</NavLink>}
        </nav>
      )}
      <div className="topbar-end">
        {!user && <ThemeSwitch />}
        {user && <NotificationBell key={user.id} />}
        {user ? (
          <UserMenu />
        ) : (
          user === null && (
            <Link to="/sign-in" className="button small-button">
              Sign in
            </Link>
          )
        )}
      </div>
    </header>
  );
}
