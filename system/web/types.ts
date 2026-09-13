export type Participant = {
  id: string; session_id: string; slot: 'A' | 'B'; generation: number; revision: number;
  step: 'consent' | 'tutorial' | 'question' | 'map' | 'complete';
  question: number; status: 'ready' | 'countdown' | 'processing' | 'result' | 'error';
  countdown_ends_at: string | null; active_job_id: string | null; error_code: string | null;
  pin: { lng: number; lat: number } | null; updated_at: string;
};
export type Response = {
  question: number; attempt: number;
  result: { raw_response: string; translated_response: string; keywords: string[]; trace: string;
    classification: unknown; processing_mode?: string; analysis_status?: string };
};
export type Snapshot = { participant: Participant; responses: Response[]; server_now: string };
export type Entry = { id: string; slot: string; token: string };
export type Created = { session_id: string; entries: Entry[] };
export type OperatorState = {
  sessions: { id: string; created_at: string }[]; participants: Participant[];
  health: { last_seen_at: string; mode: string } | null; server_now: string;
};
