import { useConfig } from "../config/ConfigProvider";
import { useAuth } from "./AuthContext";

export function PersonaSwitcher() {
  const { personas } = useConfig();
  const { currentPersona, setPersona } = useAuth();

  return (
    <label className="flex items-center gap-2 text-sm">
      Persona
      <select
        aria-label="persona"
        className="rounded border border-gray-300 px-2 py-1"
        value={currentPersona.label}
        onChange={(event) => setPersona(event.target.value)}
      >
        {personas.map((persona) => (
          <option key={persona.label} value={persona.label}>
            {persona.label}
          </option>
        ))}
      </select>
    </label>
  );
}
