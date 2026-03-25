# Timeline, Export & Entity Extraction Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 5 bugs: timeline display, era-event matching in export, tech filtering, per-era entity extraction, and chapter page counts.

**Architecture:** Each fix is independent. Tasks 1-2 are frontend/backend one-liners. Task 3 refactors export tech filtering. Task 4 is the largest — refactoring entity extraction to work per-era. Task 5 adds an `update_chapter` method and a post-page-creation update pass.

**Tech Stack:** React (frontend), Python/FastAPI (backend), Bookstack REST API, Kimi K2.5 (entity detection via Moonshot API — sequential only), Mistral Creative (entity sheets via OpenRouter)

**Spec:** `docs/superpowers/specs/2026-03-25-timeline-export-fixes-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `frontend/src/pages/Timeline.jsx` | Modify:17 | Extract `data.timeline` instead of passing full response |
| `frontend/src/components/TimelineViewer.jsx` | Modify | Remove category filters, show event_id/factions/regions |
| `backend/app/exporter/pipeline.py` | Modify:219-224,273,308-326 | Fuzzy era matching, tech filtering, chapter count update |
| `backend/app/exporter/bookstack_client.py` | Modify | Add `update_chapter()` method |
| `backend/app/narrator/entity_extraction.py` | Modify | Refactor to per-era extraction |
| `backend/app/narrator/pipeline.py` | Modify:251-253 | Pass timeline to entity extraction |
| `backend/tests/test_timeline_export_fixes.py` | Create | Tests for era matching, tech filtering |
| `backend/tests/test_entity_extraction_velmorath.py` | Create | Integration test on Velmorath data |

---

### Task 1: Fix Timeline.jsx data passing

**Files:**
- Modify: `frontend/src/pages/Timeline.jsx:17`

- [ ] **Step 1: Fix the data extraction**

In `Timeline.jsx`, line 17 currently stores the full API response `{world_id, timeline}` as-is. Change it to extract only the `timeline` field:

```jsx
// Line 17 — change:
setTimeline(data);
// to:
setTimeline(data.timeline);
```

- [ ] **Step 2: Verify in browser**

Navigate to a world's timeline page. It should now show ticks instead of "Aucune donnée de chronologie disponible."

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Timeline.jsx
git commit -m "fix: extract timeline from API response in Timeline.jsx"
```

---

### Task 2: Refactor TimelineViewer for real data structure

**Files:**
- Modify: `frontend/src/components/TimelineViewer.jsx`

The current component expects `ev.type`/`ev.category`, `ev.name`/`ev.title`, `ev.description` — none of these exist in the simulator's event structure. Real events have: `event_id`, `outcome`, `involved_factions`, `involved_regions`.

- [ ] **Step 1: Remove category constants, filters, and category-based rendering**

Replace the entire `TimelineViewer.jsx` with:

```jsx
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

  // Human-readable event name from event_id: "evt_marée_de_souvenirs" → "Marée de souvenirs"
  const formatEventId = (eventId) => {
    if (!eventId) return "Événement";
    return eventId
      .replace(/^evt_/, "")
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
```

- [ ] **Step 2: Verify in browser**

Navigate to a world's timeline. Events should show formatted event IDs, factions, and regions. No category filter bar should appear.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/TimelineViewer.jsx
git commit -m "fix: adapt TimelineViewer to real simulator event structure"
```

---

### Task 3: Fuzzy era matching for narrative events in export

**Files:**
- Modify: `backend/app/exporter/pipeline.py:219-274`
- Create: `backend/tests/test_timeline_export_fixes.py`

Currently, narrative events are grouped by exact `era` field match (line 219-224). Most events have era names that don't match any defined era exactly (19 unique names vs 5 defined eras). This causes most event narratives to be lost during export.

- [ ] **Step 1: Write tests for era matching**

Create `backend/tests/test_timeline_export_fixes.py`:

```python
"""Tests for timeline/export fix helpers."""

import pytest


def test_match_narrative_events_to_eras_exact():
    """Exact name match should work."""
    from app.exporter.pipeline import _match_narrative_events_to_eras

    eras = [
        {"name": "L'Âge des Origines", "start_year": 0, "end_year": 200},
        {"name": "L'Ère des Conflits", "start_year": 201, "end_year": 500},
    ]
    events = [
        {"era": "L'Âge des Origines", "title": "Evt 1"},
        {"era": "L'Ère des Conflits", "title": "Evt 2"},
    ]
    result = _match_narrative_events_to_eras(events, eras)
    assert len(result["L'Âge des Origines"]) == 1
    assert len(result["L'Ère des Conflits"]) == 1


