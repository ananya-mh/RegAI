import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { apiPost } from "../api-client.js";
import pool from "../db.js";

function err(message: string) {
  return { content: [{ type: "text" as const, text: message }], isError: true };
}

function ok(data: unknown) {
  return {
    content: [{ type: "text" as const, text: JSON.stringify(data, null, 2) }],
  };
}

export function registerTools(server: McpServer): void {
  // ── lookup_requirement ──────────────────────────────────────────────
  server.tool(
    "lookup_requirement",
    "Look up a regulatory requirement by ID (e.g. GDPR-Art17)",
    { regulation_id: z.string().describe("e.g. GDPR-Art17, SOC2-CC1.1") },
    async ({ regulation_id }) => {
      try {
        const [framework, ...rest] = regulation_id.split("-");
        const artRef = rest.join("-").replace(/^Art/i, "");

        const { rows } = await pool.query(
          `SELECT r.id, r.article, r.section, r.clause, r.full_text,
                  r.plain_language_summary, f.name AS framework_name
           FROM requirements r
           JOIN frameworks f ON r.framework_id = f.id
           WHERE f.name ILIKE $1 AND r.article = $2
           ORDER BY r.clause NULLS FIRST`,
          [framework, artRef],
        );

        if (rows.length === 0) {
          return ok({ regulation_id, found: false, message: "No matching requirement" });
        }

        return ok({
          regulation_id,
          framework: rows[0]?.framework_name,
          requirements: rows.map((r) => ({
            id: r.id,
            article: r.article,
            section: r.section,
            clause: r.clause,
            full_text: r.full_text,
            plain_language_summary: r.plain_language_summary,
          })),
          citation: { source: "PostgreSQL requirements table", ids: rows.map((r) => r.id) },
        });
      } catch (e) {
        return err(`lookup_requirement failed: ${e instanceof Error ? e.message : String(e)}`);
      }
    },
  );

  // ── analyze_gap ─────────────────────────────────────────────────────
  server.tool(
    "analyze_gap",
    "Perform cross-index gap analysis between a regulation and a policy",
    {
      requirement_ref: z.string().describe("Regulation reference, e.g. GDPR-Art17"),
      policy_ref: z.string().describe("Policy document name or ID"),
    },
    async ({ requirement_ref, policy_ref }) => {
      try {
        const result = await apiPost<Record<string, unknown>>("/api/internal/analyze-gap", {
          requirement_ref,
          policy_ref,
        });
        return ok(result);
      } catch (e) {
        return err(`analyze_gap failed: ${e instanceof Error ? e.message : String(e)}`);
      }
    },
  );

  // ── search_policies ─────────────────────────────────────────────────
  server.tool(
    "search_policies",
    "Semantic search across uploaded company policies",
    {
      query: z.string().describe("Natural-language search query"),
      document_name: z.string().optional().describe("Filter by document name"),
      section: z.string().optional().describe("Filter by section header"),
      upload_date: z.string().optional().describe("Filter by upload date (ISO)"),
    },
    async ({ query, document_name, section, upload_date }) => {
      try {
        const result = await apiPost<Record<string, unknown>>("/api/internal/search-policies", {
          query,
          filters: { document_name, section, upload_date },
        });
        return ok(result);
      } catch (e) {
        return err(`search_policies failed: ${e instanceof Error ? e.message : String(e)}`);
      }
    },
  );

  // ── get_compliance_status ───────────────────────────────────────────
  server.tool(
    "get_compliance_status",
    "Get compliance coverage matrix with gap breakdown",
    {
      framework_id: z.string().uuid().optional().describe("Filter to a specific framework"),
    },
    async ({ framework_id }) => {
      try {
        const fwFilter = framework_id ? "AND f.id = $1" : "";
        const params: string[] = framework_id ? [framework_id] : [];

        const { rows: frameworks } = await pool.query(
          `SELECT f.id, f.name, f.version,
                  COUNT(DISTINCT r.id) AS total_requirements,
                  COUNT(DISTINCT g.id) FILTER (WHERE g.status = 'compliant') AS compliant,
                  COUNT(DISTINCT g.id) FILTER (WHERE g.status = 'partial') AS partial,
                  COUNT(DISTINCT g.id) FILTER (WHERE g.status = 'non-compliant') AS non_compliant
           FROM frameworks f
           LEFT JOIN requirements r ON r.framework_id = f.id
           LEFT JOIN gaps g ON g.requirement_id = r.id
           WHERE 1=1 ${fwFilter}
           GROUP BY f.id, f.name, f.version
           ORDER BY f.name`,
          params,
        );

        const { rows: tasks } = await pool.query(
          `SELECT rt.status, COUNT(*) AS count
           FROM remediation_tasks rt
           JOIN gaps g ON rt.gap_id = g.id
           JOIN requirements r ON g.requirement_id = r.id
           ${framework_id ? "WHERE r.framework_id = $1" : ""}
           GROUP BY rt.status`,
          params,
        );

        return ok({
          frameworks: frameworks.map((f) => {
            const assessed = Number(f.compliant) + Number(f.partial) + Number(f.non_compliant);
            const total = Number(f.total_requirements);
            return {
              id: f.id,
              name: f.name,
              version: f.version,
              total_requirements: total,
              assessed,
              compliant: Number(f.compliant),
              partial: Number(f.partial),
              non_compliant: Number(f.non_compliant),
              coverage_pct: total > 0 ? Math.round((assessed / total) * 100) : 0,
            };
          }),
          remediation: Object.fromEntries(tasks.map((t) => [t.status, Number(t.count)])),
          citation: { source: "PostgreSQL gaps + remediation_tasks" },
        });
      } catch (e) {
        return err(`get_compliance_status failed: ${e instanceof Error ? e.message : String(e)}`);
      }
    },
  );

  // ── create_remediation_task ─────────────────────────────────────────
  server.tool(
    "create_remediation_task",
    "Create a remediation task for a compliance gap (requires confirmation)",
    {
      gap_id: z.string().uuid().describe("ID of the gap to remediate"),
      title: z.string().describe("Task title"),
      description: z.string().describe("Task description"),
      priority: z.enum(["low", "medium", "high", "critical"]).default("medium"),
      effort_estimate: z.string().optional().describe("e.g. '2-3 days'"),
      assignee: z.string().optional(),
      confirmed: z.boolean().default(false).describe("Set true to execute"),
    },
    async ({ gap_id, title, description, priority, effort_estimate, assignee, confirmed }) => {
      try {
        if (!confirmed) {
          return ok({
            status: "confirmation_required",
            message: "Review the task below and call again with confirmed=true to create it.",
            task_preview: { gap_id, title, description, priority, effort_estimate, assignee },
          });
        }

        const { rows } = await pool.query(
          `INSERT INTO remediation_tasks (id, gap_id, title, description, priority, effort_estimate, assignee, status)
           VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, $6, 'open')
           RETURNING id, created_at`,
          [gap_id, title, description, priority, effort_estimate ?? null, assignee ?? null],
        );

        const created = rows[0];

        await pool.query(
          `INSERT INTO audit_log (id, action, entity_type, entity_id, details, performed_by)
           VALUES (gen_random_uuid(), 'task_created', 'remediation_task', $1, $2, 'mcp-server')`,
          [created?.id, JSON.stringify({ gap_id, title, priority })],
        );

        return ok({
          status: "created",
          task: { id: created?.id, created_at: created?.created_at, title, priority },
          citation: { source: "PostgreSQL remediation_tasks" },
        });
      } catch (e) {
        return err(`create_remediation_task failed: ${e instanceof Error ? e.message : String(e)}`);
      }
    },
  );

  // ── generate_report_section ─────────────────────────────────────────
  server.tool(
    "generate_report_section",
    "Generate a formatted compliance report section with citations",
    {
      framework_id: z.string().uuid().optional().describe("Generate for entire framework"),
      gap_id: z.string().uuid().optional().describe("Generate for a specific gap"),
    },
    async ({ framework_id, gap_id }) => {
      try {
        if (!framework_id && !gap_id) {
          return err("Provide either framework_id or gap_id");
        }
        const result = await apiPost<Record<string, unknown>>(
          "/api/internal/generate-report-section",
          { framework_id, gap_id },
        );
        return ok(result);
      } catch (e) {
        return err(`generate_report_section failed: ${e instanceof Error ? e.message : String(e)}`);
      }
    },
  );
}
