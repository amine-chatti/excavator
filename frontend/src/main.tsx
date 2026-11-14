import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { MotionConfig } from "motion/react";
import "./index.css";
import "@fontsource-variable/fraunces";
import "@fontsource-variable/jetbrains-mono";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <MotionConfig reducedMotion="user">
      <App />
    </MotionConfig>
  </React.StrictMode>,
);
