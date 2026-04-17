import { describe, expect, it, vi } from "vitest";

import { saveDraft } from "../api";
import { PassageExamDocument } from "../types";

const documentPayload: PassageExamDocument = {
  title: "Draft title",
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
};

describe("api error formatting", () => {
  it("formats validation errors into a readable message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: {
              valid: false,
              issues: [
                {
                  path: "title",
                  message: "title must not be empty",
                  issue_type: "value_error"
                }
              ]
            }
          }),
          {
            status: 422,
            headers: {
              "Content-Type": "application/json"
            }
          }
        )
      )
    );

    await expect(
      saveDraft("draft-1", {
        title: documentPayload.title,
        description: documentPayload.description,
        normalized_document_json: documentPayload
      })
    ).rejects.toThrow("Validation failed: title: title must not be empty");
  });
});
