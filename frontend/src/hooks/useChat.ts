/**
 * useChat — manages conversation state, session ID, and API calls.
 */
import { useCallback, useRef, useState } from "react";
import { sendMessage, submitFeedback, type ChatMessage, type ChatResponse } from "../lib/api";

export interface Turn {
  id: string;
  role: "user" | "assistant";
  content: string;
  meta?: Partial<ChatResponse>;
  loading?: boolean;
  /** Set when the request failed, so the UI can offer a per-message retry. */
  failed?: boolean;
}

export function useChat(customerId?: string) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sessionId = useRef<string>(crypto.randomUUID());
  // Mirrors `turns` so callbacks can read the latest history without being
  // re-created on every message (and without stale-closure bugs on retry).
  const turnsRef = useRef<Turn[]>([]);

  const commit = useCallback((next: (prev: Turn[]) => Turn[]) => {
    setTurns((prev) => {
      const value = next(prev);
      turnsRef.current = value;
      return value;
    });
  }, []);

  const runRequest = useCallback(async (
    message: string,
    assistantTurnId: string,
    history: ChatMessage[],
  ) => {
    setLoading(true);
    setError(null);
    try {
      const resp = await sendMessage({
        message,
        session_id: sessionId.current,
        customer_id: customerId,
        conversation_history: history,
      });

      commit((prev) =>
        prev.map((t) =>
          t.id === assistantTurnId
            ? { ...t, content: resp.response, loading: false, failed: false, meta: resp }
            : t
        )
      );
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Something went wrong";
      setError(msg);
      commit((prev) =>
        prev.map((t) =>
          t.id === assistantTurnId
            ? {
                ...t,
                content: "Sorry, I encountered an error. Please try again.",
                loading: false,
                failed: true,
              }
            : t
        )
      );
    } finally {
      setLoading(false);
    }
  }, [customerId, commit]);

  const send = useCallback(async (message: string) => {
    const text = message.trim();
    if (!text || loading) return;

    // History is the conversation *before* this turn.
    const history: ChatMessage[] = turnsRef.current
      .filter((t) => !t.failed && !t.loading)
      .map((t) => ({ role: t.role, content: t.content }));

    const userTurn: Turn = { id: crypto.randomUUID(), role: "user", content: text };
    const assistantTurn: Turn = {
      id: crypto.randomUUID(),
      role: "assistant",
      content: "",
      loading: true,
    };

    commit((prev) => [...prev, userTurn, assistantTurn]);
    await runRequest(text, assistantTurn.id, history);
  }, [loading, commit, runRequest]);

  /** Re-send the user message that produced a failed assistant turn. */
  const retry = useCallback(async (assistantTurnId: string) => {
    if (loading) return;
    const all = turnsRef.current;
    const idx = all.findIndex((t) => t.id === assistantTurnId);
    if (idx < 1) return;
    const userTurn = all[idx - 1];
    if (userTurn.role !== "user") return;

    const history: ChatMessage[] = all
      .slice(0, idx - 1)
      .filter((t) => !t.failed && !t.loading)
      .map((t) => ({ role: t.role, content: t.content }));

    commit((prev) =>
      prev.map((t) =>
        t.id === assistantTurnId
          ? { ...t, content: "", loading: true, failed: false, meta: undefined }
          : t
      )
    );
    await runRequest(userTurn.content, assistantTurnId, history);
  }, [loading, commit, runRequest]);

  const sendFeedback = useCallback(async (
    turnId: string,
    rating: 1 | 2 | 3 | 4 | 5,
    helpful: boolean
  ) => {
    await submitFeedback({ session_id: sessionId.current, turn_id: turnId, rating, helpful });
  }, []);

  const reset = useCallback(() => {
    turnsRef.current = [];
    setTurns([]);
    setError(null);
    sessionId.current = crypto.randomUUID();
  }, []);

  return { turns, loading, error, send, retry, sendFeedback, reset, sessionId: sessionId.current };
}
