import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
// Bundled, so the demo renders the same without internet access.
import "@fontsource-variable/public-sans";
import "@fontsource-variable/source-serif-4";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
