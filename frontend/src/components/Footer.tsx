/** Site-wide footer, rendered on every page (see App.tsx) -- currently
 * just a Buy Me a Coffee link, kept separate from NavBar since it's
 * support/attribution content, not navigation. */
import { useTranslation } from "react-i18next";

const BUY_ME_A_COFFEE_URL = "https://buymeacoffee.com/moredolls5m";

export default function Footer() {
  const { t } = useTranslation();

  return (
    <footer className="text-center py-4 mt-5 border-top">
      <a
        href={BUY_ME_A_COFFEE_URL}
        target="_blank"
        rel="noopener noreferrer"
        className="btn btn-outline-primary btn-sm"
      >
        {t("footer.buyMeACoffee")}
      </a>
    </footer>
  );
}
