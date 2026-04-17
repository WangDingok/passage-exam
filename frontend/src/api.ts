import {
  ValidationIssue,
  ValidationResponse,
  DraftDetail,
  DraftSummary,
  PassageExamDocument
} from "./types";

export class ApiError extends Error {
  status: number;
  issues: ValidationIssue[];
  detail: unknown;

  constructor(message: string, options: { status: number; issues?: ValidationIssue[]; detail?: unknown }) {
    super(message);
    this.name = "ApiError";
    this.status = options.status;
    this.issues = options.issues ?? [];
    this.detail = options.detail;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function toValidationIssue(value: unknown): ValidationIssue | null {
  if (!isRecord(value) || typeof value.path !== "string" || typeof value.message !== "string") {
    return null;
  }

  return {
    path: value.path,
    message: value.message,
    issue_type: typeof value.issue_type === "string" ? value.issue_type : "validation_error"
  };
}

function extractValidationIssues(value: unknown): ValidationIssue[] {
  if (!isRecord(value) || !Array.isArray(value.issues)) {
    return [];
  }

  return value.issues
    .map(issue => toValidationIssue(issue))
    .filter((issue): issue is ValidationIssue => issue !== null);
}

function formatValidationMessage(issues: ValidationIssue[]): string {
  if (issues.length === 0) {
    return "Validation failed.";
  }

  const [firstIssue] = issues;
  const firstLine = `${firstIssue.path}: ${firstIssue.message}`;

  if (issues.length === 1) {
    return `Validation failed: ${firstLine}`;
  }

  return `Validation failed: ${firstLine} (+${issues.length - 1} more)`;
}

function parseErrorDetail(payloadText: string): unknown {
  if (!payloadText) {
    return null;
  }

  try {
    const parsed = JSON.parse(payloadText) as unknown;
    if (isRecord(parsed) && "detail" in parsed) {
      return parsed.detail;
    }
    return parsed;
  } catch {
    return payloadText;
  }
}

export function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

export function getValidationIssuesFromError(error: unknown): ValidationIssue[] {
  return error instanceof ApiError ? error.issues : [];
}

async function request<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  const response = await fetch(input, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    }
  });
  if (!response.ok) {
    const payloadText = await response.text();
    const detail = parseErrorDetail(payloadText);
    const issues = extractValidationIssues(detail);
    const message =
      issues.length > 0
        ? formatValidationMessage(issues)
        : typeof detail === "string" && detail.trim()
          ? detail
          : payloadText || `Request failed with status ${response.status}`;
    throw new ApiError(message, {
      status: response.status,
      issues,
      detail
    });
  }
  return response.json() as Promise<T>;
}

export async function listDrafts(search?: string, status?: string): Promise<DraftSummary[]> {
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  if (status) params.set("status", status);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return request<DraftSummary[]>(`/drafts${suffix}`);
}

export async function getDraft(draftId: string): Promise<DraftDetail> {
  return request<DraftDetail>(`/drafts/${draftId}`);
}

export async function uploadDraft(file: File): Promise<DraftDetail> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch("/drafts/upload", {
    method: "POST",
    body: formData
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<DraftDetail>;
}

export async function generateDraft(draftId: string, questionsPerGroup?: number): Promise<DraftDetail> {
  return request<DraftDetail>(`/drafts/${draftId}/generate`, {
    method: "POST",
    body: JSON.stringify({ questions_per_group: questionsPerGroup || null })
  });
}

export async function saveDraft(
  draftId: string,
  payload: { title: string; description: string; normalized_document_json?: PassageExamDocument | null }
): Promise<DraftDetail> {
  return request<DraftDetail>(`/drafts/${draftId}`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export async function validateDraft(draftId: string): Promise<ValidationResponse> {
  return request<ValidationResponse>(`/drafts/${draftId}/validate`, {
    method: "POST"
  });
}

export async function publishDraft(draftId: string): Promise<DraftDetail> {
  return request<DraftDetail>(`/drafts/${draftId}/publish`, {
    method: "POST"
  });
}