def test_match_narrative_events_to_eras_substring():
    """Substring inclusion should match."""
    from app.exporter.pipeline import _match_narrative_events_to_eras

    eras = [
        {"name": "L'Âge des Origines", "start_year": 0, "end_year": 200},
    ]
    events = [
        {"era": "L'Âge des Origines Perdues (0-200)", "title": "Evt 1"},
    ]
    result = _match_narrative_events_to_eras(events, eras)
    assert len(result["L'Âge des Origines"]) == 1


def test_match_narrative_events_to_eras_year_fallback():
    """Year-based fallback when name doesn't match at all."""
    from app.exporter.pipeline import _match_narrative_events_to_eras

    eras = [
        {"name": "L'Âge des Origines", "start_year": 0, "end_year": 200},
        {"name": "L'Ère des Conflits", "start_year": 201, "end_year": 500},
    ]
    events = [
        {"era": "Le Crépuscule des Anciens", "year": 150, "title": "Evt 1"},
        {"era": "Quelque chose", "year": 300, "title": "Evt 2"},
    ]
    result = _match_narrative_events_to_eras(events, eras)
    assert len(result["L'Âge des Origines"]) == 1
    assert len(result["L'Ère des Conflits"]) == 1


def test_match_narrative_events_orphans():
    """Events that match nothing go to orphan key."""
    from app.exporter.pipeline import _match_narrative_events_to_eras

    eras = [
        {"name": "L'Âge des Origines", "start_year": 0, "end_year": 200},
    ]
    events = [
        {"era": "Totalement inconnu", "title": "Evt 1"},
    ]
    result = _match_narrative_events_to_eras(events, eras)
    assert len(result.get("__orphans__", [])) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/openclaw/WorldForge/Worldforge && docker compose exec backend pytest tests/test_timeline_export_fixes.py -v
```

Expected: FAIL — `_match_narrative_events_to_eras` does not exist yet.

- [ ] **Step 3: Implement `_match_narrative_events_to_eras` in pipeline.py**

Add this helper function after `_group_events_by_era` (after line 107):

```python
def _match_narrative_events_to_eras(
    events: list[dict], eras: list[dict]
) -> dict[str, list[dict]]:
    """Assign narrative events to eras using cascading matching.

    Cascade: exact name → substring inclusion → year range → orphans.
    """
    result: dict[str, list[dict]] = {era.get("name", ""): [] for era in eras}
    result["__orphans__"] = []

    for ev in events:
        era_field = ev.get("era", "")
        matched = False

        # 1. Exact match
        if era_field in result and era_field != "__orphans__":
            result[era_field].append(ev)
            continue

        # 2. Substring inclusion (case-insensitive)
        era_lower = era_field.lower()
        for era in eras:
            era_name = era.get("name", "")
            if era_name.lower() in era_lower or era_lower in era_name.lower():
                result[era_name].append(ev)
                matched = True
                break

        if matched:
            continue

        # 3. Year-range fallback
        year = ev.get("year")
        if year is not None:
            for era in eras:
                start = era.get("start_year", 0)
                end = era.get("end_year", float("inf"))
                if start <= year <= end:
                    result[era.get("name", "")].append(ev)
                    matched = True
                    break

        if not matched:
            result["__orphans__"].append(ev)

    return result
```

- [ ] **Step 4: Replace the exact-match grouping in `export_to_bookstack`**

In `pipeline.py`, replace lines 217-224:

```python
    narr_events = narrative_blocks.get("events", [])
    if isinstance(narr_events, list):
        narr_events_by_era: dict[str, list[dict]] = {}
        for ev in narr_events:
            era_name = ev.get("era", "")
            narr_events_by_era.setdefault(era_name, []).append(ev)
    else:
        narr_events_by_era = {}
```

Replace with:

```python
    narr_events = narrative_blocks.get("events", [])
    if isinstance(narr_events, list):
        narr_events_by_era = _match_narrative_events_to_eras(narr_events, eras_to_use if isinstance(narr_eras_raw, list) and narr_eras_raw else timeline_eras)
    else:
        narr_events_by_era = {}
```

**Important:** `eras_to_use` is defined at line 253-256, but `narr_events_by_era` is built at line 219 (before). Move the narr_events grouping to **after** `eras_to_use` is defined (after line 256). The new code should be:

```python
    # After line 256 (after eras_to_use is defined):
    narr_events = narrative_blocks.get("events", [])
    if isinstance(narr_events, list):
        narr_events_by_era = _match_narrative_events_to_eras(narr_events, eras_to_use)
    else:
        narr_events_by_era = {}
```

And add orphan handling after the era pages loop (after line 280). If there are orphan events, create a page for them:

```python
    # After the era pages loop
    orphan_events = narr_events_by_era.get("__orphans__", [])
    if orphan_events:
        from app.exporter.formatters import format_era_page
        orphan_era = {"name": "Événements non classés", "narrative": "Événements n'ayant pu être associés à une ère définie."}
        html = format_era_page(orphan_era, [], orphan_events)
        page = await client.create_page(
            chapter_id=chapter_ids["chroniques"], name="Événements non classés", html=html
        )
        pages_created.append({"id": page["id"], "slug": page.get("slug", ""), "name": "Événements non classés", "type": "era", "key": "__orphans__"})
