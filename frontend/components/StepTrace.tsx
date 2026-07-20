const LABELS: Record<string, string> = {
  retrieve: "retrieve",
  grade_documents: "grade docs",
  web_search: "web search",
  generate: "generate",
};

export default function StepTrace({ steps }: { steps: string[] }) {
  if (!steps || steps.length === 0) return null;

  return (
    <div className="step-trace" aria-label="Agent decision path">
      {steps.map((step, i) => (
        <span key={`${step}-${i}`} style={{ display: "flex", alignItems: "center" }}>
          <span className={`step-chip ${step}`}>
            <span className="dot" />
            {LABELS[step] ?? step}
          </span>
          {i < steps.length - 1 && <span className="step-connector">→</span>}
        </span>
      ))}
    </div>
  );
}
