import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  unreadNotifications,
  type Notification,
} from "../api";
import { timeAgo } from "../timeAgo";

const POLL_MS = 30_000;

// Drawn as SVG: text glyphs don't centre reliably inside a small circle.
function TicketIcon() {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14">
      <path
        d="M2.5 4.5h11v2.2a1.5 1.5 0 0 0 0 2.6v2.2h-11V9.3a1.5 1.5 0 0 0 0-2.6Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function AlertIcon() {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14">
      <path d="M8 3.5v5.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <circle cx="8" cy="12.3" r="1.2" fill="currentColor" />
    </svg>
  );
}

/**
 * The header bell: an unread count, refreshed every 30 seconds while the tab
 * is visible (and at once when you come back to it), and a dropdown of your
 * latest notifications. The server decides what each person receives.
 */
export default function NotificationBell() {
  const navigate = useNavigate();
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<Notification[] | null>(null);
  const [more, setMore] = useState(false);
  const panel = useRef<HTMLDivElement>(null);

  const refreshCount = useCallback(() => {
    unreadNotifications()
      .then((r) => setUnread(r.unread))
      .catch(() => {}); // the bell is a hint; a failed poll just waits for the next one
  }, []);

  // Poll only while the tab is visible: no requests from forgotten background tabs.
  useEffect(() => {
    refreshCount();
    const timer = setInterval(() => document.visibilityState === "visible" && refreshCount(), POLL_MS);
    const onVisible = () => document.visibilityState === "visible" && refreshCount();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [refreshCount]);

  // Close on a click outside or Escape.
  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => !panel.current?.contains(e.target as Node) && setOpen(false);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  async function toggle() {
    if (open) return setOpen(false);
    setOpen(true);
    try {
      const page = await listNotifications();
      setItems(page.items);
      setUnread(page.unread);
      setMore(page.items.length === 20);
    } catch {
      setItems([]);
    }
  }

  async function loadOlder() {
    const oldest = items?.[items.length - 1];
    if (!oldest) return;
    const page = await listNotifications(oldest.id);
    setItems((prev) => [...(prev ?? []), ...page.items]);
    setMore(page.items.length === 20);
  }

  async function openOne(n: Notification) {
    if (!n.read) {
      setItems((prev) => prev?.map((x) => (x.id === n.id ? { ...x, read: true } : x)) ?? null);
      setUnread((u) => Math.max(0, u - 1));
      markNotificationRead(n.id).catch(refreshCount);
    }
    setOpen(false);
    if (n.link) navigate(n.link);
  }

  async function readAll() {
    setItems((prev) => prev?.map((x) => ({ ...x, read: true })) ?? null);
    setUnread(0);
    markAllNotificationsRead().catch(refreshCount);
  }

  const label = unread ? `Notifications, ${unread} unread` : "Notifications";

  return (
    <div className="bell" ref={panel}>
      <button className="bell-button" aria-label={label} title={label} aria-expanded={open} onClick={toggle}>
        <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
          <path
            d="M12 3a6 6 0 0 0-6 6v3.6L4.3 15.5A1 1 0 0 0 5.2 17h13.6a1 1 0 0 0 .9-1.5L18 12.6V9a6 6 0 0 0-6-6Zm-2.5 15.5a2.5 2.5 0 0 0 5 0"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        {unread > 0 && <span className="bell-badge">{unread > 9 ? "9+" : unread}</span>}
      </button>

      {open && (
        <div className="bell-panel" role="dialog" aria-label="Notifications">
          <div className="bell-head">
            <strong>Notifications</strong>
            {unread > 0 && (
              <button className="link" onClick={readAll}>
                Mark all as read
              </button>
            )}
          </div>
          {items === null && <p className="muted bell-empty">Loading…</p>}
          {items?.length === 0 && <p className="muted bell-empty">You're all caught up.</p>}
          {items && items.length > 0 && (
            <ul className="bell-list">
              {items.map((n) => (
                <li key={n.id}>
                  <button className={`bell-item ${n.read ? "" : "unread"} ${n.severity}`} onClick={() => openOne(n)}>
                    <span className={`bell-icon ${n.kind === "system.alert" ? `bell-icon-${n.severity}` : "bell-icon-ticket"}`} aria-hidden="true">
                      {n.kind === "system.alert" ? <AlertIcon /> : <TicketIcon />}
                    </span>
                    <span className="bell-text">
                      <strong>{n.title}</strong>
                      {n.body && <span className="bell-body">{n.body}</span>}
                      <span className="muted bell-time">{timeAgo(n.at)}</span>
                    </span>
                    {!n.read && <span className="bell-dot" aria-label="unread" />}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {more && (
            <button className="link bell-more" onClick={loadOlder}>
              Show older
            </button>
          )}
        </div>
      )}
    </div>
  );
}