```

- [ ] **Step 5: Run tests**

```bash
cd /home/openclaw/WorldForge/Worldforge && docker compose exec backend pytest tests/test_timeline_export_fixes.py -v
```

Expected: All 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/exporter/pipeline.py backend/tests/test_timeline_export_fixes.py
git commit -m "fix: fuzzy era matching for narrative events in export"
```

---

### Task 4: Export only unlocked technologies

**Files:**
- Modify: `backend/app/exporter/pipeline.py:308-326`
- Modify: `backend/tests/test_timeline_export_fixes.py`

Currently, line 313 iterates ALL `config.tech_tree.nodes`. Should only export techs unlocked by at least one faction in the simulation.

- [ ] **Step 1: Add test**

Append to `backend/tests/test_timeline_export_fixes.py`:

```python
def test_collect_unlocked_techs():
    """Only techs present in at least one faction's unlocked_techs should be returned."""
    from app.exporter.pipeline import _collect_unlocked_techs

    timeline = {
        "ticks": [
            {"year": 100, "world_state": {"factions": [
                {"id": "fac_a", "unlocked_techs": ["tech_fire"]},
                {"id": "fac_b", "unlocked_techs": ["tech_fire", "tech_wheel"]},
            ]}},
            {"year": 200, "world_state": {"factions": [
                {"id": "fac_a", "unlocked_techs": ["tech_fire", "tech_iron"]},
                {"id": "fac_b", "unlocked_techs": ["tech_fire", "tech_wheel"]},
            ]}},
        ]
    }
    tech_tree_nodes = {
        "tech_fire": {"id": "tech_fire", "name": "Feu"},
        "tech_wheel": {"id": "tech_wheel", "name": "Roue"},
        "tech_iron": {"id": "tech_iron", "name": "Fer"},
        "tech_steam": {"id": "tech_steam", "name": "Vapeur"},
    }

    result = _collect_unlocked_techs(timeline, tech_tree_nodes)
    result_ids = {t["id"] for t in result}
    assert result_ids == {"tech_fire", "tech_wheel", "tech_iron"}
    assert "tech_steam" not in result_ids
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/openclaw/WorldForge/Worldforge && docker compose exec backend pytest tests/test_timeline_export_fixes.py::test_collect_unlocked_techs -v
```

- [ ] **Step 3: Implement `_collect_unlocked_techs`**

Add helper after `_match_narrative_events_to_eras` in `pipeline.py`:

```python
def _collect_unlocked_techs(
    timeline: dict, tech_tree_nodes: dict[str, dict]
) -> list[dict]:
    """Collect techs unlocked by any faction across all ticks.

    Uses the last tick's world_state for the final cumulative state.
    Falls back to scanning all ticks if last tick has no world_state.
    """
    ticks = timeline.get("ticks", [])
    if not ticks:
        return []

    # Last tick has the cumulative final state
    unlocked_ids: set[str] = set()
    last_tick = ticks[-1]
    factions = last_tick.get("world_state", {}).get("factions", [])
    for fac in factions:
        for tech_id in fac.get("unlocked_techs", []):
            unlocked_ids.add(tech_id)

    # If last tick had nothing, scan all ticks
    if not unlocked_ids:
        for tick in ticks:
            for fac in tick.get("world_state", {}).get("factions", []):
                for tech_id in fac.get("unlocked_techs", []):
                    unlocked_ids.add(tech_id)

    # Resolve tech details from tech_tree
    result = []
    for tech_id in sorted(unlocked_ids):
        node = tech_tree_nodes.get(tech_id)
        if node:
            result.append(node)
        else:
            result.append({"id": tech_id, "name": tech_id})
    return result
```

- [ ] **Step 4: Replace tech export loop in `export_to_bookstack`**

Replace lines 308-326 in `pipeline.py`:

```python
    # --- Technologies ---
    tech_narratives = narrative_blocks.get("technologies", narrative_blocks.get("tech", {}))
    if isinstance(tech_narratives, list):
        tech_narratives = _list_to_dict(tech_narratives)

    for tech in config.get("tech_tree", {}).get("nodes", []):
```

With:

```python
    # --- Technologies (only unlocked) ---
    tech_narratives = narrative_blocks.get("technologies", narrative_blocks.get("tech", {}))
    if isinstance(tech_narratives, list):
        tech_narratives = _list_to_dict(tech_narratives)

    # tech_tree.nodes can be a list or dict — normalize to dict
    raw_nodes = config.get("tech_tree", {}).get("nodes", [])
    if isinstance(raw_nodes, list):
        tech_nodes_dict = {t["id"]: t for t in raw_nodes if isinstance(t, dict) and "id" in t}
    elif isinstance(raw_nodes, dict):
        tech_nodes_dict = raw_nodes
    else:
        tech_nodes_dict = {}

    unlocked_techs = _collect_unlocked_techs(timeline, tech_nodes_dict)

    for tech in unlocked_techs:
```

