export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-background p-8">
      <div className="max-w-2xl w-full space-y-6 text-center">
        <h1 className="text-4xl font-bold tracking-tight">ComplianceForge</h1>
        <p className="text-muted-foreground text-lg">
          AI regulatory compliance automation engine.
          <br />
          Multi-agent gap analysis for GDPR, SOC 2, and HIPAA.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-4">
          {[
            { title: "Gap Analysis", desc: "Identify compliance gaps automatically" },
            { title: "RAG Pipeline", desc: "Semantic search across regulations & policies" },
            { title: "Audit Reports", desc: "Generate DOCX/PDF reports with citations" },
          ].map((card) => (
            <div
              key={card.title}
              className="rounded-lg border bg-card p-4 text-left shadow-sm"
            >
              <h2 className="font-semibold">{card.title}</h2>
              <p className="text-sm text-muted-foreground mt-1">{card.desc}</p>
            </div>
          ))}
        </div>
        <p className="text-xs text-muted-foreground pt-4">
          AI-generated assessments are for informational purposes only and do not constitute
          legal advice.
        </p>
      </div>
    </main>
  );
}
