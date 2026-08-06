/**
 * Shapes mirroring the Flask API's JSON. Keep these in sync with
 * backend/app/models.py (Pattern.to_dict) and backend/app/scraper.py.
 */

export interface User {
  id: number;
  username: string;
  email: string;
  is_admin: boolean;
}

/** One checklist step, with this viewer's personal completed state merged in
 * by the backend (see Pattern.to_dict in models.py). */
export interface PatternStep {
  step: string;
  completed: boolean;
}

/** part name -> ordered list of steps */
export type InstructionsMap = Record<string, PatternStep[]>;

export interface Pattern {
  id: number;
  original_url: string;
  title: string;
  author: string | null;
  source_site_name: string | null;
  source_domain: string | null;
  materials: string | null;
  abbreviations: string | null;
  instructions: InstructionsMap;
  /** A single opaque URL regardless of source: either the external site's
   * scraped image, or our own GET /api/patterns/<id>/photo streaming route
   * for a manually-uploaded one (see Pattern.to_dict in models.py). */
  photo_url: string | null;
  has_photo: boolean;
  /** A Stitch Fiddle chart's grid, imported via the Stitch Fiddle page --
   * null for every other pattern. `cells` is row-major, one 0-indexed
   * `palette` lookup per cell (see PatternChartGrid.tsx). */
  chart_grid: ChartGrid | null;
  uploader: string;
  uploader_id: number;
  created_at: string | null;
}

export interface ChartGridPaletteEntry {
  hex: string;
  label: string;
}

export interface ChartGrid {
  column_count: number;
  row_count: number;
  palette: ChartGridPaletteEntry[];
  cells: number[];
}

/** One pattern the current user has stale progress on -- drives the
 * in-app "this pattern changed" banner (see UpdateBanner.tsx). */
export interface PatternNotification {
  id: number;
  title: string;
}

/** Fields editable on an already-published pattern (see PATCH
 * /api/patterns/<id>). original_url/source_site_name/source_domain stay
 * immutable for dedup + attribution integrity, so they're not part of
 * this type at all. */
export type PatternEditPayload = Pick<
  PatternDraft,
  "title" | "author" | "materials" | "abbreviations" | "instructions"
>;

/** The editable, not-yet-saved draft returned by POST /api/patterns/preview.
 * Instructions here are plain strings (no per-user completed flag yet --
 * that only exists once a Pattern row and a viewer both exist). */
export interface PatternDraft {
  title: string;
  author: string | null;
  materials: string;
  abbreviations: string;
  instructions: Record<string, string[]>;
  source_site_name: string;
  source_domain: string;
  /** Scraped photo (og:image/twitter:image), if the source page had one --
   * reviewable/clearable in PatternReviewForm before publishing. */
  photo_url: string | null;
}

export interface PreviewResponse {
  duplicate: boolean;
  existing_pattern_id: number | null;
  draft: PatternDraft | null;
}

/** A saved Stitch Fiddle (stitchfiddle.com) chart share link -- private to
 * the user who saved it. `imported_pattern_id` is null until "Import" is
 * clicked; once set, re-importing is a no-op (see the backend route). */
export interface StitchFiddleLink {
  id: number;
  share_url: string;
  chart_id: string;
  imported_pattern_id: number | null;
  created_at: string | null;
}