The rest of the loop (lines 314-326) stays the same.

- [ ] **Step 5: Run tests**

```bash
cd /home/openclaw/WorldForge/Worldforge && docker compose exec backend pytest tests/test_timeline_export_fixes.py -v
```

Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/exporter/pipeline.py backend/tests/test_timeline_export_fixes.py
git commit -m "fix: export only unlocked technologies instead of full tech tree"
```

---

### Task 5: Per-era entity extraction

**Files:**
- Modify: `backend/app/narrator/entity_extraction.py`
- Modify: `backend/app/narrator/pipeline.py:251-253`
- Create: `backend/tests/test_entity_extraction_velmorath.py`

This is the largest change. The current `run_entity_extraction` sends all narrative text in one shot with iterative deepening. The new approach processes one era at a time, building cumulative context.

- [ ] **Step 1: Add helper `_collect_era_context` to entity_extraction.py**

Add after `_collect_narrative_text` (after line 119):

```python
def _collect_era_narrative_text(narrative_blocks: dict, era: dict) -> str:
    """Collect narrative text for a specific era."""
    era_name = era.get("name", "")
    start_year = era.get("start_year", 0)
    end_year = era.get("end_year", float("inf"))
    parts = []

    # Era narrative itself
    for field in ["narrative", "description", "summary"]:
        val = era.get(field)
        if isinstance(val, str) and len(val) > 20:
            parts.append(val)

    # Events matching this era (by era field or year)
    for ev in narrative_blocks.get("events", []):
        if not isinstance(ev, dict):
            continue
        ev_era = ev.get("era", "")
        ev_year = ev.get("year")
        match = (
            ev_era == era_name
            or era_name.lower() in ev_era.lower()
            or ev_era.lower() in era_name.lower()
            or (ev_year is not None and start_year <= ev_year <= end_year)
        )
        if match:
            for v in ev.values():
                if isinstance(v, str) and len(v) > 20:
                    parts.append(v)

    # Characters — include all (they don't have era tags)
    # They'll be included in first era to maximize detection
    # Subsequent eras will have them in known_entities

    # Legends — include all (same logic)
    if not parts:
        # If no era-specific content, include a bit of general narrative
        for block_key in ["factions", "regions"]:
            items = narrative_blocks.get(block_key, [])
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        for v in item.values():
                            if isinstance(v, str) and len(v) > 20:
                                parts.append(v)

    return "\n\n".join(parts)


def _build_era_structured_context(timeline: dict, era: dict) -> str:
    """Build structured context from timeline data for an era."""
    start_year = era.get("start_year", 0)
    end_year = era.get("end_year", float("inf"))
    ticks = timeline.get("ticks", [])
    parts = []

    era_factions = set()
    era_regions = set()
    era_techs = set()
    era_events = []

    for tick in ticks:
        year = tick.get("year", 0)
        if not (start_year <= year <= end_year):
            continue

        for fac in tick.get("world_state", {}).get("factions", []):
            era_factions.add(fac.get("name", fac.get("id", "")))
            for tech_id in fac.get("unlocked_techs", []):
                era_techs.add(tech_id)

        for ev in tick.get("events", []):
            for r in ev.get("involved_regions", []):
                era_regions.add(r)
            era_events.append(ev.get("event_id", ""))

    if era_factions:
        parts.append(f"Factions actives : {', '.join(sorted(era_factions))}")
    if era_regions:
        parts.append(f"Régions concernées : {', '.join(sorted(era_regions))}")
    if era_techs:
        parts.append(f"Technologies déverrouillées : {', '.join(sorted(era_techs))}")
    if era_events:
        parts.append(f"Événements : {', '.join(e for e in era_events if e)}")

    return "\n".join(parts)
