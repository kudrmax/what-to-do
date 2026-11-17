import "@fontsource-variable/inter";
import "../styles/tokens.css";
import "../styles/base.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { pageTheme } from "../app/theme";
import { PhoneApp } from "./PhoneApp";
import { PublishedFiles } from "./snapshot";
import "../styles/narrow.css";
import "../styles/interaction.css";
import "./phone.css";

pageTheme();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <PhoneApp files={new PublishedFiles()} />
  </StrictMode>,
);
