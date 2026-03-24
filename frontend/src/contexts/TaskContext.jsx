import { createContext, useContext, useState, useEffect, useCallback, useRef } from "react";
import { wsService } from "../services/websocket";
import { apiFetch } from "../services/api";

const TaskContext = createContext(null);

export function TaskProvider({ children }) {
  const [tasks, setTasks] = useState([]);
  const unsubRef = useRef(null);

  // Fetch initial active tasks from REST endpoint
  const fetchTasks = useCallback(async () => {
    try {
      const data = await apiFetch("/tasks/");
      const list = Array.isArray(data) ? data : data.tasks || [];
      setTasks(list.filter((t) => t.status !== "completed" && t.status !== "failed"));
    } catch {
      // Endpoint may not exist yet, silently ignore
    }
  }, []);

  useEffect(() => {
    // Connect WebSocket
    wsService.connect();
    fetchTasks();

    // Listen for task_update events
    unsubRef.current = wsService.on("task_update", (data) => {
      setTasks((prev) => {
        const idx = prev.findIndex((t) => t.task_id === data.task_id);
        if (data.status === "completed" || data.status === "failed") {
          // Keep completed/failed briefly so UI can react, then remove
          if (idx >= 0) {
            const updated = [...prev];
            updated[idx] = { ...updated[idx], ...data };
            // Remove after 3 seconds
            setTimeout(() => {
              setTasks((current) => current.filter((t) => t.task_id !== data.task_id));
            }, 3000);
            return updated;
          }
          return prev;
        }
        if (idx >= 0) {
          const updated = [...prev];
          updated[idx] = { ...updated[idx], ...data };
          return updated;
        }
        return [...prev, data];
      });
    });

    return () => {
      unsubRef.current?.();
      wsService.disconnect();
    };
  }, [fetchTasks]);

  const getWorldTasks = useCallback(
    (worldId) => tasks.filter((t) => t.world_id === worldId),
    [tasks]
  );

  const isTaskRunning = useCallback(
    (worldId, type) =>
      tasks.some(
        (t) =>
          t.world_id === worldId &&
          (!type || t.task_type === type) &&
          t.status !== "completed" &&
          t.status !== "failed"
      ),
    [tasks]
  );

  const getTask = useCallback(
    (worldId, type) =>
      tasks.find(
        (t) => t.world_id === worldId && (!type || t.task_type === type)
      ),
    [tasks]
  );

  return (
    <TaskContext.Provider value={{ tasks, getWorldTasks, isTaskRunning, getTask }}>
      {children}
    </TaskContext.Provider>
  );
}

export function useTask() {
  const ctx = useContext(TaskContext);
  if (!ctx) {
    throw new Error("useTask must be used within TaskProvider");
  }
  return ctx;
}
