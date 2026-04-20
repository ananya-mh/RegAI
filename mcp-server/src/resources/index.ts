import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { ResourceTemplate } from "@modelcontextprotocol/sdk/server/mcp.js";
import pool from "../db.js";

export function registerResources(server: McpServer): void {
  // ── compliance://frameworks/{framework_id} ──────────────────────────
  server.resource(
    "framework-detail",
    new ResourceTemplate("compliance://frameworks/{framework_id}", {
      list: async () => {
        const { rows } = await pool.query("SELECT id, name, version FROM frameworks ORDER BY name");
        return {
          resources: rows.map((f) => ({
            uri: `compliance://frameworks/${f.id as string}`,
            name: `${f.name as string} v${f.version as string}`,
          })),
        };
      },
    }),
    async (uri, { framework_id }) => {
      const { rows: fw } = await pool.query(
        "SELECT id, name, version, source_url, ingested_at FROM frameworks WHERE id = $1",
        [framework_id],
      );

      if (fw.length === 0) {
        return { contents: [{ uri: uri.href, text: "Framework not found" }] };
      }

      const { rows: reqs } = await pool.query(
        `SELECT id, article, section, clause, full_text, plain_language_summary
         FROM requirements WHERE framework_id = $1
         ORDER BY article, clause NULLS FIRST`,
        [framework_id],
      );

      return {
        contents: [
          {
            uri: uri.href,
            mimeType: "application/json",
            text: JSON.stringify({ framework: fw[0], requirements: reqs }, null, 2),
          },
        ],
      };
    },
  );

  // ── compliance://gaps/{framework_id} ────────────────────────────────
  server.resource(
    "framework-gaps",
    new ResourceTemplate("compliance://gaps/{framework_id}", {
      list: async () => {
        const { rows } = await pool.query("SELECT id, name FROM frameworks ORDER BY name");
        return {
          resources: rows.map((f) => ({
            uri: `compliance://gaps/${f.id as string}`,
            name: `Gaps: ${f.name as string}`,
          })),
        };
      },
    }),
    async (uri, { framework_id }) => {
      const { rows } = await pool.query(
        `SELECT g.id, g.status, g.explanation, g.confidence_score, g.detected_at,
                r.article, r.section, r.clause,
                p.filename AS policy_filename
         FROM gaps g
         JOIN requirements r ON g.requirement_id = r.id
         JOIN policies p ON g.policy_id = p.id
         WHERE r.framework_id = $1
         ORDER BY
           CASE g.status
             WHEN 'non-compliant' THEN 1
             WHEN 'partial' THEN 2
             WHEN 'compliant' THEN 3
           END,
           g.confidence_score DESC`,
        [framework_id],
      );

      const summary = {
        framework_id,
        total: rows.length,
        non_compliant: rows.filter((r) => r.status === "non-compliant").length,
        partial: rows.filter((r) => r.status === "partial").length,
        compliant: rows.filter((r) => r.status === "compliant").length,
        gaps: rows,
      };

      return {
        contents: [
          {
            uri: uri.href,
            mimeType: "application/json",
            text: JSON.stringify(summary, null, 2),
          },
        ],
      };
    },
  );

  // ── compliance://reports/latest ─────────────────────────────────────
  server.resource("latest-report", "compliance://reports/latest", async (uri) => {
    const { rows: frameworks } = await pool.query(
      `SELECT f.id, f.name, f.version,
                COUNT(DISTINCT g.id) FILTER (WHERE g.status = 'compliant') AS compliant,
                COUNT(DISTINCT g.id) FILTER (WHERE g.status = 'partial') AS partial,
                COUNT(DISTINCT g.id) FILTER (WHERE g.status = 'non-compliant') AS non_compliant
         FROM frameworks f
         LEFT JOIN requirements r ON r.framework_id = f.id
         LEFT JOIN gaps g ON g.requirement_id = r.id
         GROUP BY f.id`,
    );

    const { rows: recentGaps } = await pool.query(
      `SELECT g.id, g.status, g.explanation, g.detected_at,
                r.article, f.name AS framework
         FROM gaps g
         JOIN requirements r ON g.requirement_id = r.id
         JOIN frameworks f ON r.framework_id = f.id
         ORDER BY g.detected_at DESC
         LIMIT 20`,
    );

    const report = {
      generated_at: new Date().toISOString(),
      frameworks: frameworks.map((f) => ({
        name: f.name,
        version: f.version,
        compliant: Number(f.compliant),
        partial: Number(f.partial),
        non_compliant: Number(f.non_compliant),
      })),
      recent_gaps: recentGaps,
    };

    return {
      contents: [
        {
          uri: uri.href,
          mimeType: "application/json",
          text: JSON.stringify(report, null, 2),
        },
      ],
    };
  });
}
