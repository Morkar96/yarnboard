/**
 * The explicit "this will be public" gate shown on the review page, between
 * the editable draft form and the Publish button. Required per the product
 * spec: uploaders must be clearly told their submission is published to the
 * whole community, not just saved privately.
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
