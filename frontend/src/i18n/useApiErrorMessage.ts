import { useTranslation } from "react-i18next";
import { ApiError } from "../api/client";

/**
 * Resolves an error caught from an API call to a localized, user-facing
 * message. ApiError.code maps to an errors.<code> key in en.json/he.json
 * when one exists; a handful of codes deliberately have no matching key
 * (scraper_error, translation_error, stitchfiddle_fetch_error,
 * invalid_share_url, invalid_translation -- see each one's comment in
 * the backend route that sends it) because that text is generated
 * per-request server-side, not a fixed string a resource file could
 * translate -- those fall through to the raw `err.message` regardless
 * of UI language. `fallback` covers the non-ApiError case (a network
 * failure, an unparseable response, etc.), and should itself be a
 * `t("...")` call at the caller so it's localized too.
 */
export function useApiErrorMessage() {
  const { t, i18n } = useTranslation();

  return (err: unknown, fallback: string): string => {
    if (err instanceof ApiError) {
      if (err.code && i18n.exists(`errors.${err.code}`)) {
        return t(`errors.${err.code}`, err.params);
      }
      return err.message;
    }
    return fallback;
  };
}
