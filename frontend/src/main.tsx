import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource-variable/inter";

import { ApiClient } from "./api/client";
import { App } from "./App";
import "./styles/tokens.css";

const api = new ApiClient(import.meta.env.VITE_API_BASE ?? "/api");

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App api={api} />
  </StrictMode>,
);
