"use client";

import { useEffect, useRef, useState } from "react";
import MessageBubble from "@/components/MessageBubble";
import { askQuestion, checkHealth } from "@/lib/api";
import { Message } from "@/lib/types";

function newId() {
  return Math.random().toString(36).slice(2);
}

const STORAGE_KEY = "agentic-rag-chat";

export default function Home() {
  const [messages, setMessages] = useState<Message[]>(() => {
    if (typeof window === "undefined") return [];
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [online, setOnline] = useState<boolean | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    checkHealth().then(setOnline);
    const interval = setInterval(() => {
      checkHealth().then(setOnline);
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
    } catch {
      // ignore storage errors (e.g. private browsing mode)
    }
  }, [messages]);

  function handleNewChat() {
    setMessages([]);
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // ignore
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const question = input.trim();
    if (!question) return;

    setError(null);
    setInput("");
    const userMsg: Message = { id: newId(), role: "user", content: question };
    const pendingId = newId();
    const pendingMsg: Message = { id: pendingId, role: "assistant", content: "", pending: true };
    setMessages((prev) => [...prev, userMsg, pendingMsg]);
    setBusy(true);

    try {
      const result = await askQuestion(question);
      setMessages((prev) =>
        prev.map((m) =>
          m.id === pendingId
            ? {
                ...m,
                content: result.answer,
                steps: result.steps,
                sources: result.sources,
                webUsed: result.web_used,
                pending: false,
              }
            : m
        )
      );
    } catch (err: any) {
      setMessages((prev) => prev.filter((m) => m.id !== pendingId));
      setError(err?.message || "Something went wrong reaching the agent.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-title">
          <span className="mark">Agentic RAG</span>
          <span className="sub">self-correcting document assistant</span>
        </div>
        <div className="header-actions">
          <button className="new-chat-btn" onClick={handleNewChat} type="button">
            New chat
          </button>
          <div className="status">
            <span
              className={`status-dot ${online === null ? "" : online ? "online" : "offline"}`}
            />
            {online === null ? "checking" : online ? "backend online" : "backend offline"}
          </div>
        </div>
      </header>

      <div className="messages" ref={scrollRef}>
        {messages.length === 0 && (
          <div className="empty-state">
            <span className="mark">no messages yet</span>
            Ask a question about your ingested documents. If the agent can&apos;t find a
            relevant answer there, it will fall back to a live web search — you&apos;ll see
            exactly which path it took above each answer.
          </div>
        )}
        {messages.map((m) => (
          <MessageBubble key={m.id} message={m} />
        ))}
      </div>

      {error && <div className="error-banner">{error}</div>}

      <form className="input-bar" onSubmit={handleSubmit}>
        <input
          type="text"
          placeholder="> ask something about your documents"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          aria-label="Ask a question"
        />
        <button type="submit" disabled={!input.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}