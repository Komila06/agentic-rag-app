import { Source } from "@/lib/types";

export default function SourceList({ sources }: { sources: Source[] }) {
  if (!sources || sources.length === 0) return null;

  return (
    <div className="sources" aria-label="Sources used">
      <div className="sources-label">Sources</div>
      {sources.map((s, i) => (
        <div key={i} className={`source-item ${s.type === "web" ? "web" : ""}`}>
          <span className="tag">[{s.type}]</span>
          <span>
            {s.source}
            {s.page ? `, p.${s.page}` : ""}
          </span>
        </div>
      ))}
    </div>
  );
}
