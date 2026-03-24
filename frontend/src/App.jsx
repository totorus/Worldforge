import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import { TaskProvider } from "./contexts/TaskContext";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Wizard from "./pages/Wizard";
import WorldView from "./pages/WorldView";
import Timeline from "./pages/Timeline";
import Narrative from "./pages/Narrative";
import ConfigEditor from "./pages/ConfigEditor";

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "100vh", color: "var(--text-secondary)" }}>
        Chargement...
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return children;
}

function AppRoutes() {
  const { user, loading } = useAuth();

  return (
    <Routes>
      <Route
        path="/login"
        element={
          !loading && user ? <Navigate to="/dashboard" replace /> : <Login />
        }
      />
      <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
      <Route path="/wizard" element={<ProtectedRoute><Wizard /></ProtectedRoute>} />
      <Route path="/wizard/:sessionId" element={<ProtectedRoute><Wizard /></ProtectedRoute>} />
      <Route path="/world/:worldId" element={<ProtectedRoute><WorldView /></ProtectedRoute>} />
      <Route path="/world/:worldId/timeline" element={<ProtectedRoute><Timeline /></ProtectedRoute>} />
      <Route path="/world/:worldId/narrative" element={<ProtectedRoute><Narrative /></ProtectedRoute>} />
      <Route path="/world/:worldId/config" element={<ProtectedRoute><ConfigEditor /></ProtectedRoute>} />
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <TaskProvider>
          <AppRoutes />
        </TaskProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
