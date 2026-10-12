/** Site-wide footer, rendered on every page (see App.tsx) -- a Buy Me a
 * Coffee link plus the Terms of Use link, kept separate from NavBar
 * since it's support/legal content, not navigation. */
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

const BUY_ME_A_COFFEE_URL = "https://buymeacoffee.com/moredolls5m";

export default function Footer() {
  const { t } = useTranslation();

  return (
    <footer className="text-center py-4 mt-5 border-top">
      <div className="d-flex justify-content-center align-items-center gap-3 flex-wrap">
        <a
          href={BUY_ME_A_COFFEE_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="btn btn-outline-primary btn-sm"
        >
          {t("footer.buyMeACoffee")}
        </a>
        <Link to="/terms" className="small">
          {t("footer.terms")}
        </Link>
      </div>
    </footer>
  );
}
