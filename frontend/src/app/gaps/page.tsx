"use client";

import { useEffect, useState } from "react";
import { getFrameworks, getGaps } from "@/lib/api";
import type { Framework, Gap } from "@/lib/types";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 20;

const statusBadge: Record<string, string> = {
  compliant: "bg-green-100 text-green-800",
  partial: "bg-yellow-100 text-yellow-800",
  "non-compliant": "bg-red-100 text-red-800",
};

export default function GapsPage() {
  const [frameworks, setFrameworks] = useState<Framework[]>([]);
  const [gaps, setGaps] = useState<Gap[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [frameworkId, setFrameworkId] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [minConfidence, setMinConfidence] = useState<number | undefined>();
  const [offset, setOffset] = useState(0);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    getFrameworks().then(setFrameworks).catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getGaps({
      framework_id: frameworkId || undefined,
      status: statusFilter || undefined,
      min_confidence: minConfidence,
      limit: PAGE_SIZE,
      offset,
    })
      .then((res) => {
        setGaps(res.gaps);
        setTotal(res.total);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [frameworkId, statusFilter, minConfidence, offset]);

  const totalPages = Math.ceil(total / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Gap Analysis</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Review compliance gaps across frameworks and policies
        </p>
      </div>

      <div className="flex flex-wrap gap-4 items-end">
        <div>
          <label className="block text-xs font-medium text-muted-foreground mb-1">
            Framework
          </label>
          <select
            value={frameworkId}
            onChange={(e) => { setFrameworkId(e.target.value); setOffset(0); }}
            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm"
          >
            <option value="">All Frameworks</option>
            {frameworks.map((fw) => (
              <option key={fw.id} value={fw.id}>
                {fw.name}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-xs font-medium text-muted-foreground mb-1">
            Status
          </label>
          <select
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); setOffset(0); }}
            className="rounded-md border border-input bg-background px-3 py-1.5 text-sm"
          >
            <option value="">All</option>
            <option value="compliant">Compliant</option>
            <option value="partial">Partial</option>
            <option value="non-compliant">Non-Compliant</option>
          </select>
        </div>

        <div>
          <label className="block text-xs font-medium text-muted-foreground mb-1">
            Min Confidence
          </label>
          <input
            type="number"
            min={0}
            max={1}
            step={0.1}
            placeholder="0.0"
            value={minConfidence ?? ""}
            onChange={(e) => {
              const v = e.target.value ? parseFloat(e.target.value) : undefined;
              setMinConfidence(v);
              setOffset(0);
            }}
            className="w-24 rounded-md border border-input bg-background px-3 py-1.5 text-sm"
          />
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-800 text-sm">
          {error}
        </div>
      )}

      {loading ? (
        <div className="text-center py-12 text-muted-foreground">Loading gaps...</div>
      ) : gaps.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-muted-foreground">No gaps found</p>
          <p className="text-sm text-muted-foreground mt-1">
            Run a gap analysis from the Chat to generate results
          </p>
        </div>
      ) : (
        <>
          <div className="rounded-lg border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr className="text-left text-xs font-medium text-muted-foreground uppercase tracking-wide">
                  <th className="px-4 py-3">Framework</th>
                  <th className="px-4 py-3">Requirement</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Policy</th>
                  <th className="px-4 py-3">Confidence</th>
                  <th className="px-4 py-3">Date</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {gaps.map((gap) => (
                  <>
                    <tr
                      key={gap.id}
                      onClick={() => setExpandedId(expandedId === gap.id ? null : gap.id)}
                      className="cursor-pointer hover:bg-muted/30 transition-colors"
                    >
                      <td className="px-4 py-3">{gap.framework_name ?? "—"}</td>
                      <td className="px-4 py-3 font-medium">
                        {gap.requirement_article
                          ? `Art. ${gap.requirement_article}`
                          : gap.requirement_id.slice(0, 8)}
                        {gap.requirement_section && (
                          <span className="text-muted-foreground ml-1">
                            ({gap.requirement_section})
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={cn(
                            "inline-flex rounded-full px-2 py-0.5 text-xs font-medium",
                            statusBadge[gap.status]
                          )}
                        >
                          {gap.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {gap.policy_filename ?? gap.policy_id.slice(0, 8)}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div className="h-1.5 w-16 rounded-full bg-muted overflow-hidden">
                            <div
                              className="h-full rounded-full bg-primary"
                              style={{ width: `${gap.confidence_score * 100}%` }}
                            />
                          </div>
                          <span className="text-xs text-muted-foreground">
                            {(gap.confidence_score * 100).toFixed(0)}%
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground text-xs">
                        {new Date(gap.detected_at).toLocaleDateString()}
                      </td>
                    </tr>
                    {expandedId === gap.id && (
                      <tr key={`${gap.id}-detail`}>
                        <td colSpan={6} className="px-4 py-4 bg-muted/20">
                          <div className="space-y-2">
                            <p className="text-sm font-medium">Explanation</p>
                            <p className="text-sm text-muted-foreground">
                              {gap.explanation}
                            </p>
                            {gap.evidence && Object.keys(gap.evidence).length > 0 && (
                              <div>
                                <p className="text-sm font-medium mt-2">Evidence</p>
                                <pre className="text-xs bg-background rounded p-2 mt-1 overflow-auto max-h-48">
                                  {JSON.stringify(gap.evidence, null, 2)}
                                </pre>
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">
              Showing {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                disabled={offset === 0}
                className="rounded-md border px-3 py-1.5 text-sm hover:bg-muted disabled:opacity-50"
              >
                Previous
              </button>
              <button
                onClick={() => setOffset(offset + PAGE_SIZE)}
                disabled={currentPage >= totalPages}
                className="rounded-md border px-3 py-1.5 text-sm hover:bg-muted disabled:opacity-50"
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
