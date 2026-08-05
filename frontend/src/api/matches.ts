import { apiRequest, jsonInit, type ApiFetch } from "./request";

export type MatchResult = "unreported" | "entry1_win" | "entry2_win" | "tie";

export interface MatchRead {
  id: string;
  round_id: string;
  entry1_id: string;
  entry2_id: string | null;
  result: MatchResult;
  reported_by: string | null;
  witnessed_by: string | null;
  table_number: number | null;
  method: string;
}

export function reportMatchResult(
  apiFetch: ApiFetch,
  matchId: string,
  result: "entry1_win" | "entry2_win" | "tie",
): Promise<MatchRead> {
  return apiRequest(
    apiFetch,
    `/matches/${matchId}/result`,
    jsonInit("POST", { result, method: "manual_entry" }),
  );
}
