import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import { StoreProvider } from "./store.jsx";
import "./i18n.js";
import "./fonts.css";
import "./styles.css";
import "./screen-type.css";
import "./green-glass.css";
import "./jotva-theme.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <StoreProvider>
      <App />
    </StoreProvider>
  </React.StrictMode>
);
