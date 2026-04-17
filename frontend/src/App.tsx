import { ChangeEvent, useEffect, useRef, useState } from "react";

import {
  getErrorMessage,
  getValidationIssuesFromError,
  generateDraft,
  getDraft,
  listDrafts,
  publishDraft,
  saveDraft,
  uploadDraft,
  validateDraft
} from "./api";
import {
  DraftEvent,
  DraftDetail,
  DraftStatus,
  DraftSummary,
  PassageExamDocument,
  ValidationIssue
} from "./types";

const statusOptions: Array<{ label: string; value: DraftStatus | "" }> = [
  { label: "All", value: "" },
  { label: "Uploaded", value: "uploaded" },
  { label: "Generated", value: "generated" },
  { label: "Reviewing", value: "reviewing" },
  { label: "Publish Failed", value: "publish_failed" },
  { label: "Published", value: "published" }
];

type BusyMode = "loading" | "uploading" | "generating" | "saving" | "validating" | "publishing";

interface GenerationProgressState {
  stage: string;
  percent: number;
  title: string;
  message: string;
  groupsCount?: number;
  questionsCount?: number;
}

const generationStageMeta: Record<string, { percent: number; title: string }> = {
  generation_started: { percent: 6, title: "Queued generation" },
  starting: { percent: 12, title: "Preparing prompt" },
  requesting_groups: { percent: 34, title: "Generating passage groups" },
  groups_generated: { percent: 58, title: "Groups drafted" },
  requesting_answers: { percent: 76, title: "Generating answer key" },
  answers_generated: { percent: 91, title: "Building normalized exam" },
  completed: { percent: 100, title: "Generation completed" }
};

