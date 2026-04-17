export type DraftStatus =
  | "uploaded"
  | "generated"
  | "reviewing"
  | "publish_failed"
  | "published";

export interface QuestionChoice {
  content: string;
  is_correct: boolean;
}

export interface PassageQuestion {
  order: number;
  type: "multiple_choice";
  question: string;
  choices: QuestionChoice[];
}

export interface PassageGroup {
  order: number;
  passage: string;
  questions: PassageQuestion[];
}

export interface PassageExamDocument {
  title: string;
  description: string;
  groups: PassageGroup[];
}

export interface PublishResultPayload {
  source_hash: string;
  parent_question_ids: string[];
  child_question_ids: string[];
  exam_id?: string | null;
  material_id?: string | null;
  skipped: boolean;
  duplicate_material_id?: string | null;
}

export interface DraftSummary {
  id: string;
  title: string;
  description: string;
  status: DraftStatus;
  source_filename: string;
  source_extension: string;
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
  published_at?: string | null;
  error_message?: string | null;
  publish_result?: PublishResultPayload | null;
}

export interface DraftEvent {
  id: string;
  draft_id: string;
  event_type: string;
  payload_json: Record<string, unknown>;
  actor_id: string;
  created_at: string;
}

export interface DraftDetail extends DraftSummary {
  source_text: string;
  normalized_document_json?: PassageExamDocument | null;
  generation_params_json?: Record<string, unknown> | null;
  events: DraftEvent[];
}

export interface ValidationIssue {
  path: string;
  message: string;
  issue_type: string;
}

export interface ValidationResponse {
  valid: boolean;
  issues: ValidationIssue[];
}
