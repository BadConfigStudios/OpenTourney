import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import type { AppConfig } from "./types";

const ConfigContext = createContext<AppConfig | null>(null);

export function useConfig(): AppConfig {
  const config = useContext(ConfigContext);
  if (config === null) {
    throw new Error("useConfig must be used within a ConfigProvider");
  }
  return config;
}

type LoadState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; config: AppConfig };

export function ConfigProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;

    fetch("/config.json")
      .then((response) => {
        if (!response.ok) throw new Error(`config.json request failed: ${response.status}`);
        return response.json() as Promise<AppConfig>;
      })
      .then((config) => {
        if (!Array.isArray(config.personas) || config.personas.length === 0) {
          throw new Error("config.json has no personas or personas is not an array");
        }
        const hasInvalidPersona = config.personas.some(
          (persona) =>
            typeof persona.label !== "string" ||
            persona.label.length === 0 ||
            typeof persona.role !== "string" ||
            persona.role.length === 0 ||
            typeof persona.token !== "string" ||
            persona.token.length === 0,
        );
        if (hasInvalidPersona) {
          throw new Error("config.json has a persona missing a non-empty label, role, or token");
        }
        if (!cancelled) setState({ status: "ready", config });
      })
      .catch((error) => {
        console.error("config.json load failed", error);
        if (!cancelled) setState({ status: "error" });
      });

    return () => {
      cancelled = true;
    };
  }, []);

  if (state.status === "loading") {
    return <div className="p-8 text-center text-gray-500">Loading…</div>;
  }

  if (state.status === "error") {
    return (
      <div className="p-8 text-center text-red-600">
        Failed to load app configuration. Try reloading the page.
      </div>
    );
  }

  return <ConfigContext.Provider value={state.config}>{children}</ConfigContext.Provider>;
}
