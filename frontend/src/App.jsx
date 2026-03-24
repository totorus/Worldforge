import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Wizard from "./pages/Wizard";
import WorldView from "./pages/WorldView";
import Timeline from "./pages/Timeline";
import Narrative from "./pages/Narrative";
import ConfigEditor from "./pages/ConfigEditor";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/wizard/:sessionId" element={<Wizard />} />
        <Route path="/world/:worldId" element={<WorldView />} />
        <Route path="/world/:worldId/timeline" element={<Timeline />} />
        <Route path="/world/:worldId/narrative" element={<Narrative />} />
        <Route path="/world/:worldId/config" element={<ConfigEditor />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
