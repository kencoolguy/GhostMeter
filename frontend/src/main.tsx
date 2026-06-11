import { App as AntdApp, ConfigProvider } from "antd";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { ghostMeterTheme } from "./theme/antdTheme";
import "./styles/global.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ConfigProvider theme={ghostMeterTheme}>
      <AntdApp>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </AntdApp>
    </ConfigProvider>
  </StrictMode>
);
