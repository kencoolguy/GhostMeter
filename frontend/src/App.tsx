import { Navigate, Route, Routes } from "react-router-dom";
import { MainLayout } from "./layouts/MainLayout";
import DevicesPage from "./pages/Devices";
import MonitorPage from "./pages/Monitor";
import SimulationPage from "./pages/Simulation";
import TemplatesPage from "./pages/Templates";

function App() {
  return (
    <Routes>
      <Route element={<MainLayout />}>
        <Route path="/templates" element={<TemplatesPage />} />
        <Route path="/devices" element={<DevicesPage />} />
        <Route path="/simulation" element={<SimulationPage />} />
        <Route path="/monitor" element={<MonitorPage />} />
        <Route path="/" element={<Navigate to="/templates" replace />} />
      </Route>
    </Routes>
  );
}

export default App;
