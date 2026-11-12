import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/layout.css";
import "./styles/sidebar.css";
import "./styles/meeting.css";
import { App } from "./App";

const rootEl = document.getElementById("root") || document.body;
createRoot(rootEl).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
