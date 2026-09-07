import type { EnglishTranslation, HebrewTranslation, Pattern } from "../types/models";

/**
 * Whichever of a pattern's translation overlays matches the current UI
 * language (from react-i18next's i18n.language, set by the navbar
 * toggle), or null if the UI language is neither "he" nor "en" or that
 * direction has no translation yet. Callers fall back to the pattern's
 * own primary content in that null case -- see PatternDetailPage.tsx's
 * module docstring for why this single formula correctly covers all
 * combinations of (primary content language) x (UI language) without
 * needing to know which language a pattern's primary content is
 * actually in.
 *
 * Shared by every place a pattern's title/materials/abbreviations/
 * instructions are displayed (PatternCard, PatternDetailPage,
 * PatternChecklist) so there's exactly one implementation of this
 * fallback to keep in sync, rather than each call site re-deriving it --
 * a previous PatternCard-only copy handled the "he" direction but forgot
 * the "en" one, so English-toggled browsing still showed Hebrew-primary
 * patterns in Hebrew.
 */
export function translationForUiLanguage(
  pattern: Pattern,
  language: string,
): HebrewTranslation | EnglishTranslation | null {
  if (language === "he") return pattern.translations.he;
  if (language === "en") return pattern.translations.en;
  return null;
}
