/**
 * ChatWindow — the main conversation UI.
 * Shows message bubbles, intent badges, citations, clickable follow-up chips,
 * actions taken, escalation banners, per-message retry, and a feedback row.
 */
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  HelpCircle,
  RefreshCw,
  RotateCcw,
  Send,
  ThumbsDown,
  ThumbsUp,
  User,
  XCircle,
} from "lucide-react";
import clsx from "clsx";
import { useChat, type Turn } from "../hooks/useChat";

const INTENT_COLORS: Record<string, string> = {
  complaint_status: "bg-blue-100 text-blue-700",
  account_inquiry: "bg-purple-100 text-purple-700",
  payment_issue: "bg-orange-100 text-orange-700",
  policy_question: "bg-green-100 text-green-700",
  product_question: "bg-cyan-100 text-cyan-700",
  fraud_report: "bg-red-100 text-red-700",
  general: "bg-gray-100 text-gray-600",
};

/** Starter prompts shown on the empty state so the first turn is one click away. */
const STARTER_PROMPTS = [
  "What's the status of my complaint?",
  "I was charged twice for the same transaction",
  "Explain the overdraft fee policy",
  "There's a charge I don't recognize on my card",
];

function IntentBadge({ intent }: { intent: string }) {
  const label = intent.replace(/_/g, " ");
  const color = INTENT_COLORS[intent] ?? INTENT_COLORS.general;
  return (
    <span className={clsx("text-xs font-medium px-2 py-0.5 rounded-full", color)}>
      {label}
    </span>
  );
}

/** Visual treatment per response_type so the four kinds are distinguishable. */
function ResponseTypeTag({ type }: { type: string }) {
  if (type === "clarification") {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-indigo-600 bg-indigo-50 border border-indigo-200 rounded-full px-2 py-0.5">
        <HelpCircle size={11} /> Needs clarification
      </span>
    );
  }
  if (type === "action_confirmation") {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-full px-2 py-0.5">
        <CheckCircle2 size={11} /> Action confirmed
      </span>
    );
  }
  return null;
}

function TypingDots() {
  return (
    <span className="flex gap-1 items-center h-5" aria-label="Assistant is typing">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-2 h-2 rounded-full bg-gray-400 animate-bounce"
          style={{ animationDelay: `${i * 0.15}s` }}
        />
      ))}
    </span>
  );
}