```

- [ ] **Step 2: Refactor `detect_entities` to accept era context**

Replace the `detect_entities` function (lines 122-202) with a version that takes optional era context and volume hints:

```python
async def detect_entities(
    narrative_blocks: dict,
    config: dict,
    *,
    era_text: str | None = None,
    structured_context: str = "",
    previously_detected: list[str] | None = None,
    volume_hint: str = "",
) -> list[dict]:
    """Detect invented entities in narrative text.

    Args:
        narrative_blocks: Full narrative blocks (for building known list).
        config: World configuration.
        era_text: If provided, use this text instead of collecting all narrative text.
        structured_context: Additional structured data (factions, regions, techs for this era).
        previously_detected: Entity names already detected in prior eras.
        volume_hint: Hint about expected entity count to push LLM to find more.

    Returns list of dicts: [{name, type, context}]
    """
    known = _build_known_entities(config, narrative_blocks)
    if previously_detected:
        known.extend(previously_detected)

    text = era_text if era_text is not None else _collect_narrative_text(narrative_blocks)

    if not text:
        return []

    genre = config.get("meta", {}).get("genre", "fantasy")
    world_name = config.get("meta", {}).get("world_name", "Monde inconnu")

    max_chars = 12000
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[...texte tronqué...]"

    type_descriptions = "\n".join(
        f"- {t}: {info['description']}" for t, info in ENTITY_TEMPLATES.items()
    )

    full_text = text
    if structured_context:
        full_text = f"Données structurées de cette période :\n{structured_context}\n\nTexte narratif :\n{text}"

    volume_instruction = ""
    if volume_hint:
        volume_instruction = f"\n\nINDICATION DE VOLUME : {volume_hint}\n"

    messages = [
        {
            "role": "system",
            "content": (
                "Tu es un analyste de lore spécialisé dans les mondes fictifs. "
                "Tu réponds toujours en français. "
                f"Le monde « {world_name} » est de genre « {genre} ». "
                "Ta tâche est d'identifier les entités inventées nommées dans le texte "
                "qui n'ont pas encore de fiche dédiée. "
                "Sois EXHAUSTIF : cherche toutes les mentions de noms propres, "
                "de lieux, de créatures, de ressources, d'organisations, d'artefacts. "
                "Réponds uniquement avec un JSON valide (sans markdown, sans commentaire)."
            ),
        },
        {
            "role": "user",
            "content": (
                "Analyse le texte narratif suivant et identifie toutes les entités inventées "
                "nommées qui mériteraient leur propre fiche encyclopédique.\n\n"
                f"Entités qui ont DÉJÀ une fiche (ne pas les inclure) :\n{', '.join(known)}\n\n"
                f"Types d'entités à détecter :\n{type_descriptions}\n\n"
                f"{volume_instruction}"
                "RÈGLES :\n"
                "- Inclure : tout nom propre inventé unique au monde (créature, lieu, personnage historique, artefact...)\n"
                "- Exclure : entités génériques (marguerite, loup, hibou, taverne, soldat anonyme)\n"
                "- Exclure : les figurants sans importance historique\n"
                "- Un personnage historique doit avoir un impact fort sur l'histoire pour mériter une fiche\n\n"
                f"{full_text}\n\n"
                "Réponds avec une liste JSON. Chaque item :\n"
                "- name : nom exact tel qu'il apparaît dans le texte\n"
                "- type : un des types listés ci-dessus\n"
                "- context : phrase courte expliquant pourquoi cette entité mérite une fiche\n"
            ),
        },
    ]

    logger.info("Detecting entities for world '%s' (known: %d)", world_name, len(known))
    response = await llm_router.complete(
        task="entity_detection", messages=messages, temperature=0.3, max_tokens=4096
    )

    try:
        entities = extract_json(response)
        if not isinstance(entities, list):
            raise ValueError("Expected a JSON list")
        known_lower = {n.lower() for n in known}
        filtered = [
            e for e in entities
            if isinstance(e, dict)
            and e.get("name", "").lower() not in known_lower
            and e.get("type") in ENTITY_TYPES
        ]
        logger.info("Detected %d new entities (from %d candidates)", len(filtered), len(entities))
        return filtered
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Failed to parse entity detection JSON: %s", e)
        return []
