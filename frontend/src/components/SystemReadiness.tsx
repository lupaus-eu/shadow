import { useEffect, useState } from "react";

import { loadSystemRevision } from "../auth-client";
import { messages, type Locale } from "../i18n";

type SystemStatus =
  | { state: "loading" }
  | { state: "ready"; schemaRevision: string }
  | { state: "error" };

export function SystemReadiness({ locale }: { locale: Locale }) {
  const [systemStatus, setSystemStatus] = useState<SystemStatus>({
    state: "loading",
  });
  const copy = messages(locale);

  useEffect(() => {
    const controller = new AbortController();

    async function load() {
      try {
        setSystemStatus({
          state: "ready",
          schemaRevision: await loadSystemRevision(controller.signal),
        });
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setSystemStatus({ state: "error" });
      }
    }

    void load();
    return () => controller.abort();
  }, []);

  const dot = systemStatus.state === "ready" ? "bg-accent" : systemStatus.state === "error" ? "bg-danger" : "bg-sidebar-muted";
  return (
    <div className="flex items-center gap-2 text-[11px] text-sidebar-muted" role="status">
      <span className={`size-1.5 shrink-0 rounded-full ${dot}`} aria-hidden="true" />
      {systemStatus.state === "loading" && copy.systemConnecting}
      {systemStatus.state === "ready" &&
        copy.systemReady(systemStatus.schemaRevision)}
      {systemStatus.state === "error" && copy.systemUnavailable}
    </div>
  );
}
