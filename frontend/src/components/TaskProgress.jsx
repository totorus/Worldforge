import styles from "../styles/TaskProgress.module.css";

const TYPE_LABELS = {
  simulation: "Simulation",
  narration: "Narration",
  export: "Export",
};

export default function TaskProgress({ task }) {
  if (!task) return null;

  const label = TYPE_LABELS[task.task_type] || task.task_type || "Tache";
  const progress = task.progress ?? 0;
  const isError = task.status === "failed";
  const isDone = task.status === "completed";
  const message = task.message || (isDone ? "Termine !" : isError ? "Erreur" : "En cours...");

  return (
    <div className={`${styles.container} ${isError ? styles.error : ""} ${isDone ? styles.done : ""}`}>
      <div className={styles.header}>
        <span className={styles.label}>{label}</span>
        <span className={styles.percent}>{Math.round(progress)}%</span>
      </div>
      <div className={styles.barTrack}>
        <div
          className={`${styles.barFill} ${isError ? styles.barError : ""} ${isDone ? styles.barDone : ""}`}
          style={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
        />
      </div>
      <div className={styles.message}>
        {isError && task.error ? task.error : message}
      </div>
    </div>
  );
}
