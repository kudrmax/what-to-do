import "@fontsource-variable/inter";
import "../styles/tokens.css";
import "../styles/base.css";
import "../styles/interaction.css";
import "../ui/Screen.css";
import "../events/DayFeed.css";
import "../events/EventCardView.css";
import "../events/EventPhoto.css";
import "../events/EventWindow.css";
import "./phone.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { pageTheme } from "../app/theme";
import { PhoneApp } from "./PhoneApp";
import { PublishedFiles } from "./snapshot";

pageTheme();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <PhoneApp files={new PublishedFiles()} />
  </StrictMode>,
);
