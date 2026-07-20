import { Message } from "@/lib/types";
import StepTrace from "./StepTrace";
import SourceList from "./SourceList";

export default function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";

  return (
    <div className={`msg-row ${isUser ? "user" : "assistant"}`}>
      <span className="msg-label">{isUser ? "you" : "agent"}</span>

      {!isUser && message.steps && <StepTrace steps={message.steps} />}

      <div className={`bubble ${message.pending ? "pending" : ""}`}>
        {message.pending ? "thinking …" : message.content}
      </div>

      {!isUser && !message.pending && message.sources && (
        <SourceList sources={message.sources} />
      )}
    </div>
  );
}
