/** All published patterns, from every user. Public -- no login required to
 * browse, matching the backend's GET /api/patterns/community. */
import { useEffect, useState } from "react";
import { fetchCommunityPatterns, fetchMySaved, savePattern, unsavePattern } from "../api/client";
import PatternCard from "../components/PatternCard";
import { useAuth } from "../context/AuthContext";
import type { Pattern } from "../types/models";

export default function CommunityPage() {
  const { user } = useAuth();
  const [patterns, setPatterns] = useState<Pattern[]>([]);
  const [savedIds, setSavedIds] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchCommunityPatterns()
      .then(setPatterns)
      .finally(() => setLoading(false));
    if (user) {
      fetchMySaved().then((saved) => setSavedIds(new Set(saved.map((p) => p.id))));
    }
  }, [user]);

  async function handleToggleSave(pattern: Pattern) {
    if (savedIds.has(pattern.id)) {
      await unsavePattern(pattern.id);
      setSavedIds((prev) => {
        const next = new Set(prev);
        next.delete(pattern.id);
        return next;
      });
    } else {
      await savePattern(pattern.id);
      setSavedIds((prev) => new Set(prev).add(pattern.id));
    }
  }

  if (loading) return <p>Loading...</p>;

  return (
    <div className="community-page">
      <h1>Community Patterns</h1>
      {patterns.length === 0 && <p>No patterns have been published yet.</p>}
      {patterns.map((pattern) => (
        <PatternCard
          key={pattern.id}
          pattern={pattern}
          onToggleSave={user ? handleToggleSave : undefined}
          isSaved={savedIds.has(pattern.id)}
        />
      ))}
    </div>
  );
}
