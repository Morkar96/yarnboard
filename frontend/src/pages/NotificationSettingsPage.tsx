/** Per-notification-type email/in-app toggles (see GET/PATCH
 * /api/notification-settings). Every NOTIFICATION_TYPES key the backend
 * knows about is always shown, defaulting to on -- see
 * NotificationSettings' docstring in types/models.ts. Each toggle saves
 * immediately (no separate "Save" step), matching how PatternVisibility
 * Panel's share-permission switches already work. */
import { useEffect, useState } from "react";
import { Alert, Card, Form, Spinner } from "react-bootstrap";
import { useTranslation } from "react-i18next";
import { fetchNotificationSettings, updateNotificationSettings } from "../api/client";
import { useApiErrorMessage } from "../i18n/useApiErrorMessage";
import type { NotificationSettings, NotificationType } from "../types/models";

const NOTIFICATION_TYPES: NotificationType[] = ["pattern_updated", "pattern_shared"];

export default function NotificationSettingsPage() {
  const { t } = useTranslation();
  const getErrorMessage = useApiErrorMessage();
  const [settings, setSettings] = useState<NotificationSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchNotificationSettings()
      .then(setSettings)
      .finally(() => setLoading(false));
  }, []);

  async function handleToggle(type: NotificationType, channel: "email" | "in_app", value: boolean) {
    setError(null);
    // Optimistic -- reverted below if the save fails.
    setSettings((prev) => (prev ? { ...prev, [type]: { ...prev[type], [channel]: value } } : prev));
    try {
      setSettings(await updateNotificationSettings({ [type]: { [channel]: value } }));
    } catch (err) {
      setError(getErrorMessage(err, t("notificationSettings.saveFailed")));
      setSettings(await fetchNotificationSettings());
    }
  }

  if (loading) return <Spinner animation="border" variant="primary" />;
  if (!settings) return null;

  return (
    <div>
      <h1 className="mb-2">{t("notificationSettings.title")}</h1>
      <p className="text-muted">{t("notificationSettings.intro")}</p>
      {error && <Alert variant="danger">{error}</Alert>}
      <Card className="shadow-sm">
        <Card.Body>
          {NOTIFICATION_TYPES.map((type, index) => (
            <div
              key={type}
              className={index > 0 ? "d-flex justify-content-between align-items-center flex-wrap gap-3 pt-3 mt-3 border-top" : "d-flex justify-content-between align-items-center flex-wrap gap-3"}
            >
              <div>
                <div className="fw-semibold">{t(`notificationSettings.types.${type}.label`)}</div>
                <div className="text-muted small">{t(`notificationSettings.types.${type}.description`)}</div>
              </div>
              <div className="d-flex gap-4">
                <Form.Check
                  type="switch"
                  id={`${type}-email`}
                  label={t("notificationSettings.emailChannel")}
                  checked={settings[type].email}
                  onChange={(e) => handleToggle(type, "email", e.target.checked)}
                />
                <Form.Check
                  type="switch"
                  id={`${type}-in-app`}
                  label={t("notificationSettings.inAppChannel")}
                  checked={settings[type].in_app}
                  onChange={(e) => handleToggle(type, "in_app", e.target.checked)}
                />
              </div>
            </div>
          ))}
        </Card.Body>
      </Card>
    </div>
  );
}
