import styles from "../styles/Narrative.module.css";

const SECTION_LABELS = {
  eras: "Eres",
  factions: "Factions",
  regions: "Regions",
  events: "Evenements",
  characters: "Personnages",
  legends: "Legendes",
};

function renderBlock(block, i) {
  if (typeof block === "string") {
    return (
      <div key={i} className={styles.block}>
        <p>{block}</p>
      </div>
    );
  }

  return (
    <div key={i} className={styles.block}>
      {block.title && <h3>{block.title}</h3>}
      {block.content && (
        <div>
          {block.content.split("\n\n").map((para, j) => (
            <p key={j}>{para}</p>
          ))}
        </div>
      )}
      {block.text && !block.content && (
        <div>
          {block.text.split("\n\n").map((para, j) => (
            <p key={j}>{para}</p>
          ))}
        </div>
      )}
    </div>
  );
}

export default function NarrativeReader({ narrativeBlocks, activeSection }) {
  if (!narrativeBlocks || Object.keys(narrativeBlocks).length === 0) {
    return (
      <div className={styles.empty}>Aucune narration disponible.</div>
    );
  }

  // If a section is active, render only that section
  if (activeSection && activeSection !== "all") {
    const blocks = narrativeBlocks[activeSection];
    if (!blocks) {
      return (
        <div className={styles.empty}>
          Aucune donnee pour la section &laquo;{" "}
          {SECTION_LABELS[activeSection] || activeSection} &raquo;.
        </div>
      );
    }

    const blockList = Array.isArray(blocks) ? blocks : [blocks];
    return (
      <div className={styles.content}>
        <div className={styles.section}>
          <h2 className={styles.sectionTitle}>
            {SECTION_LABELS[activeSection] || activeSection}
          </h2>
          {blockList.map((block, i) => renderBlock(block, i))}
        </div>
      </div>
    );
  }

  // Render all sections
  return (
    <div className={styles.content}>
      {Object.entries(narrativeBlocks).map(([key, blocks]) => {
        if (key === "coherence_report") return null;
        const blockList = Array.isArray(blocks) ? blocks : [blocks];
        return (
          <div key={key} className={styles.section}>
            <h2 className={styles.sectionTitle}>
              {SECTION_LABELS[key] || key}
            </h2>
            {blockList.map((block, i) => renderBlock(block, i))}
          </div>
        );
      })}
    </div>
  );
}
