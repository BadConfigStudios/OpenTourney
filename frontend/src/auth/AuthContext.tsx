import { useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { useConfig } from "../config/ConfigProvider";
import type { Persona } from "../config/types";

const STORAGE_KEY = "opentourney.persona";

interface AuthValue {
  currentPersona: Persona;
  setPersona: (label: string) => void;
  apiFetch: (path: string, init?: RequestInit) => Promise<Response>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (value === null) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return value;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const { personas } = useConfig();
  const queryClient = useQueryClient();

  const [personaLabel, setPersonaLabel] = useState<string>(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored && personas.some((p) => p.label === stored) ? stored : personas[0].label;
  });

  const currentPersona = personas.find((p) => p.label === personaLabel) ?? personas[0];

  const value = useMemo<AuthValue>(
    () => ({
      currentPersona,
      setPersona: (label: string) => {
        localStorage.setItem(STORAGE_KEY, label);
        setPersonaLabel(label);
        queryClient.clear();
      },
      apiFetch: (path: string, init: RequestInit = {}) =>
        fetch(path, {
          ...init,
          headers: { ...init.headers, Authorization: `Bearer ${currentPersona.token}` },
        }),
    }),
    [currentPersona, queryClient],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
