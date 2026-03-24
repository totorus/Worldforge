import styles from "../styles/WorldCard.module.css";

const STATUS_LABELS = {
  draft: "Brouillon",
  configured: "Configuré",
  simulated: "Simulé",
  narrated: "Narré",
  published: "Publié",
};

const STATUS_CLASSES = {
  draft: styles.badgeDraft,
  configured: styles.badgeConfigured,
  simulated: styles.badgeSimulated,
  narrated: styles.badgeNarrated,
  published: styles.badgePublished,
};

export default function WorldCard({ world, onClick, onSimulate, onNarrate, onExport, onDelete }) {
  const status = world.status || "draft";
  const factionCount = world.config?.factions?.length ?? world.faction_count ?? 0;
  const simYears = world.config?.simulation?.years ?? world.simulation_years ?? 0;

  function stopPropagation(handler) {
    return (e) => {
      e.stopPropagation();
      handler();
    };
  }

  const canSimulate = status === "configured" || status === "draft";
  const canNarrate = status === "simulated";
  const canExport = status === "narrated" || status === "published";

  return (
    <div className={styles.card} onClick={onClick} role="button" tabIndex={0}>
      <div className={styles.cardHeader}>
        <h3>{world.name || "Monde sans nom"}</h3>
        <span className={`${styles.badge} ${STATUS_CLASSES[status] || styles.badgeDraft}`}>
          {STATUS_LABELS[status] || status}
        </span>
      </div>

      <div className={styles.stats}>
        {factionCount > 0 && (
          <span className={styles.stat}>
            <strong>{factionCount}</strong>
            <span className={styles.statLabel}>factions</span>
          </span>
        )}
        {simYears > 0 && (
          <span className={styles.stat}>
            <strong>{simYears}</strong>
            <span className={styles.statLabel}>ans</span>
          </span>
        )}
        {world.genre && (
          <span className={styles.stat}>
            <span className={styles.statLabel}>{world.genre}</span>
          </span>
        )}
      </div>

      <div className={styles.actions}>
        {canSimulate && onSimulate && (
          <button className="btn-secondary btn-small" onClick={stopPropagation(onSimulate)}>
            Simuler
          </button>
        )}
        {canNarrate && onNarrate && (
          <button className="btn-secondary btn-small" onClick={stopPropagation(onNarrate)}>
            Narrer
          </button>
        )}
        {canExport && onExport && (
          <button className="btn-secondary btn-small" onClick={stopPropagation(onExport)}>
            Exporter
          </button>
        )}
        {onDelete && (
          <button className="btn-danger btn-small" onClick={stopPropagation(onDelete)}>
            Supprimer
          </button>
        )}
      </div>
    </div>
  );
}
