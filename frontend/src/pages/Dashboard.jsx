import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { useTask } from "../contexts/TaskContext";
import { worlds as worldsApi, wizard as wizardApi, simulate, narrate, exportApi } from "../services/api";
import WorldCard from "../components/WorldCard";
import TaskProgress from "../components/TaskProgress";
import styles from "../styles/Dashboard.module.css";

export default function Dashboard() {
  const [worldList, setWorldList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const { user, logout } = useAuth();
  const { isTaskRunning, getTask, tasks } = useTask();
  const navigate = useNavigate();

  const fetchWorlds = useCallback(async () => {
    try {
      const data = await worldsApi.list();
      setWorldList(Array.isArray(data) ? data : data.worlds || []);
    } catch (err) {
      setError(err.detail || err.message || "Impossible de charger les mondes");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchWorlds();
  }, [fetchWorlds]);

  // Auto-refresh world list when tasks complete
  useEffect(() => {
    const completedOrFailed = tasks.filter(
      (t) => t.status === "completed" || t.status === "failed"
    );
    if (completedOrFailed.length > 0) {
      fetchWorlds();
    }
  }, [tasks, fetchWorlds]);

  async function handleNewWorld() {
    setCreating(true);
    setError("");
    try {
      const data = await wizardApi.start();
      navigate(`/wizard/${data.session_id}`);
    } catch (err) {
      setError(err.detail || err.message || "Impossible de démarrer le wizard");
      setCreating(false);
    }
  }

  async function handleSimulate(worldId) {
    setError("");
    try {
      await simulate.run(worldId);
      await fetchWorlds();
    } catch (err) {
      setError(err.detail || err.message || "Erreur lors de la simulation");
    }
  }

  async function handleNarrate(worldId) {
    setError("");
    try {
      await narrate.run(worldId);
      await fetchWorlds();
    } catch (err) {
      setError(err.detail || err.message || "Erreur lors de la narration");
    }
  }

  async function handleExport(worldId) {
    setError("");
    try {
      await exportApi.toBookstack(worldId);
      await fetchWorlds();
    } catch (err) {
      setError(err.detail || err.message || "Erreur lors de l'export");
    }
  }

  async function handleDelete(worldId) {
    setError("");
    try {
      await worldsApi.delete(worldId);
      setWorldList((prev) => prev.filter((w) => w.id !== worldId));
    } catch (err) {
      setError(err.detail || err.message || "Erreur lors de la suppression");
    }
  }

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <h1>Mes Mondes</h1>
          {user && <p>Bienvenue, {user.email}</p>}
        </div>
        <div className={styles.headerActions}>
          <button
            className={`btn-primary ${styles.btnNew}`}
            onClick={handleNewWorld}
            disabled={creating}
          >
            + Nouveau Monde
          </button>
          <button
            className={`btn-secondary ${styles.btnLogout}`}
            onClick={handleLogout}
          >
            Déconnexion
          </button>
        </div>
      </div>

      {error && <div className={styles.error}>{error}</div>}

      {loading ? (
        <div className={styles.loading}>Chargement de vos mondes...</div>
      ) : worldList.length === 0 ? (
        <div className={styles.empty}>
          <h2>Aucun monde pour l'instant</h2>
          <p>
            Créez votre premier monde en lançant le wizard conversationnel.
          </p>
          <button
            className="btn-primary"
            onClick={handleNewWorld}
            disabled={creating}
          >
            + Créer un monde
          </button>
        </div>
      ) : (
        <div className={styles.grid}>
          {worldList.map((world) => {
            const worldRunning = isTaskRunning(world.id);
            const worldTask = getTask(world.id);
            return (
              <div key={world.id} style={{ position: "relative" }}>
                <WorldCard
                  world={world}
                  onClick={() => navigate(`/world/${world.id}`)}
                  onSimulate={worldRunning ? undefined : () => handleSimulate(world.id)}
                  onNarrate={worldRunning ? undefined : () => handleNarrate(world.id)}
                  onExport={worldRunning ? undefined : () => handleExport(world.id)}
                  onDelete={worldRunning ? undefined : () => handleDelete(world.id)}
                />
                {worldTask && worldTask.status !== "completed" && worldTask.status !== "failed" && (
                  <div style={{
                    position: "absolute",
                    bottom: 0,
                    left: 0,
                    right: 0,
                    padding: "0 8px 8px",
                    background: "linear-gradient(transparent, rgba(0,0,0,0.8))",
                    borderRadius: "0 0 8px 8px",
                  }}>
                    <TaskProgress task={worldTask} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
