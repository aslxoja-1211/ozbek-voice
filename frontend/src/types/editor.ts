export type ActionType = "APPEND" | "REPLACE" | "DELETE" | "FORMAT";
export type ClientActionType = "UNDO" | "REDO";
export type TranslationLanguage = "ru" | "en";

export interface TranslateResponse {
  source_text: string;
  target_language: TranslationLanguage;
  translated_text: string;
  provider: string;
  latency_ms: number;
  note?: string | null;
}

export interface EditorEditCommand {
  action: ActionType;
  target: string;
  replacement: string;
  updated_full_text: string | null;
  confidence: number;
}

export interface TextSpan {
  start: number;
  end: number;
  matched_text: string;
}

export interface ApplyResult {
  previous_text: string;
  new_text: string;
  changed: boolean;
  applied_strategy: string;
  matched_span?: TextSpan | null;
  format_hint?: string | null;
}

export interface LatencyMetrics {
  stt_ms: number;
  llm_ms: number;
  diff_ms: number;
  total_ms: number;
}

export interface ProviderInfo {
  stt_provider: string;
  llm_provider: string;
  stt_is_mock: boolean;
  llm_is_mock: boolean;
}

export interface PipelineResponse {
  raw_transcript: string;
  command: EditorEditCommand;
  diff: ApplyResult;
  latency: LatencyMetrics;
  providers: ProviderInfo;
  client_action?: ClientActionType | null;
  note?: string | null;
}

export type WSServerMessage =
  | { type: "connected"; active_stt: string; active_llm: string }
  | { type: "utterance_started" }
  | { type: "pong" }
  | { type: "status"; stage: string }
  | { type: "result"; payload: PipelineResponse }
  | { type: "translation_status"; target_language: TranslationLanguage }
  | { type: "translation_result"; payload: TranslateResponse }
  | { type: "translation_error"; message: string }
  | { type: "error"; message: string };

export interface HistoryEntry {
  id: string;
  timestamp: string;
  rawTranscript: string;
  command: EditorEditCommand;
  strategy: string;
  totalMs: number;
}
