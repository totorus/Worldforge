import { useState, useEffect, useCallback, useRef } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { worlds, simulate, narrate, exportApi } from "../services/api";
import { useTask } from "../contexts/TaskContext";
import TaskProgress from "../components/TaskProgress";
import styles from "../styles/WorldView.module.css";

const STATUS_LABELS = {
  draft: "Brouillon",
  configured: "Configure",
  simulated: "Simule",
  narrated: "Narre",
  exported: "Exporte",
};

const TABS = [
  { key: "summary", label: "Resume" },
  { key: "timeline", label: "Timeline" },
  { key: "narrative", label: "Narration" },
  { key: "config", label: "Configuration" },
];

export default function WorldView() {
  const { worldId } = useParams();
  const navigate = useNavigate();
  const { isTaskRunning, getTask, tasks } = useTask();

  const [world, setWorld] = useState(null);
  const [activeTab, setActiveTab] = useState("summary");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const currentTask = getTask(worldId);
  const taskRunning = isTaskRunning(worldId);

  const fetchWorld = useCallback(async () => {
    try {
      const data = await worlds.get(worldId);
      setWorld(data);
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

  // Auto-refresh world data when a task completes or fails
  const prevTasksRef = useRef(tasks);
  useEffect(() => {
    const prevWorldTasks = prevTasksRef.current.filter((t) => t.world_id === worldId);
    const curWorldTasks = tasks.filter((t) => t.world_id === worldId);

    // Check if any task just became completed/failed
    for (const task of curWorldTasks) {
      if (task.status === "completed" || task.status === "failed") {
        const prev = prevWorldTasks.find((t) => t.task_id === task.task_id);
        if (prev && prev.status !== task.status) {
          fetchWorld();
          if (task.status === "failed" && task.error) {
            setError(task.error);
          }
          break;
        }
      }
    }
    prevTasksRef.current = tasks;
  }, [tasks, worldId, fetchWorld]);

  const handleSimulate = async () => {
    setError(null);
    try {
      await simulate.run(worldId);
      // Task progress now handled via WebSocket
    } catch (err) {
      setError(err.message);
    }
  };

  const handleNarrate = async () => {
    setError(null);
    try {
      await narrate.run(worldId);
    } catch (err) {
      setError(err.message);
    }
  };

  const handleExport = async () => {
    setError(null);
    try {
      await exportApi.toBookstack(worldId);
    } catch (err) {
      setError(err.message);
    }
  };

  const handleDelete = async () => {
    if (!window.confirm("Supprimer definitivement ce monde ?")) return;
    try {
      await worlds.delete(worldId);
      navigate("/dashboard");
    } catch (err) {
      setError(err.message);
    }
  };

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

  const config = world?.config || {};
  const status = world?.status || "draft";
  const canSimulate = ["configured", "simulated", "narrated", "exported"].includes(status);
  const canNarrate = ["simulated", "narrated", "exported"].includes(status);
  const canExport = ["narrated", "exported"].includes(status);

  const factionCount = config.factions?.length || 0;
  const regionCount = config.geography?.regions?.length || 0;
  const resourceCount = config.resources?.length || 0;
  const timelineYears = config.meta?.simulation_years || world?.simulation_years || 0;

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div className={styles.headerTop}>
          <Link to="/dashboard" className={styles.backLink}>
            Retour aux mondes
          </Link>
        </div>
        <h1 className={styles.worldName}>
          {world.name || "Monde sans nom"}
          <span className={`${styles.badge} ${styles[status]}`}>
            {STATUS_LABELS[status] || status}
          </span>
        </h1>

        <div className={styles.tabs}>
          {TABS.map((tab) => (
            <button
              key={tab.key}
              className={`${styles.tab} ${
                activeTab === tab.key ? styles.active : ""
              }`}
              onClick={() => setActiveTab(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      <div className={styles.content}>
        {error && <div className={styles.error}>{error}</div>}

        {activeTab === "summary" && (
          <>
            <div className={styles.statsGrid}>
              <div className={styles.statCard}>
                <div className={styles.statValue}>{factionCount}</div>
                <div className={styles.statLabel}>Factions</div>
              </div>
              <div className={styles.statCard}>
                <div className={styles.statValue}>{regionCount}</div>
                <div className={styles.statLabel}>Regions</div>
              </div>
              <div className={styles.statCard}>
                <div className={styles.statValue}>{resourceCount}</div>
                <div className={styles.statLabel}>Ressources</div>
              </div>
              <div className={styles.statCard}>
                <div className={styles.statValue}>{timelineYears}</div>
                <div className={styles.statLabel}>Annees</div>
              </div>
            </div>

            {currentTask && (
              <div style={{ marginBottom: 16 }}>
                <TaskProgress task={currentTask} />
              </div>
            )}

            <div className={styles.actions}>
              {canSimulate && (
                <button
                  className={`${styles.actionBtn} ${styles.simulate}`}
                  onClick={handleSimulate}
                  disabled={taskRunning}
                >
                  Simuler
                </button>
              )}
              {canNarrate && (
                <button
                  className={`${styles.actionBtn} ${styles.narrate}`}
                  onClick={handleNarrate}
                  disabled={taskRunning}
                >
                  Narrer
                </button>
              )}
              {canExport && (
                <button
                  className={`${styles.actionBtn} ${styles.export}`}
                  onClick={handleExport}
                  disabled={taskRunning}
                >
                  Exporter vers Wiki
                </button>
              )}
              <Link
                to={`/world/${worldId}/config`}
                className={`${styles.actionBtn} ${styles.config}`}
                style={{ textDecoration: "none" }}
              >
                Configuration
              </Link>
              <button
                className={`${styles.actionBtn} ${styles.delete}`}
                onClick={handleDelete}
                disabled={taskRunning}
              >
                Supprimer
              </button>
            </div>

            <div className={styles.links}>
              {(status === "simulated" ||
                status === "narrated" ||
                status === "exported") && (
                <Link
                  to={`/world/${worldId}/timeline`}
                  className={styles.link}
                >
                  Voir la chronologie
                </Link>
              )}
              {(status === "narrated" || status === "exported") && (
                <Link
                  to={`/world/${worldId}/narrative`}
                  className={styles.link}
                >
                  Lire la narration
                </Link>
              )}
            </div>
          </>
        )}

        {activeTab === "timeline" && (
          <div>
            <Link to={`/world/${worldId}/timeline`} className={styles.link}>
              Ouvrir la chronologie complete
            </Link>
          </div>
        )}

        {activeTab === "narrative" && (
          <div>
            <Link to={`/world/${worldId}/narrative`} className={styles.link}>
              Ouvrir la narration complete
            </Link>
          </div>
        )}

        {activeTab === "config" && (
          <div className={styles.configSection}>
            <h3>Configuration JSON</h3>
            <pre className={styles.configPre}>
              {JSON.stringify(config, null, 2)}
            </pre>
            <div style={{ marginTop: 16 }}>
              <Link
                to={`/world/${worldId}/config`}
                className={styles.link}
              >
                Editer la configuration
              </Link>
            </div>
          </div>
        )}
      </div>

      {taskRunning && (
        <div className={styles.progressOverlay}>
          <div className={styles.progressBox}>
            <TaskProgress task={currentTask} />
            <p style={{ color: "var(--text-secondary)", marginTop: 8 }}>
              Cette operation peut prendre plusieurs minutes.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
