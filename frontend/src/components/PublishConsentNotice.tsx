/**
 * The explicit "this will be public" gate shown on the review page, between
 * the editable draft form and the Publish button. Required per the product
 * spec: uploaders must be clearly told their submission is published to the
 * whole community, not just saved privately.
 */
interface Props {
  acknowledged: boolean;
  onAcknowledgeChange: (acknowledged: boolean) => void;
}

export default function PublishConsentNotice({ acknowledged, onAcknowledgeChange }: Props) {
  return (
    <div className="publish-consent-notice">
      <p>
        <strong>Publishing to Yarnboard:</strong> this pattern will be saved to the shared
        Yarnboard community library and visible to all users, along with your username and a
        link back to the original source. Please only submit patterns you have the right to
        share, and review the extracted content above for accuracy before publishing.
      </p>
      <label>
        <input
          type="checkbox"
          checked={acknowledged}
          onChange={(e) => onAcknowledgeChange(e.target.checked)}
        />
        I understand this pattern will be published publicly.
      </label>
    </div>
  );
}
