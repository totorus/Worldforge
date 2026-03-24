import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { worlds } from "../services/api";
import NarrativeReader from "../components/NarrativeReader";
import styles from "../styles/Narrative.module.css";

const SECTIONS = [
  { key: "eras", label: "Eres" },
  { key: "factions", label: "Factions" },
  { key: "regions", label: "Regions" },
  { key: "events", label: "Evenements" },
  { key: "characters", label: "Personnages" },
  { key: "legends", label: "Legendes" },
];

export default function Narrative() {
  const { worldId } = useParams();
  const [narrative, setNarrative] = useState(null);
  const [activeSection, setActiveSection] = useState("eras");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    worlds
      .getNarrative(worldId)
      .then((data) => {
        setNarrative(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [worldId]);

  if (loading) {
    return (
      <div className={styles.loadingPage}>
        <div className={styles.spinner} />
        Chargement de la narration...
      </div>
    );
  }

  if (error) {
    return <div className={styles.error}>{error}</div>;
  }

  const blocks = narrative?.narrative_blocks || narrative?.blocks || narrative || {};
  const coherenceReport = narrative?.coherence_report || blocks?.coherence_report;

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1 className={styles.title}>Narration</h1>
        <Link to={`/world/${worldId}`} className={styles.backLink}>
          Retour au monde
        </Link>
      </div>

      <div className={styles.tabs}>
        {SECTIONS.map((sec) => (
          <button
            key={sec.key}
            className={`${styles.tab} ${
              activeSection === sec.key ? styles.active : ""
            }`}
            onClick={() => setActiveSection(sec.key)}
          >
            {sec.label}
          </button>
        ))}
      </div>

      <NarrativeReader narrativeBlocks={blocks} activeSection={activeSection} />

      {coherenceReport && (
        <div style={{ padding: "0 32px 32px", maxWidth: 800, margin: "0 auto" }}>
          <div className={styles.coherenceReport}>
            <h3>Rapport de coherence</h3>
            {coherenceReport.score != null && (
              <div className={styles.coherenceScore}>
                {coherenceReport.score}/10
              </div>
            )}
            {coherenceReport.issues && coherenceReport.issues.length > 0 && (
              <ul className={styles.coherenceIssues}>
                {coherenceReport.issues.map((issue, i) => (
                  <li key={i}>
                    {typeof issue === "string" ? issue : issue.description || issue.message}
                  </li>
                ))}
              </ul>
            )}
            {coherenceReport.summary && (
              <p style={{ color: "var(--text-secondary)", marginTop: 12 }}>
                {coherenceReport.summary}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