```

- [ ] **Step 3: Rewrite `run_entity_extraction` for per-era processing**

Replace the `run_entity_extraction` function (lines 370-448) with:

```python
async def run_entity_extraction(
    config: dict,
    narrative_blocks: dict,
    timeline: dict | None = None,
    max_depth: int = 4,
    on_progress=None,
) -> dict:
    """Run entity extraction per era with cumulative context.

    If timeline and eras are available, processes era by era.
    Falls back to the old iterative deepening if no eras.

    Modifies narrative_blocks in-place, adding entities_<type> keys.
    """
    eras = narrative_blocks.get("eras", [])
    if not isinstance(eras, list) or not eras or timeline is None:
        # Fallback: old iterative approach
        return await _run_entity_extraction_iterative(
            config, narrative_blocks, max_depth, on_progress
        )

    # Sort eras chronologically
    sorted_eras = sorted(eras, key=lambda e: e.get("start_year", 0))

    total_generated = 0
    all_detected_names: list[str] = []

    n_factions = len(config.get("factions", []))
    n_regions = len(config.get("geography", {}).get("regions", []))

    for i, era in enumerate(sorted_eras):
        era_name = era.get("name", f"Ère {i+1}")
        if on_progress:
            await on_progress(f"Extraction d'entités — ère {i+1}/{len(sorted_eras)} : {era_name}")

        logger.info("Entity extraction for era '%s' (%d/%d)", era_name, i + 1, len(sorted_eras))

        # Build era-specific text and structured context
        era_text = _collect_era_narrative_text(narrative_blocks, era)
        structured = _build_era_structured_context(timeline, era)

        # Volume hint for first era (push LLM to find more)
        volume_hint = ""
        if i == 0:
            volume_hint = (
                f"Ce monde a {n_factions} factions et {n_regions} régions. "
                f"On s'attend à trouver au minimum {max(2, n_factions // 2)} races, "
                f"{max(3, n_factions)} créatures/faune/flore, "
                f"{max(2, n_regions)} lieux notables, "
                f"et plusieurs organisations, artefacts et ressources."
            )

        # Include characters and legends text in first era
        if i == 0:
            extra_parts = []
            for block_key in ["characters", "legends"]:
                items = narrative_blocks.get(block_key, [])
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            for v in item.values():
                                if isinstance(v, str) and len(v) > 20:
                                    extra_parts.append(v)
            if extra_parts:
                era_text = era_text + "\n\n" + "\n\n".join(extra_parts)

        # Detect
        new_entities = await detect_entities(
            narrative_blocks, config,
            era_text=era_text,
            structured_context=structured,
            previously_detected=all_detected_names,
            volume_hint=volume_hint,
        )

        if not new_entities:
            logger.info("No new entities for era '%s'", era_name)
            continue

        logger.info("Found %d new entities in era '%s'", len(new_entities), era_name)

        # Generate sheets (sequential — Mistral via OpenRouter)
        for entity in new_entities:
            if on_progress:
                await on_progress(f"Fiche : {entity.get('name', '?')}")
            sheet = await generate_entity_sheet(entity, config, narrative_blocks)
            entity_type = entity.get("type", "artefact")
            block_key = f"entities_{entity_type}"
            if block_key not in narrative_blocks:
                narrative_blocks[block_key] = []
            narrative_blocks[block_key].append(sheet)
            all_detected_names.append(entity.get("name", ""))
            total_generated += 1

        # Generate cosmogonies for new races
        races = narrative_blocks.get("entities_race", [])
        existing_cosmogonies = {
            c.get("race", "") for c in narrative_blocks.get("entities_cosmogonie", [])
            if isinstance(c, dict)
        }
        new_races = [r for r in races if isinstance(r, dict) and r.get("name", "") not in existing_cosmogonies]
        if new_races:
            if on_progress:
                await on_progress(f"Cosmogonies ({len(new_races)} races)")
            for race in new_races:
                cosmo = await generate_cosmogony(race, config, narrative_blocks)
                if "entities_cosmogonie" not in narrative_blocks:
                    narrative_blocks["entities_cosmogonie"] = []
                narrative_blocks["entities_cosmogonie"].append(cosmo)
                total_generated += 1

    summary = {
        "total_generated": total_generated,
        "eras_processed": len(sorted_eras),
        "counts": {},
    }
    for entity_type in ENTITY_TYPES + ["cosmogonie"]:
        key = f"entities_{entity_type}"
        count = len(narrative_blocks.get(key, []))
        if count > 0:
            summary["counts"][entity_type] = count

    logger.info("Per-era entity extraction complete: %d entities generated", total_generated)
    return summary


async def _run_entity_extraction_iterative(
    config: dict,
    narrative_blocks: dict,
    max_depth: int = 4,
    on_progress=None,
) -> dict:
    """Original iterative deepening approach — fallback when no eras/timeline."""
    total_generated = 0

    for depth in range(1, max_depth + 1):
        if on_progress:
            await on_progress(f"Extraction d'entités — niveau {depth}/{max_depth}")

        logger.info("Entity extraction depth %d/%d", depth, max_depth)
        new_entities = await detect_entities(narrative_blocks, config)

        if not new_entities:
            logger.info("No new entities found at depth %d, stopping", depth)
            break

        logger.info("Found %d new entities at depth %d", len(new_entities), depth)

        for entity in new_entities:
            sheet = await generate_entity_sheet(entity, config, narrative_blocks)
            entity_type = entity.get("type", "artefact")
            block_key = f"entities_{entity_type}"
            if block_key not in narrative_blocks:
                narrative_blocks[block_key] = []
            narrative_blocks[block_key].append(sheet)
            total_generated += 1

        races = narrative_blocks.get("entities_race", [])
        existing_cosmogonies = {
            c.get("race", "") for c in narrative_blocks.get("entities_cosmogonie", [])
            if isinstance(c, dict)
        }
        new_races = [r for r in races if isinstance(r, dict) and r.get("name", "") not in existing_cosmogonies]
        if new_races:
            if on_progress:
                await on_progress(f"Génération des cosmogonies ({len(new_races)} races)")
            for race in new_races:
                cosmo = await generate_cosmogony(race, config, narrative_blocks)
                if "entities_cosmogonie" not in narrative_blocks:
                    narrative_blocks["entities_cosmogonie"] = []
                narrative_blocks["entities_cosmogonie"].append(cosmo)
                total_generated += 1

    summary = {
        "total_generated": total_generated,
        "depth_reached": min(depth, max_depth) if total_generated > 0 else 0,
        "counts": {},
    }
    for entity_type in ENTITY_TYPES + ["cosmogonie"]:
        key = f"entities_{entity_type}"
        count = len(narrative_blocks.get(key, []))
        if count > 0:
            summary["counts"][entity_type] = count

    logger.info("Entity extraction complete: %d entities generated", total_generated)
    return summary
