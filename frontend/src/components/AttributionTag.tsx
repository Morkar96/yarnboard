/**
 * Single source of truth for pattern attribution. Rendered by both
 * PatternCard (list views: Community/Mine/Saved) and PatternDetailPage --
 * never hand-rolled in more than one place, so "who uploaded it" and "who
 * originally made it" can't drift or go missing on any one view.
 */
import { useTranslation } from "react-i18next";
import type { Pattern } from "../types/models";

export default function AttributionTag({ pattern }: { pattern: Pattern }) {
  const { t } = useTranslation();
  const originalSite =
    pattern.source_site_name || pattern.source_domain || t("attribution.originalSiteFallback");

  return (
    <div className="small text-muted d-flex flex-column gap-1 mb-2">
      <span>
        {t("attribution.uploadedBy")} <strong className="text-body">{pattern.uploader}</strong>
      </span>
      <span>
        {t("attribution.originalByOn")}{" "}
        <strong className="text-body">{pattern.author || t("attribution.unknownAuthor")}</strong>{" "}
        {t("attribution.on")}{" "}
        <a
          href={pattern.original_url}
          target="_blank"
          rel="noopener noreferrer"
          className="link-primary"
        >
          {originalSite}
        </a>
      </span>
    </div>
  );
}
