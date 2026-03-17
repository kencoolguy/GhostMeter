import { Navigate, Route, Routes } from "react-router-dom";
import { MainLayout } from "./layouts/MainLayout";
import DevicesPage from "./pages/Devices";
import DeviceDetail from "./pages/Devices/DeviceDetail";
import MonitorPage from "./pages/Monitor";
import SimulationPage from "./pages/Simulation";
import TemplatesPage from "./pages/Templates";
import TemplateForm from "./pages/Templates/TemplateForm";

function App() {
  return (
    <Routes>
      <Route element={<MainLayout />}>
        <Route path="/templates/new" element={<TemplateForm />} />
        <Route path="/templates/:id" element={<TemplateForm />} />
        <Route path="/templates" element={<TemplatesPage />} />
        <Route path="/devices/:id" element={<DeviceDetail />} />
        <Route path="/devices" element={<DevicesPage />} />
        <Route path="/simulation" element={<SimulationPage />} />
        <Route path="/monitor" element={<MonitorPage />} />
        <Route path="/" element={<Navigate to="/templates" replace />} />
      </Route>
    </Routes>
  );
}

export default App;
