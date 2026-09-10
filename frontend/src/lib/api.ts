/**
 * API client — typed wrappers around the FastAPI backend.
 */
import axios from "axios";

const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";

const api = axios.create({ baseURL: BASE_URL, timeout: 60_000 });

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
}

export interface ChatRequest {
  message: string;
  session_id?: string;
  customer_id?: string;
  conversation_history?: ChatMessage[];
}

export interface ChatResponse {
  session_id: string;
  turn_id: string;
  response: string;
  response_type: "answer" | "clarification" | "action_confirmation" | "escalation";
  intent: string;
  confidence: number;
  citations: string[];
  follow_up_suggestions: string[];
  actions_taken: Array<{ action: string; success: boolean }>;
  should_escalate: boolean;
  escalation_reason?: string;
  metadata: Record<string, unknown>;
}

export interface FeedbackRequest {
  session_id: string;
  turn_id: string;
  rating: 1 | 2 | 3 | 4 | 5;
  helpful: boolean;
  comment?: string;
}

export async function sendMessage(req: ChatRequest): Promise<ChatResponse> {
  const { data } = await api.post<ChatResponse>("/chat", req);
  return data;
}

export async function submitFeedback(req: FeedbackRequest): Promise<void> {
  await api.post("/chat/feedback", req);
}

export async function getHealth() {
  const { data } = await api.get("/admin/health");
  return data;
}

/** SSE streaming — yields ChatResponse metadata on completion */
export function streamMessage(
  req: ChatRequest,
  onToken: (token: string) => void,
  onDone: (meta: Partial<ChatResponse>) => void,
  onError: (err: string) => void
): () => void {
  const url = `${BASE_URL}/chat/stream`;
  let aborted = false;

  (async () => {
    try {
      const resp = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req),
      });
      if (!resp.body) throw new Error("No response body");
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();

      while (!aborted) {
        const { done, value } = await reader.read();
        if (done) break;
        const lines = decoder.decode(value).split("\n");
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const chunk = JSON.parse(line.slice(6));
          if (chunk.type === "token") onToken(chunk.content);
          else if (chunk.type === "done") onDone(chunk.metadata);
          else if (chunk.type === "error") onError(chunk.content);
        }
      }
    } catch (e) {
      if (!aborted) onError(String(e));
    }
  })();

  return () => { aborted = true; };
}
