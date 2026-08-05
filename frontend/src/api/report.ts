import { apiRequest, type ApiFetch } from "./request";

export interface StandingRow {
  entry_id: string;
  points: number;
  rank: number;
}

export interface PodReport {
  is_complete: boolean;
  rounds_played: number;
  is_partial: boolean;
  standings: StandingRow[];
}

export function fetchPodReport(apiFetch: ApiFetch, podId: string): Promise<PodReport> {
  return apiRequest(apiFetch, `/pods/${podId}/report`);
}
