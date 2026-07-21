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
    <div className="small text-muted d-flex flex-column gap-1 mb-2">
      <span>
        Uploaded by <strong className="text-body">{pattern.uploader}</strong>
      </span>
      <span>
        Original pattern by <strong className="text-body">{pattern.author || "Unknown"}</strong>{" "}
        on{" "}
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
