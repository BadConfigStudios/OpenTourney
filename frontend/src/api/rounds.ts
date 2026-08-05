import { apiRequest, type ApiFetch } from "./request";
import type { MatchRead } from "./matches";

export interface RoundRead {
  id: string;
  pod_id: string;
  number: number;
  matches: MatchRead[];
}

export function fetchRounds(apiFetch: ApiFetch, podId: string): Promise<RoundRead[]> {
  return apiRequest(apiFetch, `/pods/${podId}/rounds`);
}

export function generateRound(apiFetch: ApiFetch, podId: string): Promise<RoundRead> {
  return apiRequest(apiFetch, `/pods/${podId}/rounds`, { method: "POST" });
}
