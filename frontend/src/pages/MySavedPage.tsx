/** Community patterns this account has bookmarked -- may or may not have
 * been uploaded by this same account (see MyUploadsPage for that list). */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchMySaved, unsavePattern } from "../api/client";
import PatternCard from "../components/PatternCard";
import type { Pattern } from "../types/models";

export default function MySavedPage() {
  const [patterns, setPatterns] = useState<Pattern[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchMySaved()
      .then(setPatterns)
      .finally(() => setLoading(false));
  }, []);

  async function handleUnsave(pattern: Pattern) {
    await unsavePattern(pattern.id);
    setPatterns((prev) => prev.filter((p) => p.id !== pattern.id));
  }

  if (loading) return <p>Loading...</p>;

  return (
    <div className="my-saved-page">
      <h1>My Saved Patterns</h1>
      {patterns.length === 0 && (
        <p>
          You haven't saved any patterns yet. Browse the <Link to="/community">Community</Link>{" "}
          page to find some.
        </p>
      )}
      {patterns.map((pattern) => (
        <PatternCard key={pattern.id} pattern={pattern} onToggleSave={handleUnsave} isSaved />
      ))}
    </div>
  );
}
