import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { worlds } from "../services/api";
import TimelineViewer from "../components/TimelineViewer";
import styles from "../styles/Timeline.module.css";

export default function Timeline() {
  const { worldId } = useParams();
  const [timeline, setTimeline] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    worlds
      .getTimeline(worldId)
      .then((data) => {
        setTimeline(data);
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
        Chargement de la chronologie...
      </div>
    );
  }

  if (error) {
    return <div className={styles.error}>{error}</div>;
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1 className={styles.title}>Chronologie</h1>
        <Link to={`/world/${worldId}`} className={styles.backLink}>
          Retour au monde
        </Link>
      </div>

      <TimelineViewer timeline={timeline} />
    </div>
  );
}
