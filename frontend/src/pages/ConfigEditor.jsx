import { useState, useEffect, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import { worlds } from "../services/api";
import WorldGraph from "../components/WorldGraph";
import styles from "../styles/ConfigEditor.module.css";

export default function ConfigEditor() {
  const { worldId } = useParams();

  const [world, setWorld] = useState(null);
  const [configText, setConfigText] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [saveError, setSaveError] = useState(null);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saving, setSaving] = useState(false);

  const fetchWorld = useCallback(async () => {
    try {
      const data = await worlds.get(worldId);
      setWorld(data);
      setConfigText(JSON.stringify(data.config || {}, null, 2));
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [worldId]);

  useEffect(() => {
    fetchWorld();
  }, [fetchWorld]);

  const isReadOnly =
    world?.status === "simulated" ||
    world?.status === "narrated" ||
    world?.status === "exported";

  const handleFormat = () => {
    try {
      const parsed = JSON.parse(configText);
      setConfigText(JSON.stringify(parsed, null, 2));
      setSaveError(null);
    } catch (err) {
      setSaveError("JSON invalide : " + err.message);
    }
  };

  const handleSave = async () => {
    setSaveError(null);
    setSaveSuccess(false);

    let parsed;
    try {
      parsed = JSON.parse(configText);
    } catch (err) {
      setSaveError("JSON invalide : " + err.message);
      return;
    }

    setSaving(true);
    try {
      await worlds.updateConfig(worldId, parsed);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err) {
      setSaveError(err.detail || err.message);
    } finally {
      setSaving(false);
    }
  };

  // Parse config for graph
  let parsedConfig = null;
  try {
    parsedConfig = JSON.parse(configText);
  } catch {
    // invalid JSON, skip graph
  }

  if (loading) {
    return (
      <div className={styles.loadingPage}>
        <div className={styles.spinner} />
        Chargement...
      </div>
    );
  }

  if (error && !world) {
    return <div className={styles.error}>{error}</div>;
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1 className={styles.title}>Configuration</h1>
        <Link to={`/world/${worldId}`} className={styles.backLink}>
          Retour au monde
        </Link>
      </div>

      <div className={styles.content}>
        {isReadOnly && (
          <div className={styles.readOnlyBanner}>
            Ce monde a deja ete simule. La configuration est en lecture seule.
          </div>
        )}

        <div className={styles.editorWrap}>
          <textarea
            className={`${styles.editor} ${isReadOnly ? styles.readOnly : ""}`}
            value={configText}
            onChange={(e) => {
              setConfigText(e.target.value);
              setSaveSuccess(false);
            }}
            readOnly={isReadOnly}
            spellCheck={false}
          />
        </div>

        {!isReadOnly && (
          <div className={styles.toolbar}>
            <button
              className={styles.saveBtn}
              onClick={handleSave}
              disabled={saving}
            >
              {saving ? "Sauvegarde..." : "Sauvegarder"}
            </button>
            <button className={styles.formatBtn} onClick={handleFormat}>
              Formater
            </button>
            {saveSuccess && (
              <span className={styles.successMsg}>
                Configuration sauvegardee.
              </span>
            )}
          </div>
        )}

        {saveError && <div className={styles.errorMsg}>{saveError}</div>}

        {parsedConfig &&
          parsedConfig.factions &&
          parsedConfig.factions.length > 0 && (
            <div className={styles.graphSection}>
              <h3>Relations entre factions</h3>
              <WorldGraph config={parsedConfig} />
            </div>
          )}
      </div>
    </div>
  );
}
