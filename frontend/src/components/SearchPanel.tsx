import { useState, type FormEvent } from "react";
import { api } from "../api";
import type { SearchHit } from "../types";
import { markMatches } from "../utils";

interface SearchPanelProps {
  onSelectMeeting: (meetingId: string, start?: number) => void;
}

export function SearchPanel({ onSelectMeeting }: SearchPanelProps) {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [error, setError] = useState("");
  const [searching, setSearching] = useState(false);
  const [searched, setSearched] = useState("");

  const handleSubmit = async (ev: FormEvent) => {
    ev.preventDefault();
    const q = query.trim();
    setHits(null);
    setError("");
    if (!q) return;
    setSearching(true);
    try {
      const res = await api<{ hits: SearchHit[] }>(
        "GET",
        "/api/search?q=" + encodeURIComponent(q),
      );
      setSearched(q);
      setHits(res.hits);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSearching(false);
    }
  };

  return (
    <section className="sidebar-section" aria-labelledby="search-h">
      <h2 id="search-h">Search transcripts</h2>
      <form id="search-form" role="search" onSubmit={handleSubmit}>
        <label htmlFor="q" className="sr-only">
          Search
        </label>
        <div className="row">
          <div>
            <input
              type="search"
              id="q"
              placeholder="Search words…"
              value={query}
              onChange={(e) => {
                const v = e.target.value;
                setQuery(v);
                if (!v.trim()) {
                  setHits(null);
                  setError("");
                }
              }}
            />
          </div>
          <button type="submit">Search</button>
        </div>
      </form>
      <div id="hits" aria-busy={searching || undefined}>
        {searching && (
          <p
            className="muted"
            role="status"
            style={{ fontSize: "var(--text-xs)", margin: "var(--sp-1) 0 0" }}
          >
            Searching…
          </p>
        )}
        {error && (
          <div className="err" role="alert">
            {error}
          </div>
        )}
        {hits !== null && hits.length === 0 && (
          <p
            className="muted"
            style={{ fontSize: "var(--text-xs)", margin: "var(--sp-1) 0 0" }}
          >
            No matches.
          </p>
        )}
        {hits !== null &&
          hits.map((h, idx) => (
            <button
              key={`${h.meeting_id}-${h.start}-${idx}`}
              type="button"
              className="item hit"
              onClick={() => onSelectMeeting(h.meeting_id, h.start)}
            >
              <div className="m">
                {`${h.timestamp} ${h.title || h.meeting_id}${h.speaker ? " · " + h.speaker : ""}`}
              </div>
              <div style={{ fontSize: "var(--text-xs)", marginTop: 2 }}>
                {markMatches(h.text, searched).map((part, i) =>
                  part.match ? (
                    <mark key={i}>{part.text}</mark>
                  ) : (
                    part.text
                  ),
                )}
              </div>
            </button>
          ))}
      </div>
    </section>
  );
}
