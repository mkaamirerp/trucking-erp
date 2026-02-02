import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { MeProvider } from "./hooks/useMe";
import { AuthProvider } from "./contexts/AuthContext";
import "./index.css";
import "./styles/company-setup.css";
import "./styles/login.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <MeProvider>
          <App />
        </MeProvider>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>
);
