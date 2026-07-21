/**
 * Polls for patterns the current user has stale checklist progress on
 * (edited since they last worked on it) and shows one dismissible banner
 * per pattern -- the in-app half of the update-notification feature (the
 * other half is the email sent at edit time, see backend/app/email.py).
 *
 * Polling, not push: checks on mount and every 60s while a user is logged
 * in. No service worker, no OS-level notification -- this only shows
 * while the app is actually open, by design (confirmed with the user).
 */
import { useEffect, useState } from "react";
import { Alert } from "react-bootstrap";
import { Link } from "react-router-dom";
import { acknowledgePatternUpdate, fetchNotifications } from "../api/client";
import { useAuth } from "../context/AuthContext";
import type { PatternNotification } from "../types/models";

const POLL_INTERVAL_MS = 60_000;

export default function UpdateBanner() {
  const { user } = useAuth();
  const [notifications, setNotifications] = useState<PatternNotification[]>([]);

  useEffect(() => {
    if (!user) {
      setNotifications([]);
      return;
    }

    let cancelled = false;
    const poll = () => {
      fetchNotifications()
        .then((result) => {
          if (!cancelled) setNotifications(result);
        })
        .catch(() => {
          // Transient failure -- just try again next interval.
        });
    };

    poll();
    const interval = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [user]);

  async function dismiss(id: number) {
    // Optimistic removal -- if the acknowledge call fails, the next poll
    // just re-adds it, so there's no need to roll this back manually.
    setNotifications((prev) => prev.filter((n) => n.id !== id));
    try {
      await acknowledgePatternUpdate(id);
    } catch {
      // See above.
    }
  }

  if (notifications.length === 0) return null;

  return (
    <div className="container pt-3">
      {notifications.map((n) => (
        <Alert key={n.id} variant="info" dismissible onClose={() => dismiss(n.id)}>
          <Link to={`/pattern/${n.id}`}>{n.title}</Link> has changed since you last worked on
          it. Dismissing this will clear your old checklist progress on it.
        </Alert>
      ))}
    </div>
  );
}