function toOptionalNumber(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function getGenerationProgressState(draft: DraftDetail): GenerationProgressState | null {
  for (const event of draft.events) {
    if (event.event_type !== "generation_progress" && event.event_type !== "generation_started") {
      continue;
    }

    const rawStage = event.payload_json.stage;
    const stage =
      typeof rawStage === "string" && rawStage in generationStageMeta ? rawStage : "generation_started";
    const stageMeta = generationStageMeta[stage] ?? generationStageMeta.generation_started;
    const rawMessage = event.payload_json.message;

    return {
      stage,
      percent: stageMeta.percent,
      title: stageMeta.title,
      message: typeof rawMessage === "string" ? rawMessage : "Generating quiz...",
      groupsCount: toOptionalNumber(event.payload_json.groups_count),
      questionsCount: toOptionalNumber(event.payload_json.questions_count)
    };
  }

  return null;
}

function isGenerationEvent(event: DraftEvent): boolean {
  return event.event_type === "generation_progress" || event.event_type === "generation_started";
}

function App() {
  const [drafts, setDrafts] = useState<DraftSummary[]>([]);
  const [selectedDraft, setSelectedDraft] = useState<DraftDetail | null>(null);
  const [editingDocument, setEditingDocument] = useState<PassageExamDocument | null>(null);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<DraftStatus | "">("");
  const [questionsPerGroup, setQuestionsPerGroup] = useState("4");
  const [file, setFile] = useState<File | null>(null);
  const [issues, setIssues] = useState<ValidationIssue[]>([]);
  const [busyLabel, setBusyLabel] = useState<string | null>(null);
  const [busyMode, setBusyMode] = useState<BusyMode | null>(null);
  const [generationProgress, setGenerationProgress] = useState<GenerationProgressState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"source" | "validation">("source");
  const [statusDropdownOpen, setStatusDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const generationRunRef = useRef(0);

  useEffect(() => {
    void refreshDrafts();
  }, []);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setStatusDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  useEffect(() => {
    const handler = setTimeout(() => {
      void refreshDrafts();
    }, 500);

    return () => {
      clearTimeout(handler);
    };
  }, [search, status]);

  function handleRequestError(requestError: unknown) {
    const validationIssues = getValidationIssuesFromError(requestError);
    if (validationIssues.length > 0) {
      setIssues(validationIssues);
      setActiveTab("validation");
    }
    setError(getErrorMessage(requestError));
  }

  async function refreshDrafts() {
    try {
      setError(null);
      const items = await listDrafts(search || undefined, status || undefined);
      setDrafts(items);
    } catch (requestError) {
      handleRequestError(requestError);
    }
  }

  async function loadDraft(draftId: string) {
    try {
      setBusyMode("loading");
      setGenerationProgress(null);
      setBusyLabel("Loading draft...");
      setError(null);
      const detail = await getDraft(draftId);
      setSelectedDraft(detail);
      setEditingDocument(detail.normalized_document_json ?? null);
      setIssues([]);
    } catch (requestError) {
      handleRequestError(requestError);
    } finally {
      setBusyMode(null);
      setBusyLabel(null);
    }
  }

  async function handleUpload() {
    if (!file) return;
    try {
      setError(null);
      setBusyMode("uploading");
      setGenerationProgress(null);
      setBusyLabel("Uploading source...");
      const draft = await uploadDraft(file);
      await refreshDrafts();
      await loadDraft(draft.id);
      setFile(null);
    } catch (requestError) {
      handleRequestError(requestError);
    } finally {
      setBusyMode(null);
      setBusyLabel(null);
    }
  }

  async function handleGenerate() {
    if (!selectedDraft) return;
    const draftId = selectedDraft.id;
    let pollTimer: number | undefined;
    const generationRunId = generationRunRef.current + 1;
    generationRunRef.current = generationRunId;

    let isPolling = true;
    let forceResolve: ((draft: DraftDetail) => void) | null = null;
    const pollPromise = new Promise<DraftDetail>((resolve) => {
      forceResolve = resolve;
    });

    const syncGenerationProgress = async () => {
      const detail = await getDraft(draftId);
      if (generationRunRef.current !== generationRunId) {
        return detail;
      }

      const progress = getGenerationProgressState(detail);
      if (progress) {
        setGenerationProgress(prev => {
          if (!prev || prev.stage !== progress.stage || prev.message !== progress.message || prev.percent !== progress.percent) {
            return progress;
          }
          return prev;
        });
        setBusyLabel(prev => prev !== progress.message ? progress.message : prev);
      }

      // If backend finished and updated the status, we can resolve early!
      if (detail.status === "generated" || detail.status === "published") {
        if (forceResolve) forceResolve(detail);
      }

      return detail;
    };

    try {
      setError(null);
      setBusyMode("generating");
      setGenerationProgress({
        stage: "generation_started",
        percent: generationStageMeta.generation_started.percent,
        title: generationStageMeta.generation_started.title,
        message: "Generation request started."
      });
      setBusyLabel("Generation request started.");
      
      const pollProgress = async () => {
        if (!isPolling) return;
        try {
          await syncGenerationProgress();
        } catch (err) {}
        if (isPolling) {
          pollTimer = window.setTimeout(pollProgress, 1500);
        }
      };
      pollTimer = window.setTimeout(pollProgress, 1500);

      const generationPromise = generateDraft(draftId, Number(questionsPerGroup));
      void syncGenerationProgress().catch(() => {});
      
      // Race the API call against the polling detection.
      // If ngrok hangs but polling finishes first, we win and unblock!
      // If the API throws an error (like 500 or 400), race will throw, and we show the error.
      const finalDraft = await Promise.race([generationPromise, pollPromise]);

      const completedProgress = getGenerationProgressState(finalDraft);
      if (completedProgress) {
        setGenerationProgress(completedProgress);
      }
      setSelectedDraft(finalDraft);
      setEditingDocument(finalDraft.normalized_document_json ?? null);
      await refreshDrafts();
    } catch (requestError) {
      handleRequestError(requestError);
    } finally {
      if (generationRunRef.current === generationRunId) {
        generationRunRef.current = 0;
      }
      isPolling = false;
      if (pollTimer !== undefined) {
        window.clearTimeout(pollTimer);
      }
      setBusyMode(null);
      setGenerationProgress(null);
      setBusyLabel(null);
    }
  }

  async function handleSave() {
    if (!selectedDraft) return;
    try {
      setError(null);
      setBusyMode("saving");
      setGenerationProgress(null);
      setBusyLabel("Saving draft...");
      const draft = await saveDraft(selectedDraft.id, {
        title: editingDocument?.title ?? selectedDraft.title,
        description: editingDocument?.description ?? selectedDraft.description,
        normalized_document_json: editingDocument
      });
      setSelectedDraft(draft);
      setEditingDocument(draft.normalized_document_json ?? null);
      await refreshDrafts();
    } catch (requestError) {
      handleRequestError(requestError);
    } finally {
      setBusyMode(null);
      setBusyLabel(null);
    }
  }

  async function handleValidate() {
    if (!selectedDraft) return;
    try {
      setError(null);
      setBusyMode("validating");
      setGenerationProgress(null);
      setBusyLabel("Saving & Validating draft...");
      
      // Tự động lưu trước khi validate để đảm bảo BE kiểm tra dữ liệu mới nhất
      const draft = await saveDraft(selectedDraft.id, {
        title: editingDocument?.title ?? selectedDraft.title,
        description: editingDocument?.description ?? selectedDraft.description,
        normalized_document_json: editingDocument
      });
      setSelectedDraft(draft);
      setEditingDocument(draft.normalized_document_json ?? null);

      const result = await validateDraft(draft.id);
      setIssues(result.issues);
    } catch (requestError) {
      handleRequestError(requestError);
    } finally {
      setBusyMode(null);
      setBusyLabel(null);
    }
  }

  async function handlePublish() {
    if (!selectedDraft) return;
    try {
      setError(null);
      setBusyMode("publishing");
      setGenerationProgress(null);
      setBusyLabel("Saving & Publishing exam...");
      
      // Tự động lưu bản mới nhất từ giao diện xuống database trước
      await saveDraft(selectedDraft.id, {
        title: editingDocument?.title ?? selectedDraft.title,
        description: editingDocument?.description ?? selectedDraft.description,
        normalized_document_json: editingDocument
      });

      const draft = await publishDraft(selectedDraft.id);
      setSelectedDraft(draft);
      setEditingDocument(draft.normalized_document_json ?? null);
      await refreshDrafts();
    } catch (requestError) {
      handleRequestError(requestError);
    } finally {
      setBusyMode(null);
      setBusyLabel(null);
    }
  }

  function updateDocument(next: PassageExamDocument) {
    setEditingDocument(next);
  }

  function updateGroupPassage(groupIndex: number, value: string) {
    if (!editingDocument) return;
    const groups = editingDocument.groups.map((group, index) =>
      index === groupIndex ? { ...group, passage: value } : group
    );
    updateDocument({ ...editingDocument, groups });
  }

  function updateQuestion(groupIndex: number, questionIndex: number, value: string) {
    if (!editingDocument) return;
    const groups = editingDocument.groups.map((group, index) => {
      if (index !== groupIndex) return group;
      return {
        ...group,
        questions: group.questions.map((question, idx) =>
          idx === questionIndex ? { ...question, question: value } : question
        )
      };
    });
    updateDocument({ ...editingDocument, groups });
  }

  function updateChoice(groupIndex: number, questionIndex: number, choiceIndex: number, value: string) {
    if (!editingDocument) return;
    const groups = editingDocument.groups.map((group, index) => {
      if (index !== groupIndex) return group;
      return {
        ...group,
        questions: group.questions.map((question, idx) => {
          if (idx !== questionIndex) return question;
          return {
            ...question,
            choices: question.choices.map((choice, choiceIdx) =>
              choiceIdx === choiceIndex ? { ...choice, content: value } : choice
            )
          };
        })
      };
    });
    updateDocument({ ...editingDocument, groups });
  }

  function updateCorrectAnswer(groupIndex: number, questionIndex: number, choiceIndex: number) {
    if (!editingDocument) return;
    const groups = editingDocument.groups.map((group, index) => {
      if (index !== groupIndex) return group;
      return {
        ...group,
        questions: group.questions.map((question, idx) => {
          if (idx !== questionIndex) return question;
          return {
            ...question,
            choices: question.choices.map((choice, choiceIdx) => ({
              ...choice,
              is_correct: choiceIdx === choiceIndex
            }))
          };
        })
      };
    });
    updateDocument({ ...editingDocument, groups });
  }

  const isBusy = Boolean(busyLabel);
  const busyTitle =
    busyMode === "generating"
      ? generationProgress?.title ?? "Generating quiz"
      : busyMode === "loading"
        ? "Loading draft"
        : busyMode === "uploading"
          ? "Uploading source"
          : busyMode === "saving"
            ? "Saving review"
            : busyMode === "validating"
              ? "Validating draft"
              : busyMode === "publishing"
                ? "Publishing exam"
                : "Working";
  const busyMessage = busyLabel ?? "Please wait...";

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="logo-area">
            <h1>Passage Exam</h1>
            <p>Workflow Manager</p>
          </div>
          <div className="upload-box">
            <label className="upload-label" htmlFor="file-upload" title={file ? file.name : "Select Document (.txt, .doc, .docx)"}>
              {file ? file.name : "Select Document (.txt, .doc, .docx)"}
            </label>
            <input
              id="file-upload"
              type="file"
              className="hidden"
              accept=".txt,.doc,.docx"
              onChange={(event: ChangeEvent<HTMLInputElement>) => setFile(event.target.files?.[0] ?? null)}
            />
            <button className="btn-primary" onClick={handleUpload} disabled={!file || isBusy}>
              Upload Source
            </button>
          </div>
        </div>

        <div className="sidebar-filters">
          <div className="filter-row">
            <input
              placeholder="Search title or filename..."
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <button className="btn-icon" onClick={() => void refreshDrafts()} disabled={isBusy} title="Refresh">
              ↻
            </button>
          </div>
          <div className="custom-select-container" ref={dropdownRef}>
            <button
              className="custom-select-button"
              onClick={() => setStatusDropdownOpen((prev) => !prev)}
              aria-expanded={statusDropdownOpen}
            >
              <span>{statusOptions.find((o) => o.value === status)?.label || "All"}</span>
              <span className="custom-select-arrow"></span>
            </button>
            {statusDropdownOpen && (
              <div className="custom-select-dropdown">
                {statusOptions.map((option) => (
                  <button
                    key={option.label}
                    className={`custom-select-option ${status === option.value ? "selected" : ""}`}
                    onClick={() => {
                      setStatus(option.value as DraftStatus | "");
                      setStatusDropdownOpen(false);
                    }}
                  >
                    <span className="custom-select-checkmark">{status === option.value ? "✓" : ""}</span>
                    {option.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="draft-list">
          {drafts.map((draft) => (
            <button
              key={draft.id}
              className={`draft-card ${selectedDraft?.id === draft.id ? "active" : ""}`}
              onClick={() => void loadDraft(draft.id)}
            >
              <div className="meta">
                <span className={`badge status-${draft.status}`}>{draft.status.replace("_", " ")}</span>
                <span className="muted">{new Date(draft.updated_at).toLocaleDateString()}</span>
              </div>
              <strong>{draft.title || "Untitled Draft"}</strong>
              <span className="filename">{draft.source_filename}</span>
            </button>
          ))}
          {drafts.length === 0 && !busyLabel && (
            <div className="empty-state" style={{ padding: "1rem" }}>
              <span style={{ fontSize: "0.875rem" }}>No drafts found.</span>
            </div>
          )}
        </div>
      </aside>

      <main className={`workspace ${isBusy ? "is-busy" : ""}`}>
        {selectedDraft ? (
          <>
            <header className="workspace-header">
              <div className="draft-info">
                <div className="draft-info-title">
                  <h2>{selectedDraft.title || "Untitled Draft"}</h2>
                  <span className={`badge status-${selectedDraft.status}`}>{selectedDraft.status.replace("_", " ")}</span>
                </div>
                <span className="file-name">{selectedDraft.source_filename}</span>
              </div>
              <div className="workspace-actions">
                <div className="generate-group">
                  <span style={{ fontSize: "0.875rem", paddingLeft: "0.5rem", color: "var(--text-muted)" }}>Q/Group</span>
                  <input
                    type="number"
                    min={1}
                    value={questionsPerGroup}
                    onChange={(event) => setQuestionsPerGroup(event.target.value)}
                  />
                  <button onClick={handleGenerate} disabled={isBusy}>
                    Generate
                  </button>
                </div>
                <button onClick={handleSave} disabled={!editingDocument || isBusy}>
                  Save Review
                </button>
                <button onClick={handleValidate} disabled={isBusy}>
                  Validate
                </button>
                <button className="btn-primary" onClick={handlePublish} disabled={!editingDocument || isBusy}>
                  Publish
                </button>
              </div>
            </header>

            {busyLabel && <div className="alert info">{busyLabel}</div>}
            {error && <div className="alert error">{error}</div>}

            <div className="workspace-content">
              <div className="split-view">
                <div className="pane source-pane">
                  <div className="pane-header">
                    <button
                      className={`pane-tab ${activeTab === "source" ? "active" : ""}`}
                      onClick={() => setActiveTab("source")}
                    >
                      Source & History
                    </button>
                    <button
                      className={`pane-tab ${activeTab === "validation" ? "active" : ""}`}
                      onClick={() => setActiveTab("validation")}
                    >
                      Validation & Result
                    </button>
                  </div>
                  <div className="pane-content">
                    {activeTab === "source" ? (
                      <>
                        <h3 className="pane-title" style={{ padding: "0 0 0.5rem", border: "none", background: "none" }}>Source Preview</h3>
                        <pre className="source-preview" style={{ marginBottom: "1.5rem" }}>{selectedDraft.source_text}</pre>
                        
                        <h3 className="pane-title" style={{ padding: "0 0 0.5rem", border: "none", background: "none" }}>Event History</h3>
                        <ul className="event-list">
                          {selectedDraft.events.map((event) => (
                            <li key={event.id}>
                              <strong>{event.event_type}</strong>
                              <span>{new Date(event.created_at).toLocaleString()}</span>
                              {isGenerationEvent(event) && typeof event.payload_json.message === "string" ? (
                                <p className="muted" style={{ margin: "0.25rem 0 0" }}>{event.payload_json.message}</p>
                              ) : null}
                              <code>{JSON.stringify(event.payload_json)}</code>
                            </li>
                          ))}
                        </ul>
                      </>
                    ) : (
                      <>
                        <h3 className="pane-title" style={{ padding: "0 0 0.5rem", border: "none", background: "none" }}>Validation Issues</h3>
                        {issues.length === 0 ? (
                          <p className="muted" style={{ fontSize: "0.875rem", marginBottom: "1.5rem" }}>No validation issues loaded or no issues found.</p>
                        ) : (
                          <ul className="issue-list" style={{ marginBottom: "1.5rem" }}>
                            {issues.map((issue) => (
                              <li key={`${issue.path}-${issue.message}`}>
                                <strong>{issue.path}</strong>
                                <span>{issue.message}</span>
                              </li>
                            ))}
                          </ul>
                        )}

                        <h3 className="pane-title" style={{ padding: "0 0 0.5rem", border: "none", background: "none" }}>Publish Result</h3>
                        {selectedDraft.publish_result ? (
                          <pre className="source-preview">{JSON.stringify(selectedDraft.publish_result, null, 2)}</pre>
                        ) : (
                          <p className="muted" style={{ fontSize: "0.875rem" }}>Draft has not been published yet.</p>
                        )}
                      </>
                    )}
                  </div>
                </div>

                <div className="pane editor-pane">
                  <h3 className="pane-title">Review Draft</h3>
                  <div className="pane-content">
                    {editingDocument ? (
                      <div className="editor-form">
                        <div className="form-group">
                          <label>Title</label>
                          <input
                            value={editingDocument.title}
                            onChange={(event) => updateDocument({ ...editingDocument, title: event.target.value })}
                          />
                        </div>
                        <div className="form-group">
                          <label>Description</label>
                          <textarea
                            rows={3}
                            value={editingDocument.description}
                            onChange={(event) => updateDocument({ ...editingDocument, description: event.target.value })}
                          />
                        </div>

                        {editingDocument.groups.map((group, groupIndex) => (
                          <div key={group.order} className="group-card">
                            <h4>Passage Group {group.order}</h4>
                            <div className="form-group">
                              <label>Passage HTML/Text</label>
                              <textarea
                                rows={5}
                                value={group.passage}
                                onChange={(event) => updateGroupPassage(groupIndex, event.target.value)}
                              />
                            </div>

                            {group.questions.map((question, questionIndex) => (
                              <div key={question.order} className="question-card">
                                <label>
                                  <span>Question {question.order}</span>
                                  <textarea
                                    rows={3}
                                    value={question.question}
                                    onChange={(event) => updateQuestion(groupIndex, questionIndex, event.target.value)}
                                  />
                                </label>
                                <div className="choice-grid">
                                  {question.choices.map((choice, choiceIndex) => (
                                    <label key={choiceIndex} className="choice-row">
                                      <input
                                        type="radio"
                                        name={`correct-${group.order}-${question.order}`}
                                        checked={choice.is_correct}
                                        onChange={() => updateCorrectAnswer(groupIndex, questionIndex, choiceIndex)}
                                      />
                                      <textarea
                                        rows={2}
                                        value={choice.content}
                                        onChange={(event) =>
                                          updateChoice(groupIndex, questionIndex, choiceIndex, event.target.value)
                                        }
                                      />
                                    </label>
                                  ))}
                                </div>
                              </div>
                            ))}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="empty-state">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                          <polyline points="14 2 14 8 20 8"></polyline>
                          <line x1="16" y1="13" x2="8" y2="13"></line>
                          <line x1="16" y1="17" x2="8" y2="17"></line>
                          <polyline points="10 9 9 9 8 9"></polyline>
                        </svg>
                        <h3>No Generated Exam</h3>
                        <p>Click "Generate" to create a normalized exam from the source text.</p>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </>
        ) : (
          <div className="empty-state" style={{ background: "var(--bg-surface)", margin: "1.5rem", borderRadius: "var(--radius-lg)" }}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 20h9"></path>
              <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path>
            </svg>
            <h3>Select a Draft</h3>
            <p>Upload a source file or select an existing draft from the sidebar to start reviewing.</p>
          </div>
        )}
        {isBusy && (
          <div className="busy-overlay" aria-live="polite" aria-busy="true">
            <div className="busy-card">
              <div className="busy-header terminal-style">
                <div className="busy-info">
                  <strong><span className="prompt-arrow">&gt;</span> {busyTitle}<span className="animated-dots"></span></strong>
                  <span className="terminal-message">{busyMessage}</span>
                </div>
              </div>
              {busyMode === "generating" && generationProgress ? (
                <>
                  <div className="busy-progress-track" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={generationProgress.percent}>
                    <div className="busy-progress-fill" style={{ width: `${generationProgress.percent}%` }} />
                  </div>
                  <div className="busy-progress-meta">
                    <span>{generationProgress.percent}%</span>
                    <span>
                      {generationProgress.groupsCount ?? 0} groups
                      {" • "}
                      {generationProgress.questionsCount ?? 0} questions
                    </span>
                  </div>
                </>
              ) : null}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
