export type PersonaRole = "organizer" | "scorekeeper" | "player";

export interface AppConfig {
  oidcAuthority: string;
  oidcClientId: string;
}
