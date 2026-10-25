import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import Root from "./Root";
import "./index.css";

// Night mode is remembered on this device (the moon button in the top bar).
if (localStorage.getItem("coach-theme") === "dark") document.documentElement.dataset.theme = "dark";

// An open tab keeps running the code it first loaded. When a newer build is deployed, reload it (checked when the
// tab comes back into view and every 5 minutes; never while typing). Production only: the dev server updates itself.
if (import.meta.env.PROD) {
  const mine = [...document.scripts].map((s) => s.src).find((src) => src.includes("/assets/index-")) ?? "";
  const check = () =>
    fetch("/api/version", { cache: "no-store" })
      .then((r) => r.json())
      .then((v: { script?: string }) => {
        const typing = document.activeElement instanceof HTMLInputElement || document.activeElement instanceof HTMLTextAreaElement;
        if (v.script && mine && !mine.endsWith(v.script) && !typing) location.reload();
      })
      .catch(() => {});
  document.addEventListener("visibilitychange", () => document.visibilityState === "visible" && check());
  window.addEventListener("focus", check);
  setInterval(check, 5 * 60 * 1000);
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
);
