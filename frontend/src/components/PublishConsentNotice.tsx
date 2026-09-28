/**
 * The explicit "this will be public" gate shown on the review page, between
 * the editable draft form and the Publish button. Required per the product
 * spec: uploaders must be clearly told their submission is published to the
 * whole community, not just saved privately.
 */
import { Alert, Form } from "react-bootstrap";

interface Props {
  acknowledged: boolean;
  onAcknowledgeChange: (acknowledged: boolean) => void;
}

export default function PublishConsentNotice({ acknowledged, onAcknowledgeChange }: Props) {
  return (
    <Alert variant="warning" className="my-4">
      <p className="mb-3">
        <strong>Publishing to Yarnboard:</strong> this pattern will be saved to the shared
        Yarnboard community library and visible to all users, along with your username and a
        link back to the original source. Please only submit patterns you have the right to
        share, and review the extracted content above for accuracy before publishing.
      </p>
      <Form.Check
        type="checkbox"
        id="publish-consent"
        label="I understand this pattern will be published publicly."
        checked={acknowledged}
        onChange={(e) => onAcknowledgeChange(e.target.checked)}
      />
    </Alert>
  );
}
