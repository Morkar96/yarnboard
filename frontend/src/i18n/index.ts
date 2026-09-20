/**
 * i18next setup. Deliberately no <I18nextProvider> wrapping App -- every
 * component just calls useTranslation() directly against this one global
 * instance (the standard react-i18next pattern when there's only ever
 * one active language tree, not a multi-tenant/multi-instance app).
 *
 * Two languages only, both bundled at build time (no lazy-loaded
 * namespaces) -- the UI string set is small enough that splitting it out
 * would be premature. "en" and "he" mirror the two Pattern-content
 * languages (English fields, title_he/materials_he/etc. -- see
 * backend/app/models.py), though this file only covers static UI
 * chrome; pattern content translation is unrelated data, not routed
 * through i18next at all (see PatternDetailPage.tsx).
 */
import i18next from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./en.json";
import he from "./he.json";

export const SUPPORTED_LANGUAGES = ["en", "he"] as const;
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];
export const RTL_LANGUAGES: SupportedLanguage[] = ["he"];

const STORAGE_KEY = "yarnboard-language";

function isSupportedLanguage(value: string | null): value is SupportedLanguage {
  return SUPPORTED_LANGUAGES.includes(value as SupportedLanguage);
}

/** Reads the persisted choice, falling back to English -- there's no
 * browser-language auto-detection, so a first-time visitor always sees
 * English until they explicitly switch (see NavBar's language toggle).
 * Guards against localStorage being unavailable (privacy-mode browsers
 * that throw on access, or a test environment with no storage at all)
 * rather than letting the whole app fail to boot over a language
 * preference that can safely just default to English instead. */
export function getStoredLanguage(): SupportedLanguage {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return isSupportedLanguage(stored) ? stored : "en";
  } catch {
    return "en";
  }
}

/** Applies `dir`/`lang` to <html> for the given language -- the one
 * thing that has to happen outside React's render cycle (CSS direction
 * and the RTL Bootstrap stylesheet toggle both key off these attributes;
 * see main.tsx's applyDirection, called both at boot and on every
 * language change). */
export function isRtl(language: string): boolean {
  return RTL_LANGUAGES.includes(language as SupportedLanguage);
}

i18next.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    he: { translation: he },
  },
  lng: getStoredLanguage(),
  fallbackLng: "en",
  interpolation: {
    // React already escapes rendered text -- i18next's own HTML-escaping
    // would double-escape things like the "'" in patternDetail copy.
    escapeValue: false,
  },
});

i18next.on("languageChanged", (language) => {
  try {
    localStorage.setItem(STORAGE_KEY, language);
  } catch {
    // See getStoredLanguage's try/catch above -- losing the persisted
    // preference is fine, the app still works for this session.
  }
});

export default i18next;
