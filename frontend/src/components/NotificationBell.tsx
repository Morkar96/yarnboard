/**
 * In-app notification inbox, shown as a bell icon + unread badge in the
 * nav bar. Polls on mount and every 60s while logged in -- same cadence
 * and "don't bother with push/service-workers" rationale as UpdateBanner,
 * a separate and older notification mechanism (the "this pattern changed"
 * banner) that intentionally isn't merged into this one: that one is
 * tied to checklist-progress staleness with its own acknowledge flow,
 * this one is the general in-app inbox for discrete events like being
 * shared a pattern.
 */
import { useEffect, useState } from "react";
import { Badge, Button, Dropdown } from "react-bootstrap";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import {
  fetchNotificationInbox,
  markAllNotificationsRead,
  markNotificationRead,
} from "../api/client";
import { useAuth } from "../context/AuthContext";
import type { AppNotification } from "../types/models";

const POLL_INTERVAL_MS = 60_000;

export default function NotificationBell() {
  const { user } = useAuth();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [notifications, setNotifications] = useState<AppNotification[]>([]);

  useEffect(() => {
    if (!user) {
      setNotifications([]);
      return;
    }

    let cancelled = false;
    const poll = () => {
      fetchNotificationInbox()
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

  if (!user) return null;

  const unreadCount = notifications.filter((n) => !n.read).length;

  async function handleClick(notification: AppNotification) {
    if (!notification.read) {
      setNotifications((prev) =>
        prev.map((n) => (n.id === notification.id ? { ...n, read: true } : n)),
      );
      markNotificationRead(notification.id).catch(() => {
        // Best-effort -- next poll re-syncs the real state either way.
      });
    }
    if (notification.link) navigate(notification.link);
  }

  async function handleMarkAllRead() {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
    try {
      await markAllNotificationsRead();
    } catch {
      // See handleClick.
    }
  }

  return (
    <Dropdown align="end">
      <Dropdown.Toggle
        as={Button}
        variant="outline-light"
        size="sm"
        className="position-relative"
        id="notification-bell-toggle"
      >
        {t("notifications.bellLabel")}
        {unreadCount > 0 && (
          <Badge
            bg="danger"
            pill
            className="position-absolute top-0 start-100 translate-middle"
          >
            {unreadCount}
          </Badge>
        )}
      </Dropdown.Toggle>
      <Dropdown.Menu style={{ minWidth: "20rem", maxHeight: "24rem", overflowY: "auto" }}>
        <div className="d-flex justify-content-between align-items-center px-3 py-1">
          <strong className="small">{t("notifications.inboxTitle")}</strong>
          {unreadCount > 0 && (
            <Button variant="link" size="sm" className="p-0" onClick={handleMarkAllRead}>
              {t("notifications.markAllRead")}
            </Button>
          )}
        </div>
        {notifications.length === 0 ? (
          <p className="text-muted small px-3 mb-2">{t("notifications.empty")}</p>
        ) : (
          notifications.map((n) => (
            <Dropdown.Item
              key={n.id}
              onClick={() => handleClick(n)}
              className={n.read ? "text-muted" : "fw-semibold"}
              style={{ whiteSpace: "normal" }}
            >
              {n.message}
            </Dropdown.Item>
          ))
        )}
      </Dropdown.Menu>
    </Dropdown>
  );
}