```

- [ ] **Step 4: Update narrator pipeline to pass timeline**

In `backend/app/narrator/pipeline.py`, modify `_run_entity_extraction` (lines 251-253):

```python
# Change:
async def _run_entity_extraction(config: dict, narrative_blocks: dict) -> dict:
    """Run entity extraction with iterative deepening."""
    return await run_entity_extraction(config, narrative_blocks, max_depth=4)

# To:
async def _run_entity_extraction(config: dict, narrative_blocks: dict, timeline: dict | None = None) -> dict:
    """Run entity extraction per era (or iterative fallback)."""
    return await run_entity_extraction(config, narrative_blocks, timeline=timeline, max_depth=4)
```

Also update the call site at line 80:

```python
# Change:
narrative_blocks["entity_summary"] = await _run_entity_extraction(config, narrative_blocks)

# To:
narrative_blocks["entity_summary"] = await _run_entity_extraction(config, narrative_blocks, timeline)
```

And update the step map at line 118:

```python
# Change:
"entity_extraction": lambda: _run_entity_extraction(config, narrative_blocks),

# To:
"entity_extraction": lambda: _run_entity_extraction(config, narrative_blocks, timeline),
```

- [ ] **Step 5: Run existing tests**

```bash
cd /home/openclaw/WorldForge/Worldforge && docker compose exec backend pytest tests/ -v
```

Expected: All existing tests should still pass (the old iterative path is preserved as fallback).

- [ ] **Step 6: Commit**

```bash
git add backend/app/narrator/entity_extraction.py backend/app/narrator/pipeline.py
git commit -m "feat: per-era entity extraction with cumulative context"
```

- [ ] **Step 7: Test entity extraction on Velmorath**

Create `backend/tests/test_entity_extraction_velmorath.py`:

```python
"""Integration test: entity extraction on Velmorath data.

Run inside the backend container:
    docker compose exec backend python -m pytest tests/test_entity_extraction_velmorath.py -v -s

This test hits the real LLM APIs — it's slow and costs tokens.
Skip in CI with: pytest -m "not integration"
"""

import asyncio
import json
import logging
import pytest
from sqlalchemy import select

logging.basicConfig(level=logging.INFO)

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_velmorath_entity_extraction():
    """Run per-era entity extraction on Velmorath and print results."""
    from app.database import async_session
    from app.models.world import World
    from app.narrator.entity_extraction import run_entity_extraction

    async with async_session() as db:
        result = await db.execute(
            select(World).where(World.name.ilike("%velmorath%"))
        )
        world = result.scalar_one_or_none()

    assert world is not None, "Velmorath not found in DB"
    assert world.config is not None, "Velmorath has no config"
    assert world.timeline is not None, "Velmorath has no timeline"
    assert world.narrative_blocks is not None, "Velmorath has no narrative_blocks"

    # Clear previous entities to test from scratch
    nb = dict(world.narrative_blocks)
    for key in list(nb.keys()):
        if key.startswith("entities_"):
            del nb[key]

    summary = await run_entity_extraction(
        config=world.config,
        narrative_blocks=nb,
        timeline=world.timeline,
        max_depth=4,
        on_progress=lambda msg: print(f"  >> {msg}"),
    )

    print("\n=== ENTITY EXTRACTION RESULTS ===")
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    # Minimum expectations for a 7-faction, 6-region world
    counts = summary.get("counts", {})
    total = summary.get("total_generated", 0)

    print(f"\nTotal generated: {total}")
    for entity_type, count in sorted(counts.items()):
        print(f"  {entity_type}: {count}")

    # Soft assertions — we want at least some variety
    assert total >= 5, f"Expected at least 5 entities, got {total}"
    assert len(counts) >= 3, f"Expected at least 3 entity types, got {len(counts)}"
