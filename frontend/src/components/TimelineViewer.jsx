import { useState } from "react";
import styles from "../styles/Timeline.module.css";

const CATEGORY_LABELS = {
  conflict: "Conflit",
  diplomacy: "Diplomatie",
  catastrophe: "Catastrophe",
  cultural: "Culturel",
  economic: "Economique",
  discovery: "Decouverte",
};

const CATEGORY_ICONS = {
  conflict: "\u2694",
  diplomacy: "\uD83E\uDD1D",
  catastrophe: "\uD83C\uDF0B",
  cultural: "\uD83C\uDFAD",
  economic: "\uD83D\uDCB0",
  discovery: "\uD83D\uDD2D",
};

export default function TimelineViewer({ timeline }) {
  const [expandedTicks, setExpandedTicks] = useState(new Set());
  const [activeFilter, setActiveFilter] = useState(null);

  if (!timeline || !timeline.ticks || timeline.ticks.length === 0) {
    return <div className={styles.empty}>Aucune donnee de chronologie disponible.</div>;
  }

  const ticks = timeline.ticks;

  // Gather all event categories
  const allCategories = new Set();
  ticks.forEach((tick) => {
    (tick.events || []).forEach((ev) => {
      if (ev.type || ev.category) {
        allCategories.add(ev.type || ev.category);
      }
    });
  });

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

  const filteredTicks = ticks.map((tick) => {
    if (!activeFilter) return tick;
    return {
      ...tick,
      events: (tick.events || []).filter(
        (ev) => (ev.type || ev.category) === activeFilter
      ),
    };
  });

  return (
    <>
      {/* Stats */}
      <div className={styles.stats}>
        <div className={styles.stat}>
          <div className={styles.statValue}>{ticks.length}</div>
          <div className={styles.statLabel}>Periodes</div>
        </div>
        <div className={styles.stat}>
          <div className={styles.statValue}>{totalEvents}</div>
          <div className={styles.statLabel}>Evenements</div>
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

      {/* Filters */}
      {allCategories.size > 0 && (
        <div className={styles.filters}>
          <button
            className={`${styles.filterBtn} ${
              !activeFilter ? styles.active : ""
            }`}
            onClick={() => setActiveFilter(null)}
          >
            Tous
          </button>
          {[...allCategories].map((cat) => (
            <button
              key={cat}
              className={`${styles.filterBtn} ${
                activeFilter === cat ? styles.active : ""
              }`}
              onClick={() =>
                setActiveFilter(activeFilter === cat ? null : cat)
              }
            >
              {CATEGORY_ICONS[cat] || ""} {CATEGORY_LABELS[cat] || cat}
            </button>
          ))}
        </div>
      )}

      {/* Timeline */}
      <div className={styles.timeline}>
        {filteredTicks.map((tick, i) => {
          const hasContent =
            (tick.events?.length || 0) +
              (tick.tech_unlocks?.length || 0) +
              (tick.character_events?.length || 0) >
            0;
          if (!hasContent && activeFilter) return null;

          const expanded = expandedTicks.has(i);
          const yearLabel =
            tick.year ?? tick.label ?? `Periode ${i + 1}`;

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
                  {(tick.events || []).map((ev, j) => {
                    const cat = ev.type || ev.category || "default";
                    return (
                      <div
                        key={j}
                        className={`${styles.eventCard} ${
                          styles[cat] || ""
                        }`}
                      >
                        <div className={styles.eventType}>
                          {CATEGORY_ICONS[cat] || ""}{" "}
                          {CATEGORY_LABELS[cat] || cat}
                        </div>
                        <div className={styles.eventName}>
                          {ev.name || ev.title || "Evenement"}
                        </div>
                        {(ev.description || ev.details) && (
                          <div className={styles.eventDesc}>
                            {ev.description || ev.details}
                          </div>
                        )}
                      </div>
                    );
                  })}

                  {(tick.tech_unlocks || []).map((tech, j) => (
                    <div key={`tech-${j}`} className={styles.techUnlock}>
                      <span>&#x2699;</span>
                      <span>
                        {typeof tech === "string"
                          ? tech
                          : tech.name || tech.label || "Technologie"}
                      </span>
                    </div>
                  ))}

                  {(tick.character_events || []).map((ce, j) => (
                    <div key={`char-${j}`} className={styles.characterEvent}>
                      <span>&#x1F464;</span>
                      <span>
                        {typeof ce === "string"
                          ? ce
                          : `${ce.character || ce.name || "Personnage"}: ${
                              ce.event || ce.action || ""
                            }`}
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
