/**
 * Shapes mirroring the Flask API's JSON. Keep these in sync with
 * backend/app/models.py (Pattern.to_dict) and backend/app/scraper.py.
 */

export interface User {
  id: number;
  username: string;
  email: string;
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
  uploader: string;
  created_at: string | null;
}

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
}

export interface PreviewResponse {
  duplicate: boolean;
  existing_pattern_id: number | null;
  draft: PatternDraft | null;
}