function MessageBubble({ turn, onFeedback, onSuggestion, onRetry }: {
  turn: Turn;
  onFeedback: (rating: 1 | 5, helpful: boolean) => void;
  onSuggestion: (text: string) => void;
  onRetry: () => void;
}) {
  const isUser = turn.role === "user";
  const [feedbackGiven, setFeedbackGiven] = useState(false);
  const meta = turn.meta;

  const handleFeedback = (helpful: boolean) => {
    onFeedback(helpful ? 5 : 1, helpful);
    setFeedbackGiven(true);
  };

  return (
    <div className={clsx("flex gap-3 max-w-3xl", isUser ? "ml-auto flex-row-reverse" : "mr-auto")}>
      {/* Avatar */}
      <div className={clsx(
        "flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-white mt-1",
        isUser ? "bg-blue-500" : "bg-emerald-600"
      )}>
        {isUser ? <User size={16} /> : <Bot size={16} />}
      </div>

      <div className="flex flex-col gap-1 min-w-0">
        {/* Escalation banner */}
        {meta?.should_escalate && (
          <div className="flex items-center gap-2 text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 text-sm mb-1">
            <AlertTriangle size={14} />
            <span>
              {meta.escalation_reason
                ? `Connecting you with a human specialist — ${meta.escalation_reason}`
                : "Connecting you with a human specialist"}
            </span>
          </div>
        )}

        {/* Bubble */}
        <div className={clsx(
          "rounded-2xl px-4 py-3 text-sm leading-relaxed",
          isUser
            ? "bg-blue-600 text-white rounded-br-sm"
            : "bg-white border text-gray-800 rounded-bl-sm shadow-sm",
          !isUser && turn.failed
            ? "border-red-200 bg-red-50"
            : !isUser && meta?.response_type === "escalation"
              ? "border-amber-200"
              : !isUser && "border-gray-200"
        )}>
          {turn.loading ? <TypingDots /> : (
            <ReactMarkdown className="prose prose-sm max-w-none prose-p:my-1">
              {turn.content}
            </ReactMarkdown>
          )}
        </div>

        {/* Failed → offer a retry for this message only */}
        {!isUser && turn.failed && (
          <div className="px-1">
            <button
              onClick={onRetry}
              className="inline-flex items-center gap-1.5 text-xs text-red-600 hover:text-red-700 font-medium"
            >
              <RotateCcw size={12} /> Retry
            </button>
          </div>
        )}

        {/* Assistant metadata row */}
        {!isUser && !turn.loading && meta && !turn.failed && (
          <div className="flex flex-wrap gap-2 items-center px-1">
            <IntentBadge intent={meta.intent ?? "general"} />
            <ResponseTypeTag type={meta.response_type ?? "answer"} />
            <span className="text-xs text-gray-400">
              {Math.round((meta.confidence ?? 0) * 100)}% confidence
            </span>
            {(meta.citations ?? []).slice(0, 2).map((c) => (
              <span key={c} className="text-xs text-gray-400 italic">[{c}]</span>
            ))}
          </div>
        )}

        {/* Actions the agent actually performed */}
        {!isUser && !turn.loading && (meta?.actions_taken ?? []).length > 0 && (
          <div className="flex flex-wrap gap-1.5 px-1 mt-0.5">
            {(meta?.actions_taken ?? []).map((a, i) => (
              <span
                key={`${a.action}-${i}`}
                className={clsx(
                  "inline-flex items-center gap-1 text-xs rounded-md px-2 py-0.5 border",
                  a.success
                    ? "text-emerald-700 bg-emerald-50 border-emerald-200"
                    : "text-red-700 bg-red-50 border-red-200"
                )}
                title={a.success ? "Completed" : "Failed"}
              >
                {a.success ? <CheckCircle2 size={11} /> : <XCircle size={11} />}
                {a.action.replace(/_/g, " ")}
              </span>
            ))}
          </div>
        )}

        {/* Follow-up suggestions — clicking one sends it */}
        {!isUser && !turn.loading && (meta?.follow_up_suggestions ?? []).length > 0 && (
          <div className="flex flex-wrap gap-2 mt-1 px-1">
            {(meta?.follow_up_suggestions ?? []).map((s) => (
              <button
                key={s}
                onClick={() => onSuggestion(s)}
                className="text-xs bg-gray-100 hover:bg-emerald-50 hover:text-emerald-700 hover:border-emerald-200 border border-transparent text-gray-600 rounded-full px-3 py-1 transition-colors"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {/* Feedback */}
        {!isUser && !turn.loading && turn.meta && !turn.failed && (
          <div className="flex gap-2 px-1 mt-0.5">
            {feedbackGiven ? (
              <span className="text-xs text-gray-400">Thanks for your feedback!</span>
            ) : (
              <>
                <button
                  onClick={() => handleFeedback(true)}
                  className="text-gray-400 hover:text-emerald-500 transition-colors"
                  aria-label="Helpful"
                >
                  <ThumbsUp size={14} />
                </button>
                <button
                  onClick={() => handleFeedback(false)}
                  className="text-gray-400 hover:text-red-500 transition-colors"
                  aria-label="Not helpful"
                >
                  <ThumbsDown size={14} />
                </button>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default function ChatWindow() {
  const { turns, loading, error, send, retry, sendFeedback, reset } = useChat();
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  // Auto-grow the textarea up to ~5 rows.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`;
  }, [input]);

  const submit = (text: string) => {
    const value = text.trim();
    if (!value || loading) return;
    send(value);
    setInput("");
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    submit(input);
  };

  // Enter sends, Shift+Enter inserts a newline.
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit(input);
    }
  };

  const lastTurn = turns[turns.length - 1];

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-emerald-600 flex items-center justify-center">
            <Bot size={20} className="text-white" />
          </div>
          <div>
            <h1 className="font-semibold text-gray-900">Fin AI Agent</h1>
            <p className="text-xs text-emerald-600">● Online · Financial Support</p>
          </div>
        </div>
        <button
          onClick={reset}
          className="text-gray-400 hover:text-gray-600 transition-colors"
          aria-label="New conversation"
          title="New conversation"
        >
          <RefreshCw size={18} />
        </button>
      </header>

      {/* Messages */}
      <main className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
        {turns.length === 0 && (
          <div className="text-center mt-16">
            <Bot size={40} className="mx-auto mb-3 text-gray-300" />
            <p className="font-medium text-gray-500">How can I help you today?</p>
            <p className="text-xs mt-1 text-gray-400">
              Ask about complaints, payments, accounts, or policies.
            </p>
            <div className="flex flex-wrap gap-2 justify-center mt-6 max-w-lg mx-auto">
              {STARTER_PROMPTS.map((p) => (
                <button
                  key={p}
                  onClick={() => submit(p)}
                  className="text-xs text-left bg-white hover:bg-emerald-50 hover:border-emerald-300 hover:text-emerald-700 border border-gray-200 text-gray-600 rounded-xl px-3 py-2 shadow-sm transition-colors"
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
        )}
        {turns.map((turn) => (
          <MessageBubble
            key={turn.id}
            turn={turn}
            onFeedback={(rating, helpful) => sendFeedback(turn.id, rating, helpful)}
            onSuggestion={submit}
            onRetry={() => retry(turn.id)}
          />
        ))}
        {error && (
          <div className="text-center text-red-500 text-sm" role="alert">{error}</div>
        )}
        <div ref={bottomRef} />
      </main>

      {/* Screen-reader announcements for assistant replies */}
      <div className="sr-only" aria-live="polite" aria-atomic="true">
        {loading
          ? "Fin is typing"
          : lastTurn?.role === "assistant" && !lastTurn.loading
            ? lastTurn.content
            : ""}
      </div>

      {/* Input */}
      <footer className="bg-white border-t border-gray-200 px-4 py-3">
        <form onSubmit={handleSubmit} className="flex gap-3 max-w-3xl mx-auto items-end">
          <textarea
            ref={textareaRef}
            rows={1}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type your message…  (Enter to send, Shift+Enter for a new line)"
            disabled={loading}
            className="flex-1 resize-none rounded-xl border border-gray-300 px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 disabled:opacity-50"
            aria-label="Message input"
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl px-4 py-2.5 flex items-center gap-2 text-sm font-medium disabled:opacity-40 transition-colors"
            aria-label="Send message"
          >
            <Send size={16} />
            Send
          </button>
        </form>
        <p className="text-center text-xs text-gray-400 mt-2">
          Fin AI may make mistakes. For urgent issues, call 1-800-XXX-XXXX.
        </p>
      </footer>
    </div>
  );
}
