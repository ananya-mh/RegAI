"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getPolicies, uploadPolicy } from "@/lib/api";
import type { Policy, PolicyUploadResult } from "@/lib/types";
import { cn } from "@/lib/utils";

export default function PoliciesPage() {
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<PolicyUploadResult | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadPolicies = useCallback(() => {
    setLoading(true);
    getPolicies()
      .then(setPolicies)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { loadPolicies(); }, [loadPolicies]);

  const handleFile = async (file: File) => {
    const ext = file.name.split(".").pop()?.toLowerCase();
    if (ext !== "pdf" && ext !== "docx") {
      setUploadError("Only PDF and DOCX files are supported.");
      return;
    }

    setUploading(true);
    setUploadResult(null);
    setUploadError(null);

    try {
      const result = await uploadPolicy(file);
      setUploadResult(result);
      loadPolicies();
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Policies</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Upload and manage company policy documents
        </p>
      </div>

      {/* Upload area */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          const file = e.dataTransfer.files[0];
          if (file) handleFile(file);
        }}
        className={cn(
          "rounded-lg border-2 border-dashed p-8 text-center transition-colors",
          dragging ? "border-primary bg-primary/5" : "border-muted-foreground/25",
          uploading && "opacity-50 pointer-events-none"
        )}
      >
        <svg
          className="mx-auto size-10 text-muted-foreground/50 mb-3"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={1.5}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
          />
        </svg>
        {uploading ? (
          <p className="text-sm text-muted-foreground">Parsing and indexing document...</p>
        ) : (
          <>
            <p className="text-sm font-medium">
              Drag and drop a PDF or DOCX file here
            </p>
            <p className="text-xs text-muted-foreground mt-1">or</p>
            <button
              onClick={() => fileInputRef.current?.click()}
              className="mt-2 rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90"
            >
              Browse files
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.docx"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleFile(file);
                e.target.value = "";
              }}
            />
          </>
        )}
      </div>

      {uploadResult && (
        <div className="rounded-lg border border-green-200 bg-green-50 p-4 flex items-center justify-between">
          <div className="text-sm text-green-800">
            <span className="font-medium">{uploadResult.policy.filename}</span> uploaded successfully
            — {uploadResult.chunks_created} chunks indexed
          </div>
          <button
            onClick={() => setUploadResult(null)}
            className="text-green-600 hover:text-green-800 text-sm"
          >
            Dismiss
          </button>
        </div>
      )}

      {uploadError && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 flex items-center justify-between">
          <p className="text-sm text-red-800">{uploadError}</p>
          <button
            onClick={() => setUploadError(null)}
            className="text-red-600 hover:text-red-800 text-sm"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Policy list */}
      <div>
        <h2 className="text-lg font-semibold mb-3">Uploaded Policies</h2>

        {loading ? (
          <div className="text-center py-8 text-muted-foreground">Loading policies...</div>
        ) : error ? (
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-800 text-sm">
            {error}
          </div>
        ) : policies.length === 0 ? (
          <div className="text-center py-8">
            <p className="text-muted-foreground">No policies uploaded yet</p>
            <p className="text-sm text-muted-foreground mt-1">
              Upload a PDF or DOCX to get started
            </p>
          </div>
        ) : (
          <div className="rounded-lg border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr className="text-left text-xs font-medium text-muted-foreground uppercase tracking-wide">
                  <th className="px-4 py-3">Filename</th>
                  <th className="px-4 py-3">Upload Date</th>
                  <th className="px-4 py-3">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {policies.map((p) => (
                  <tr key={p.id} className="hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3 font-medium">{p.filename}</td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {new Date(p.upload_date).toLocaleDateString(undefined, {
                        year: "numeric",
                        month: "short",
                        day: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </td>
                    <td className="px-4 py-3">
                      {p.parsed_text_path ? (
                        <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800">
                          Parsed
                        </span>
                      ) : (
                        <span className="rounded-full bg-yellow-100 px-2 py-0.5 text-xs font-medium text-yellow-800">
                          Pending
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
