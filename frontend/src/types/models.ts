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
  translations: PatternTranslations;
  uploader: string;
  uploader_id: number;
  created_at: string | null;
}

/** One instructions part's Hebrew translation. Keyed in
 * HebrewTranslation.instructions by the *same* English part-name string
 * used in Pattern.instructions -- never a translated key -- because
 * checklist progress (toggleProgress) is keyed by that English part
 * name; see Pattern.instructions_he's docstring in backend/app/models.py.
 * `steps_he` is always the same length as the corresponding English
 * steps array, matched by index the same way PatternStep is. */
export interface HebrewInstructionEntry {
  heading_he: string;
  steps_he: string[];
}

export interface HebrewTranslation {
  title: string;
  materials: string | null;
  abbreviations: string | null;
  instructions: Record<string, HebrewInstructionEntry>;
  /** False until a human (uploader or admin) has confirmed the
   * auto-translation via an edit -- see PATCH /api/patterns/<id>. */
  reviewed: boolean;
}

/** null until POST /api/patterns/<id>/translate has been run at least
 * once for this pattern. Only "he" exists today -- shaped as a map keyed
 * by language so a second language could be added later without
 * reshaping this type. */
export interface PatternTranslations {
  he: HebrewTranslation | null;
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
 * this type at all.
 *
 * The title_he/materials_he/abbreviations_he/instructions_he fields are
 * optional and only sent when the uploader/an admin is also editing the
 * Hebrew translation in the same request -- omitting `instructions_he`
 * entirely leaves any existing translation untouched server-side (see
 * edit_pattern's docstring in backend/app/patterns/routes.py). When
 * present, instructions_he must have exactly the same keys as
 * `instructions` and each entry's steps_he the same length as its
 * English counterpart, or the backend rejects the whole request. */
export type PatternEditPayload = Pick<
  PatternDraft,
  "title" | "author" | "materials" | "abbreviations" | "instructions"
> & {
  title_he?: string;
  materials_he?: string | null;
  abbreviations_he?: string | null;
  instructions_he?: Record<string, HebrewInstructionEntry>;
};

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
