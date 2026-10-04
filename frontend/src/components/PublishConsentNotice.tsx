/**
 * The explicit "this will be public" gate shown when publishing a pattern
 * to the community (see PatternVisibilityPanel), between the "Publish"
 * button and the actual POST /<id>/publish call. Required per the product
 * spec: uploaders must be clearly told their pattern is about to become
 * visible to everyone, not just saved privately -- which is what
 * submitting/importing a pattern does on its own, before this gate is
 * ever shown.
 */
import { Alert, Form } from "react-bootstrap";
import { useTranslation } from "react-i18next";

interface Props {
  acknowledged: boolean;
  onAcknowledgeChange: (acknowledged: boolean) => void;
}

export default function PublishConsentNotice({ acknowledged, onAcknowledgeChange }: Props) {
  const { t } = useTranslation();

  return (
    <Alert variant="warning" className="my-4">
      <p className="mb-3">
        <strong>{t("publishConsent.introLead")}</strong> {t("publishConsent.intro")}
      </p>
      <Form.Check
        type="checkbox"
        id="publish-consent"
        label={t("publishConsent.checkboxLabel")}
        checked={acknowledged}
        onChange={(e) => onAcknowledgeChange(e.target.checked)}
      />
    </Alert>
  );
}
