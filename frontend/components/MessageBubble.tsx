"use client";

import { useState } from "react";
import { Message } from "@/lib/types";
import StepTrace from "./StepTrace";
import SourceList from "./SourceList";

export default function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";
  const [copied, setCopied] = useState(false);

  function handleCopy() {
    navigator.clipboard.writeText(message.content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  return (
    <div className={`msg-row ${isUser ? "user" : "assistant"}`}>
      <span className="msg-label">{isUser ? "you" : "agent"}</span>

      {!isUser && message.steps && <StepTrace steps={message.steps} />}

      <div className={`bubble ${message.pending ? "pending" : ""}`}>
        {message.pending ? "thinking …" : message.content}
      </div>

      {!isUser && !message.pending && (
        <button className="copy-btn" onClick={handleCopy} type="button">
          {copied ? "copied ✓" : "copy"}
        </button>
      )}

      {!isUser && !message.pending && message.sources && (
        <SourceList sources={message.sources} />
      )}
    </div>
  );
}