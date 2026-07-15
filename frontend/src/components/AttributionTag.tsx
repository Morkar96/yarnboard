/**
 * Single source of truth for pattern attribution. Rendered by both
 * PatternCard (list views: Community/Mine/Saved) and PatternDetailPage --
 * never hand-rolled in more than one place, so "who uploaded it" and "who
 * originally made it" can't drift or go missing on any one view.
 */
import type { Pattern } from "../types/models";

export default function AttributionTag({ pattern }: { pattern: Pattern }) {
  const originalSite = pattern.source_site_name || pattern.source_domain || "the original site";

  return (
    <div className="attribution-tag">
      <span className="attribution-line">
        Uploaded by <strong>{pattern.uploader}</strong>
      </span>
      <span className="attribution-line">
        Original pattern by <strong>{pattern.author || "Unknown"}</strong> on{" "}
        <a href={pattern.original_url} target="_blank" rel="noopener noreferrer">
          {originalSite}
        </a>
      </span>
    </div>
  );
}
