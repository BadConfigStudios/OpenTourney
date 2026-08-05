export type PersonaRole = "organizer" | "scorekeeper" | "player";

export interface Persona {
  label: string;
  role: PersonaRole;
  token: string;
}

export interface AppConfig {
  personas: Persona[];
}
