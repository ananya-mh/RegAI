"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { streamChat } from "@/lib/api";
import { cn } from "@/lib/utils";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  status?: string;
  interpretations?: { regulation_id: string; summary: string; operational_meaning: string }[];
  gaps?: { requirement_id: string; status: string; explanation: string; confidence_score: number }[];
  error?: string;
  streaming?: boolean;
}

let counter = 0;
function nextId() {
  counter += 1;
  return `msg-${Date.now()}-${counter}`;
}

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const send = useCallback(() => {
    const text = input.trim();
    if (!text || streaming) return;

    const userId = nextId();
    const assistantId = nextId();
    setMessages((prev) => [
      ...prev,
      { id: userId, role: "user", text },
      { id: assistantId, role: "assistant", text: "", streaming: true },
    ]);
    setInput("");
    setStreaming(true);

    const controller = streamChat(
      text,
      (event, data) => {
        setMessages((prev) => {
          const msgs = [...prev];
          const idx = msgs.findIndex((m) => m.id === assistantId);
          if (idx === -1) return prev;
          const msg = { ...msgs[idx] };

          try {
            if (event === "status") {
              const parsed = JSON.parse(data);
              msg.status = parsed.stage ?? data;
            } else if (event === "interpretations") {
              msg.interpretations = JSON.parse(data);
            } else if (event === "gaps") {
              msg.gaps = JSON.parse(data);
            } else if (event === "text") {
              const parsed = JSON.parse(data);
              msg.text = (msg.text ?? "") + (parsed.content ?? "");
            } else if (event === "error") {
              const parsed = JSON.parse(data);
              msg.error = parsed.message ?? data;
              msg.streaming = false;
            }
          } catch {
            if (event === "text") msg.text = (msg.text ?? "") + data;
          }

          msgs[idx] = msg;
          return msgs;
        });
      },
      () => {
        setMessages((prev) => {
          const msgs = [...prev];
          const idx = msgs.findIndex((m) => m.id === assistantId);
          if (idx !== -1) msgs[idx] = { ...msgs[idx], streaming: false, status: undefined };
          return msgs;
        });
        setStreaming(false);
        abortRef.current = null;
      },
      (err) => {
        setMessages((prev) => {
          const msgs = [...prev];
          const idx = msgs.findIndex((m) => m.id === assistantId);
          if (idx !== -1) msgs[idx] = { ...msgs[idx], error: err.message, streaming: false };
          return msgs;
        });
        setStreaming(false);
        abortRef.current = null;
      }
    );
    abortRef.current = controller;
  }, [input, streaming]);

  return (
    <div className="flex h-full flex-col">
      <div className="shrink-0 border-b px-6 py-4">
        <h1 className="text-lg font-semibold">Compliance Chat</h1>
        <p className="text-sm text-muted-foreground">
          Ask about GDPR, SOC 2, or HIPAA compliance
        </p>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-4">
        {messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-center text-muted-foreground">
            <p className="font-medium">Start a conversation</p>
            <p className="text-sm mt-1 max-w-sm">
              Ask about specific regulations, request gap analyses, or check compliance status.
            </p>
          </div>
        ) : (
          <div className="mx-auto max-w-3xl space-y-4">
            {messages.map((msg) => (
              <div key={msg.id} className={cn("flex", msg.role === "user" ? "justify-end" : "justify-start")}>
                <div
                  className={cn(
                    "max-w-[80%] rounded-lg px-4 py-2.5 text-sm",
                    msg.role === "user"
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted text-foreground"
                  )}
                >
                  {msg.status && msg.streaming && !msg.text && (
                    <p className="text-muted-foreground italic">{msg.status}...</p>
                  )}
                  {msg.text && (
                    <div className="whitespace-pre-wrap leading-relaxed">
                      {msg.text}
                      {msg.streaming && (
                        <span className="inline-block w-1.5 h-4 ml-0.5 bg-current animate-pulse" />
                      )}
                    </div>
                  )}
                  {msg.interpretations && msg.interpretations.length > 0 && (
                    <div className="mt-2 space-y-1.5">
                      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                        Interpretations
                      </p>
                      {msg.interpretations.map((i, idx) => (
                        <div key={idx} className="rounded border bg-background p-2 text-xs">
                          <span className="font-medium">{i.regulation_id}</span>: {i.summary}
                        </div>
                      ))}
                    </div>
                  )}
                  {msg.gaps && msg.gaps.length > 0 && (
                    <div className="mt-2 space-y-1.5">
                      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                        Gap Assessments
                      </p>
                      {msg.gaps.map((g, idx) => (
                        <div key={idx} className="rounded border bg-background p-2 text-xs">
                          <div className="flex items-center justify-between">
                            <span className="font-medium">{g.requirement_id}</span>
                            <span
                              className={cn(
                                "rounded-full px-2 py-0.5 text-xs font-medium",
                                g.status === "compliant" && "bg-green-100 text-green-800",
                                g.status === "partial" && "bg-yellow-100 text-yellow-800",
                                g.status === "non-compliant" && "bg-red-100 text-red-800"
                              )}
                            >
                              {g.status}
                            </span>
                          </div>
                          <p className="mt-1">{g.explanation}</p>
                          <p className="text-muted-foreground mt-0.5">
                            Confidence: {(g.confidence_score * 100).toFixed(0)}%
                          </p>
                        </div>
                      ))}
                    </div>
                  )}
                  {msg.error && (
                    <p className="text-destructive text-sm mt-1">{msg.error}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="shrink-0 border-t bg-background px-6 py-4">
        <div className="mx-auto max-w-3xl flex gap-2 items-end">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            placeholder="Ask a compliance question..."
            disabled={streaming}
            rows={1}
            className="flex-1 resize-none rounded-lg border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50 min-h-[40px] max-h-[160px]"
          />
          <button
            onClick={streaming ? () => { abortRef.current?.abort(); setStreaming(false); } : send}
            disabled={!streaming && !input.trim()}
            className="shrink-0 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {streaming ? "Stop" : "Send"}
          </button>
        </div>
        <p className="mx-auto max-w-3xl text-xs text-muted-foreground mt-2">
          Enter to send, Shift+Enter for newline. AI assessments do not constitute legal advice.
        </p>
      </div>
    </div>
  );
}
