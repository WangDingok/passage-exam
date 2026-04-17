import {
  DraftDetail,
  DraftSummary,
  PassageExamDocument,
  ValidationResponse
} from "./types";

async function request<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  const response = await fetch(input, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    }
  });
  if (!response.ok) {
    const payload = await response.text();
    throw new Error(payload || `Request failed with status ${response.status}`);
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
