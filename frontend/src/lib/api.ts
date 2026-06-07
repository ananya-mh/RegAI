import type {
  Framework,
  FrameworkStatus,
  GapList,
  Policy,
  PolicyUploadResult,
  RemediationTask,
  UsageSummary,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`API error ${res.status.toString()}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export async function apiGet<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  return handleResponse<T>(res);
}

export async function apiPost<T>(
  path: string,
  body?: unknown,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    ...init,
  });
  return handleResponse<T>(res);
}

// ── Frameworks ──────────────────────────────────────────────────────────────

export function getFrameworks() {
  return apiGet<Framework[]>("/api/frameworks");
}

export function getFrameworkStatus(id: string) {
  return apiGet<FrameworkStatus>(`/api/frameworks/${id}/status`);
}

// ── Gaps ────────────────────────────────────────────────────────────────────

export function getGaps(params?: {
  framework_id?: string;
  status?: string;
  min_confidence?: number;
  limit?: number;
  offset?: number;
}) {
  const search = new URLSearchParams();
  if (params?.framework_id) search.set("framework_id", params.framework_id);
  if (params?.status) search.set("status", params.status);
  if (params?.min_confidence != null)
    search.set("min_confidence", params.min_confidence.toString());
  if (params?.limit != null) search.set("limit", params.limit.toString());
  if (params?.offset != null) search.set("offset", params.offset.toString());
  const qs = search.toString();
  return apiGet<GapList>(`/api/gaps${qs ? `?${qs}` : ""}`);
}

// ── Remediation ─────────────────────────────────────────────────────────────

export function getRemediationTasks(status?: string) {
  const qs = status ? `?status=${status}` : "";
  return apiGet<RemediationTask[]>(`/api/gaps/remediation${qs}`);
}

export function createRemediation(
  gapId: string,
  data: {
    title: string;
    description?: string;
    priority?: string;
    effort_estimate?: string;
    assignee?: string;
  },
) {
  return apiPost<RemediationTask>(`/api/gaps/${gapId}/remediation`, data);
}

// ── Policies ────────────────────────────────────────────────────────────────

export function getPolicies() {
  return apiGet<Policy[]>("/api/policies");
}

export async function uploadPolicy(file: File): Promise<PolicyUploadResult> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/policies/upload`, {
    method: "POST",
    body: form,
  });
  return handleResponse<PolicyUploadResult>(res);
}

// ── Usage ───────────────────────────────────────────────────────────────────

export function getUsageSummary() {
  return apiGet<UsageSummary>("/api/usage");
}

// ── Chat (SSE) ──────────────────────────────────────────────────────────────

export function streamChat(
  message: string,
  onEvent: (event: string, data: string) => void,
  onDone: () => void,
  onError: (err: Error) => void,
): AbortController {
  const controller = new AbortController();

  fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
    signal: controller.signal,
  })
    .then(async (res) => {
      if (!res.ok) {
        const text = await res.text().catch(() => res.statusText);
        throw new Error(`Chat API error ${res.status.toString()}: ${text}`);
      }
      const reader = res.body?.getReader();
      if (!reader) throw new Error("No response body");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        let currentEvent = "message";
        for (const line of lines) {
          if (line.startsWith("event: ")) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            const data = line.slice(6);
            if (currentEvent === "done") {
              onDone();
            } else {
              onEvent(currentEvent, data);
            }
          }
        }
      }
      onDone();
    })
    .catch((err: unknown) => {
      if (err instanceof Error && err.name !== "AbortError") {
        onError(err);
      }
    });

  return controller;
}
