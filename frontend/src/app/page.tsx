"use client";

import { useEffect, useState } from "react";
import { getFrameworks, getFrameworkStatus } from "@/lib/api";
import type { Framework, FrameworkStatus } from "@/lib/types";

export default function Dashboard() {
  const [frameworks, setFrameworks] = useState<Framework[]>([]);
  const [statuses, setStatuses] = useState<Record<string, FrameworkStatus>>({});
  const [selectedId, setSelectedId] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        setLoading(true);
        const fws = await getFrameworks();
        if (cancelled) return;
        setFrameworks(fws);
        if (fws.length > 0) setSelectedId(fws[0].id);

        const results = await Promise.all(
          fws.map((fw) =>
            getFrameworkStatus(fw.id).then((s) => [fw.id, s] as const)
          )
        );
        if (cancelled) return;
        const map: Record<string, FrameworkStatus> = {};
        for (const [id, s] of results) map[id] = s;
        setStatuses(map);
      } catch (err) {
        if (!cancelled)
          setError(err instanceof Error ? err.message : "Failed to load");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  const selected = selectedId ? statuses[selectedId] : null;

  if (loading) {
    return (
      <div className="p-8">
        <h1 className="text-2xl font-bold mb-8">Dashboard</h1>
        <div className="text-center py-20 text-muted-foreground">Loading frameworks...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8">
        <h1 className="text-2xl font-bold mb-8">Dashboard</h1>
        <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-red-800">{error}</div>
      </div>
    );
  }

  if (frameworks.length === 0) {
    return (
      <div className="p-8">
        <h1 className="text-2xl font-bold mb-8">Dashboard</h1>
        <div className="rounded-lg border bg-card p-12 text-center">
          <p className="text-muted-foreground">No regulatory frameworks ingested yet.</p>
          <p className="text-sm text-muted-foreground mt-1">Ingest GDPR, SOC 2, or HIPAA to get started.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold">Dashboard</h1>

      <div>
        <label htmlFor="fw-select" className="block text-sm font-medium text-muted-foreground mb-1">
          Framework
        </label>
        <select
          id="fw-select"
          value={selectedId}
          onChange={(e) => setSelectedId(e.target.value)}
          className="w-full max-w-xs rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        >
          {frameworks.map((fw) => (
            <option key={fw.id} value={fw.id}>
              {fw.name} (v{fw.version})
            </option>
          ))}
        </select>
      </div>

      {selected && (
        <div className="rounded-lg border bg-card p-6 space-y-6">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-semibold">{selected.framework.name}</h2>
            <span className="text-sm text-muted-foreground">v{selected.framework.version}</span>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium">Compliance Coverage</span>
              <span className="text-sm font-semibold">{selected.coverage_pct.toFixed(1)}%</span>
            </div>
            <div className="h-3 w-full rounded-full bg-muted overflow-hidden">
              <div
                className="h-full rounded-full bg-primary transition-all duration-500"
                style={{ width: `${Math.min(selected.coverage_pct, 100)}%` }}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {[
              { label: "Total Requirements", value: selected.total_requirements },
              { label: "Assessed", value: selected.assessed },
              { label: "Remaining", value: selected.total_requirements - selected.assessed },
              { label: "Coverage", value: `${selected.coverage_pct.toFixed(0)}%` },
            ].map((stat) => (
              <div key={stat.label} className="rounded-md border bg-background p-3 text-center">
                <div className="text-2xl font-bold">{stat.value}</div>
                <div className="text-xs text-muted-foreground mt-1">{stat.label}</div>
              </div>
            ))}
          </div>

          <div>
            <h3 className="text-sm font-medium text-muted-foreground mb-3">Gap Breakdown</h3>
            <div className="flex flex-wrap gap-3">
              <span className="inline-flex items-center gap-1.5 rounded-full bg-green-100 px-4 py-1.5 text-sm font-medium text-green-800">
                <span className="h-2 w-2 rounded-full bg-green-500" />
                Compliant: {selected.compliant}
              </span>
              <span className="inline-flex items-center gap-1.5 rounded-full bg-yellow-100 px-4 py-1.5 text-sm font-medium text-yellow-800">
                <span className="h-2 w-2 rounded-full bg-yellow-500" />
                Partial: {selected.partial}
              </span>
              <span className="inline-flex items-center gap-1.5 rounded-full bg-red-100 px-4 py-1.5 text-sm font-medium text-red-800">
                <span className="h-2 w-2 rounded-full bg-red-500" />
                Non-Compliant: {selected.non_compliant}
              </span>
            </div>
          </div>
        </div>
      )}

      <div>
        <h2 className="text-lg font-semibold mb-4">All Frameworks</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {frameworks.map((fw) => {
            const s = statuses[fw.id];
            return (
              <button
                key={fw.id}
                type="button"
                onClick={() => setSelectedId(fw.id)}
                className={`rounded-lg border p-5 text-left shadow-sm transition-colors hover:bg-accent/50 ${
                  selectedId === fw.id ? "border-primary ring-1 ring-primary" : "bg-card"
                }`}
              >
                <h3 className="font-semibold">{fw.name}</h3>
                <p className="text-xs text-muted-foreground mt-0.5">v{fw.version}</p>
                {s ? (
                  <div className="mt-4 space-y-2">
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-muted-foreground">Coverage</span>
                      <span className="font-semibold">{s.coverage_pct.toFixed(1)}%</span>
                    </div>
                    <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
                      <div
                        className="h-full rounded-full bg-primary transition-all duration-500"
                        style={{ width: `${Math.min(s.coverage_pct, 100)}%` }}
                      />
                    </div>
                    <div className="flex gap-2 mt-2">
                      <span className="text-xs rounded bg-green-100 px-1.5 py-0.5 text-green-700">{s.compliant}</span>
                      <span className="text-xs rounded bg-yellow-100 px-1.5 py-0.5 text-yellow-700">{s.partial}</span>
                      <span className="text-xs rounded bg-red-100 px-1.5 py-0.5 text-red-700">{s.non_compliant}</span>
                    </div>
                  </div>
                ) : (
                  <p className="text-xs text-muted-foreground mt-3">Loading...</p>
                )}
              </button>
            );
          })}
        </div>
      </div>

      <p className="text-xs text-muted-foreground text-center pt-4">
        AI-generated assessments are for informational purposes only and do not constitute legal advice.
      </p>
    </div>
  );
}
