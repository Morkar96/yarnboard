/** Patterns this account personally submitted -- distinct from patterns
 * merely bookmarked from the community (see MySavedPage). */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchMyUploads } from "../api/client";
import PatternCard from "../components/PatternCard";
import type { Pattern } from "../types/models";

export default function MyUploadsPage() {
  const [patterns, setPatterns] = useState<Pattern[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchMyUploads()
      .then(setPatterns)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p>Loading...</p>;

  return (
    <div className="my-uploads-page">
      <h1>My Uploads</h1>
      {patterns.length === 0 && (
        <p>
          You haven't submitted any patterns yet. <Link to="/submit">Submit one</Link>.
        </p>
      )}
      {patterns.map((pattern) => (
        <PatternCard key={pattern.id} pattern={pattern} />
      ))}
    </div>
  );
}
