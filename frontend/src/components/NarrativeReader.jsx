import styles from "../styles/Narrative.module.css";

const SECTION_LABELS = {
  eras: "Eres",
  factions: "Factions",
  regions: "Regions",
  events: "Evenements",
  characters: "Personnages",
  legends: "Legendes",
};

function renderText(text) {
  if (!text) return null;
  const str = typeof text === "string" ? text : JSON.stringify(text);
  return str.split("\n\n").map((para, j) => (
    <p key={j} className={styles.paragraph}>
      {para.split("\n").map((line, k) => (
        <span key={k}>
          {k > 0 && <br />}
          {line}
        </span>
      ))}
    </p>
  ));
}

function renderList(items, label) {
  if (!items || !Array.isArray(items) || items.length === 0) return null;
  return (
    <div className={styles.subSection}>
      <h4>{label}</h4>
      <ul>
        {items.map((item, i) => (
          <li key={i}>
            {typeof item === "string"
              ? item
              : item.name
                ? <><strong>{item.name}</strong> — {item.description || ""}</>
                : JSON.stringify(item)}
          </li>
        ))}
      </ul>
    </div>
  );
}

function renderEra(era, i) {
  return (
    <div key={i} className={styles.block}>
      <h3>
        {era.name}
        <span className={styles.meta}>
          {" "}(An {era.start_year} — An {era.end_year})
        </span>
      </h3>
      {renderText(era.description)}
      {era.key_events && era.key_events.length > 0 && (
        <div className={styles.subSection}>
          <h4>Evenements cles</h4>
          <ul>
            {era.key_events.map((evt, j) => (
              <li key={j}>{evt}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function renderFaction(fac, i) {
  return (
    <div key={i} className={styles.block}>
      <h3>{fac.name}</h3>
      {renderText(fac.description)}
      {fac.culture && (
        <div className={styles.subSection}>
          <h4>Culture</h4>
          {renderText(fac.culture)}
        </div>
      )}
      {fac.governance_description && (
        <div className={styles.subSection}>
          <h4>Gouvernance</h4>
          {renderText(fac.governance_description)}
        </div>
      )}
      {renderList(fac.strengths, "Forces")}
      {renderList(fac.weaknesses, "Faiblesses")}
      {renderList(fac.notable_moments, "Moments marquants")}
      {fac.current_state && (
        <div className={styles.subSection}>
          <h4>Etat actuel</h4>
          {renderText(fac.current_state)}
        </div>
      )}
    </div>
  );
}

function renderRegion(reg, i) {
  return (
    <div key={i} className={styles.block}>
      <h3>{reg.name}</h3>
      {renderText(reg.description)}
      {reg.landscape && (
        <div className={styles.subSection}>
          <h4>Paysage</h4>
          {renderText(reg.landscape)}
        </div>
      )}
      {reg.resources_description && (
        <div className={styles.subSection}>
          <h4>Ressources</h4>
          {renderText(reg.resources_description)}
        </div>
      )}
      {reg.strategic_importance && (
        <div className={styles.subSection}>
          <h4>Importance strategique</h4>
          {renderText(reg.strategic_importance)}
        </div>
      )}
      {reg.atmosphere && (
        <div className={styles.subSection}>
          <h4>Atmosphere</h4>
          {renderText(reg.atmosphere)}
        </div>
      )}
      {renderList(reg.notable_events, "Evenements notables")}
    </div>
  );
}

function renderEvent(evt, i) {
  return (
    <div key={i} className={styles.block}>
      <h3>
        {evt.title}
        <span className={styles.meta}> — An {evt.year}</span>
        {evt.era && (
          <span className={styles.meta}> ({evt.era})</span>
        )}
      </h3>
      {renderText(evt.narrative)}
      {evt.consequences_narrative && (
        <div className={styles.subSection}>
          <h4>Consequences</h4>
          {renderText(evt.consequences_narrative)}
        </div>
      )}
      {evt.involved_factions && evt.involved_factions.length > 0 && (
        <p className={styles.meta}>
          Factions impliquees : {evt.involved_factions.join(", ")}
        </p>
      )}
    </div>
  );
}

function renderCharacter(char, i) {
  return (
    <div key={i} className={styles.block}>
      <h3>
        {char.name}
        <span className={styles.meta}>
          {" "}— {char.role}{char.faction ? `, ${char.faction}` : ""}
        </span>
      </h3>
      {char.birth_year != null && (
        <p className={styles.meta}>
          An {char.birth_year}
          {char.death_year != null ? ` — An ${char.death_year}` : " — ?"}
        </p>
      )}
      {renderText(char.biography)}
      {char.personality && (
        <div className={styles.subSection}>
          <h4>Personnalite</h4>
          {renderText(char.personality)}
        </div>
      )}
      {char.legacy && (
        <div className={styles.subSection}>
          <h4>Heritage</h4>
          {renderText(char.legacy)}
        </div>
      )}
    </div>
  );
}

function renderLegend(leg, i) {
  return (
    <div key={i} className={styles.block}>
      <h3>
        {leg.title}
        {leg.type && (
          <span className={styles.meta}> — {leg.type}</span>
        )}
      </h3>
      {renderText(leg.narrative)}
      {leg.moral && (
        <div className={styles.subSection}>
          <h4>Morale</h4>
          {renderText(leg.moral)}
        </div>
      )}
      {leg.era_origin && (
        <p className={styles.meta}>Ere d'origine : {leg.era_origin}</p>
      )}
      {leg.related_factions && leg.related_factions.length > 0 && (
        <p className={styles.meta}>
          Factions liees : {leg.related_factions.join(", ")}
        </p>
      )}
    </div>
  );
}

function renderBlock(block, i, sectionKey) {
  if (typeof block === "string") {
    return (
      <div key={i} className={styles.block}>
        <p>{block}</p>
      </div>
    );
  }

  switch (sectionKey) {
    case "eras":
      return renderEra(block, i);
    case "factions":
      return renderFaction(block, i);
    case "regions":
      return renderRegion(block, i);
    case "events":
      return renderEvent(block, i);
    case "characters":
      return renderCharacter(block, i);
    case "legends":
      return renderLegend(block, i);
    default:
      // Fallback: render all string values
      return (
        <div key={i} className={styles.block}>
          {block.title && <h3>{block.title}</h3>}
          {block.name && !block.title && <h3>{block.name}</h3>}
          {renderText(
            block.content || block.description || block.narrative ||
            block.text || block.biography || ""
          )}
        </div>
      );
  }
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
          {blockList.map((block, i) => renderBlock(block, i, activeSection))}
        </div>
      </div>
    );
  }

  // Render all sections
  return (
    <div className={styles.content}>
      {Object.entries(narrativeBlocks).map(([key, blocks]) => {
        if (key === "coherence_report" || key === "names") return null;
        const blockList = Array.isArray(blocks) ? blocks : [blocks];
        return (
          <div key={key} className={styles.section}>
            <h2 className={styles.sectionTitle}>
              {SECTION_LABELS[key] || key}
            </h2>
            {blockList.map((block, i) => renderBlock(block, i, key))}
          </div>
        );
      })}
    </div>
  );
}
