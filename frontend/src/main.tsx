import "@fontsource-variable/inter";
import "./styles/tokens.css";
import "./styles/base.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { createApi } from "./api/client";
import { App } from "./App";
import "./styles/narrow.css";

const API_PREFIX = "/api";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App api={createApi(import.meta.env.VITE_API_BASE ?? API_PREFIX)} />
  </StrictMode>,
);
