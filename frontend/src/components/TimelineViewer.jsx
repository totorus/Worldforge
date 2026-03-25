import { useState } from "react";
import styles from "../styles/Timeline.module.css";

export default function TimelineViewer({ timeline }) {
  const [expandedTicks, setExpandedTicks] = useState(new Set());

  if (!timeline || !timeline.ticks || timeline.ticks.length === 0) {
    return <div className={styles.empty}>Aucune donnée de chronologie disponible.</div>;
  }

  const ticks = timeline.ticks;

  // Stats
  const totalEvents = ticks.reduce(
    (sum, t) => sum + (t.events?.length || 0),
    0
  );
  const totalTechs = ticks.reduce(
    (sum, t) => sum + (t.tech_unlocks?.length || 0),
    0
  );
  const totalChars = ticks.reduce(
    (sum, t) => sum + (t.character_events?.length || 0),
    0
  );

  const toggleTick = (i) => {
    setExpandedTicks((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  };

  // Human-readable name from IDs: "evt_marée_de_souvenirs" → "Marée de souvenirs"
  const formatEventId = (id) => {
    if (!id) return "Événement";
    return id
      .replace(/^(evt|fac|tech|role|reg)_/, "")
      .replace(/_/g, " ")
      .replace(/^\w/, (c) => c.toUpperCase());
  };

  return (
    <>
      {/* Stats */}
      <div className={styles.stats}>
        <div className={styles.stat}>
          <div className={styles.statValue}>{ticks.length}</div>
          <div className={styles.statLabel}>Périodes</div>
        </div>
        <div className={styles.stat}>
          <div className={styles.statValue}>{totalEvents}</div>
          <div className={styles.statLabel}>Événements</div>
        </div>
        <div className={styles.stat}>
          <div className={styles.statValue}>{totalTechs}</div>
          <div className={styles.statLabel}>Technologies</div>
        </div>
        <div className={styles.stat}>
          <div className={styles.statValue}>{totalChars}</div>
          <div className={styles.statLabel}>Personnages</div>
        </div>
      </div>

      {/* Timeline */}
      <div className={styles.timeline}>
        {ticks.map((tick, i) => {
          const hasContent =
            (tick.events?.length || 0) +
              (tick.tech_unlocks?.length || 0) +
              (tick.character_events?.length || 0) >
            0;
          if (!hasContent) return null;

          const expanded = expandedTicks.has(i);
          const yearLabel = tick.year ?? `Période ${i + 1}`;

          return (
            <div key={i} className={styles.tick}>
              <div className={styles.tickDot} />
              <div
                className={styles.tickYear}
                onClick={() => toggleTick(i)}
              >
                <span
                  className={`${styles.tickToggle} ${
                    expanded ? styles.open : ""
                  }`}
                >
                  &#9654;
                </span>
                An {yearLabel}
                {tick.events?.length > 0 && (
                  <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                    ({tick.events.length} evt)
                  </span>
                )}
              </div>

              {expanded && (
                <div className={styles.tickDetails}>
                  {(tick.events || []).map((ev, j) => (
                    <div key={j} className={styles.eventCard}>
                      <div className={styles.eventName}>
                        {formatEventId(ev.event_id)}
                      </div>
                      {ev.involved_factions?.length > 0 && (
                        <div className={styles.eventDesc}>
                          Factions : {ev.involved_factions.join(", ")}
                        </div>
                      )}
                      {ev.involved_regions?.length > 0 && (
                        <div className={styles.eventDesc}>
                          Régions : {ev.involved_regions.join(", ")}
                        </div>
                      )}
                    </div>
                  ))}

                  {(tick.tech_unlocks || []).map((tech, j) => (
                    <div key={`tech-${j}`} className={styles.techUnlock}>
                      <span>&#x2699;</span>
                      <span>
                        {typeof tech === "string"
                          ? tech
                          : formatEventId(tech.tech_id || tech.name || "Technologie")}
                        {tech.faction_id && (
                          <span style={{ color: "var(--text-muted)", marginLeft: 6 }}>
                            ({formatEventId(tech.faction_id)})
                          </span>
                        )}
                      </span>
                    </div>
                  ))}

                  {(tick.character_events || []).map((ce, j) => (
                    <div key={`char-${j}`} className={styles.characterEvent}>
                      <span>&#x1F464;</span>
                      <span>
                        {typeof ce === "string"
                          ? ce
                          : `${formatEventId(ce.role || "Personnage")} — ${
                              ce.type === "spawn" ? "apparition" : ce.type === "retire" ? "retrait" : ce.type || ""
                            }`}
                        {ce.faction_id && (
                          <span style={{ color: "var(--text-muted)", marginLeft: 6 }}>
                            ({formatEventId(ce.faction_id)})
                          </span>
                        )}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </>
  );
}