```

Run it manually:

```bash
cd /home/openclaw/WorldForge/Worldforge && docker compose exec backend python -m pytest tests/test_entity_extraction_velmorath.py -v -s
```

Review the output. If the results are insufficient (< 5 entities, < 3 types), adjust the volume hints or prompts and re-run.

- [ ] **Step 8: Commit test file**

```bash
git add backend/tests/test_entity_extraction_velmorath.py
git commit -m "test: add Velmorath integration test for entity extraction"
```

---

### Task 6: Chapter page count in Bookstack export

**Files:**
- Modify: `backend/app/exporter/bookstack_client.py`
- Modify: `backend/app/exporter/pipeline.py`

- [ ] **Step 1: Add `update_chapter` to BookstackClient**

In `bookstack_client.py`, after the `create_chapter` method (after line 163), add:

```python
    async def update_chapter(
        self, chapter_id: int, *, description: str | None = None
    ) -> dict[str, Any]:
        """PUT /api/chapters/{id}"""
        payload: dict[str, Any] = {}
        if description is not None:
            payload["description"] = description
        return await self._put(f"/chapters/{chapter_id}", payload)
```

- [ ] **Step 2: Add chapter count update pass in pipeline.py**

In `pipeline.py`, after the cross-reference pass (after line 502), before the mapping build (before line 507), add:

```python
    # ------------------------------------------------------------------
    # Pass 3: update chapter descriptions with page counts
    # ------------------------------------------------------------------
    # Count pages per chapter
    chapter_page_counts: dict[int, int] = {}
    for p in pages_created:
        # Find which chapter this page belongs to by matching type to chapter key
        type_to_chapter = {
            "region": "atlas", "era": "chroniques", "faction": "factions",
            "race": "races", "cosmogony": "cosmogonies", "character": "personnages",
            "tech": "tech", "legend": "legendes", "fauna": "faune",
            "flora": "flore", "bestiary": "bestiaire", "location": "lieux",
            "resource": "ressources", "organization": "organisations",
            "artifact": "artefacts", "annex": "annexes",
        }
        ch_key = type_to_chapter.get(p.get("type", ""))
        if ch_key and ch_key in chapter_ids:
            ch_id = chapter_ids[ch_key]
            chapter_page_counts[ch_id] = chapter_page_counts.get(ch_id, 0) + 1

    # Update each chapter description with count
    for key, name, desc in chapter_defs:
        ch_id = chapter_ids[key]
        count = chapter_page_counts.get(ch_id, 0)
        new_desc = f"{desc} — {count} fiche{'s' if count != 1 else ''}"
        await client.update_chapter(ch_id, description=new_desc)

    logger.info("Updated chapter descriptions with page counts")
```

- [ ] **Step 3: Add test for update_chapter**

Append to `backend/tests/test_timeline_export_fixes.py`:

```python
def test_chapter_page_count_mapping():
    """Verify type-to-chapter mapping covers all page types."""
    type_to_chapter = {
        "region": "atlas", "era": "chroniques", "faction": "factions",
        "race": "races", "cosmogony": "cosmogonies", "character": "personnages",
        "tech": "tech", "legend": "legendes", "fauna": "faune",
        "flora": "flore", "bestiary": "bestiaire", "location": "lieux",
        "resource": "ressources", "organization": "organisations",
        "artifact": "artefacts", "annex": "annexes",
    }
    # All page types used in pipeline should be mapped
    expected_types = {
        "region", "era", "faction", "race", "cosmogony", "character",
        "tech", "legend", "fauna", "flora", "bestiary", "location",
        "resource", "organization", "artifact", "annex",
    }
    assert set(type_to_chapter.keys()) == expected_types
```

- [ ] **Step 4: Run tests**

```bash
cd /home/openclaw/WorldForge/Worldforge && docker compose exec backend pytest tests/test_timeline_export_fixes.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/exporter/bookstack_client.py backend/app/exporter/pipeline.py backend/tests/test_timeline_export_fixes.py
git commit -m "feat: update chapter descriptions with page counts after export"
```

---

### Task 7: Rebuild and verify

- [ ] **Step 1: Rebuild Docker containers**

```bash
cd /home/openclaw/WorldForge/Worldforge && docker compose up --build -d
```

- [ ] **Step 2: Run all tests**

```bash
cd /home/openclaw/WorldForge/Worldforge && docker compose exec backend pytest tests/ -v --ignore=tests/test_entity_extraction_velmorath.py
```

- [ ] **Step 3: Verify timeline in browser**

Navigate to `https://worldforge.ssantoro.fr`, open Velmorath, click "Chronologie". Verify events display with event IDs, factions, and regions.

- [ ] **Step 4: Run Velmorath entity extraction test**

```bash
cd /home/openclaw/WorldForge/Worldforge && docker compose exec backend python -m pytest tests/test_entity_extraction_velmorath.py -v -s
```

Review results. If insufficient, iterate on prompts in entity_extraction.py.

- [ ] **Step 5: Re-export Velmorath to Bookstack**

Trigger export from the UI or via API. Verify:
- Event narrative pages are populated (not empty)
- Only unlocked techs have pages
- Chapter descriptions show page counts
- Entity chapters have more entries than before
