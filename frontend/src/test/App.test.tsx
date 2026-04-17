import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import { DraftDetail, DraftSummary } from "../types";

const {
  listDrafts,
  getDraft,
  saveDraft,
  validateDraft
} = vi.hoisted(() => ({
  listDrafts: vi.fn(),
  getDraft: vi.fn(),
  saveDraft: vi.fn(),
  validateDraft: vi.fn()
}));

vi.mock("../api", () => ({
  listDrafts,
  getDraft,
  saveDraft,
  validateDraft,
  getErrorMessage: (error: unknown) => (error instanceof Error ? error.message : String(error)),
  getValidationIssuesFromError: () => [],
  generateDraft: vi.fn(),
  publishDraft: vi.fn(),
  uploadDraft: vi.fn()
}));

function buildDraftSummary(): DraftSummary {
  return {
    id: "draft-1",
    title: "Draft title",
    description: "Draft description",
    status: "generated",
    source_filename: "draft.txt",
    source_extension: ".txt",
    created_by: "user-1",
    updated_by: "user-1",
    created_at: "2026-04-17T00:00:00Z",
    updated_at: "2026-04-17T00:00:00Z",
    published_at: null,
    error_message: null,
    publish_result: null
  };
}

function buildDraftDetail(title = "Draft title"): DraftDetail {
  return {
    ...buildDraftSummary(),
    title,
    source_text: "Source text",
    normalized_document_json: {
      title,
      description: "Draft description",
      groups: [
        {
          order: 1,
          passage: "<p>Passage</p>",
          questions: [
            {
              order: 1,
              type: "multiple_choice",
              question: "<p>Question</p>",
              choices: [
                { content: "<p>A</p>", is_correct: true },
                { content: "<p>B</p>", is_correct: false },
                { content: "<p>C</p>", is_correct: false },
                { content: "<p>D</p>", is_correct: false }
              ]
            }
          ]
        }
      ]
    },
    generation_params_json: null,
    events: []
  };
}

describe("App validation flow", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listDrafts.mockResolvedValue([buildDraftSummary()]);
    getDraft.mockResolvedValue(buildDraftDetail());
  });

  it("clears the previous error after a later validation passes", async () => {
    saveDraft
      .mockRejectedValueOnce(new Error("Validation failed: title: title must not be empty"))
      .mockResolvedValueOnce(buildDraftDetail("Recovered title"));
    validateDraft.mockResolvedValue({ valid: true, issues: [] });

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /draft title/i }));

    const titleInput = await screen.findByDisplayValue("Draft title");
    fireEvent.change(titleInput, { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Validate" }));

    expect(await screen.findByText("Validation failed: title: title must not be empty")).toBeInTheDocument();

    fireEvent.change(titleInput, { target: { value: "Recovered title" } });
    fireEvent.click(screen.getByRole("button", { name: "Validate" }));

    await waitFor(() => {
      expect(screen.queryByText("Validation failed: title: title must not be empty")).not.toBeInTheDocument();
    });
    expect(validateDraft).toHaveBeenCalledWith("draft-1");
  });
});
