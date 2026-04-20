import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

export function registerPrompts(server: McpServer): void {
  // ── gap_analysis ────────────────────────────────────────────────────
  server.prompt(
    "gap_analysis",
    "Structured prompt for assessing compliance gaps with few-shot examples",
    {
      regulation_text: z.string().describe("Full text of the regulatory requirement"),
      policy_text: z.string().describe("Full text of the matched company policy"),
    },
    ({ regulation_text, policy_text }) => ({
      messages: [
        {
          role: "user" as const,
          content: {
            type: "text" as const,
            text: `You are a regulatory compliance analyst. Assess whether the company policy satisfies the regulatory requirement below. Provide a structured gap assessment.

## Regulatory Requirement
${regulation_text}

## Company Policy
${policy_text}

## Instructions
Produce a JSON object with these fields:
- status: "compliant" | "partial" | "non-compliant"
- explanation: 2-3 sentences explaining the assessment
- evidence: array of specific quotes from the policy that support or contradict compliance
- confidence_score: 0.0 to 1.0
- missing_elements: array of specific requirements not addressed by the policy

## Examples of Good Assessments

### Example 1 (Compliant)
{
  "status": "compliant",
  "explanation": "The policy explicitly addresses data subject access requests with a 30-day response window, matching the regulation's requirement. The process includes identity verification and electronic delivery.",
  "evidence": ["Section 4.2: All data subject access requests shall be fulfilled within 30 calendar days", "Section 4.3: Identity verification via two-factor authentication before data release"],
  "confidence_score": 0.92,
  "missing_elements": []
}

### Example 2 (Partial)
{
  "status": "partial",
  "explanation": "The policy covers data encryption at rest but omits encryption in transit, which the regulation requires for all personal data transfers.",
  "evidence": ["Section 6.1: AES-256 encryption for all stored personal data"],
  "confidence_score": 0.75,
  "missing_elements": ["Encryption in transit for personal data transfers", "Key management procedures"]
}

### Example 3 (Non-compliant)
{
  "status": "non-compliant",
  "explanation": "The policy contains no provisions for data breach notification. The regulation mandates notification to the supervisory authority within 72 hours and to affected individuals without undue delay.",
  "evidence": [],
  "confidence_score": 0.95,
  "missing_elements": ["Breach notification to supervisory authority within 72 hours", "Breach notification to affected data subjects", "Breach severity assessment procedure"]
}

Now assess the regulation and policy above.`,
          },
        },
      ],
    }),
  );

  // ── requirement_interpreter ─────────────────────────────────────────
  server.prompt(
    "requirement_interpreter",
    "Translate legal/regulatory language into plain language with operational guidance",
    {
      regulation_text: z.string().describe("The regulatory text to interpret"),
      framework_name: z.string().optional().describe("e.g. GDPR, SOC 2"),
    },
    ({ regulation_text, framework_name }) => ({
      messages: [
        {
          role: "user" as const,
          content: {
            type: "text" as const,
            text: `You are a regulatory compliance expert specializing in ${framework_name ?? "data protection regulations"}. Translate the following regulation into plain language.

## Regulatory Text
${regulation_text}

## Provide
1. **Plain-language summary**: What this requirement says in simple terms (2-3 sentences)
2. **Operational meaning**: What an organization must concretely do to comply (bullet list)
3. **Evidence of compliance**: What documentation or controls an auditor would look for (bullet list)
4. **Common pitfalls**: Mistakes organizations commonly make when trying to comply (bullet list)
5. **Related requirements**: Other regulations or standards that overlap with this one

Format your response as a structured JSON object with these five keys.`,
          },
        },
      ],
    }),
  );

  // ── remediation_plan ────────────────────────────────────────────────
  server.prompt(
    "remediation_plan",
    "Generate actionable remediation steps for a compliance gap",
    {
      gap_description: z.string().describe("Description of the identified gap"),
      regulation_text: z.string().describe("The regulatory requirement"),
      policy_text: z.string().describe("The current company policy"),
      severity: z.enum(["low", "medium", "high", "critical"]).optional(),
    },
    ({ gap_description, regulation_text, policy_text, severity }) => ({
      messages: [
        {
          role: "user" as const,
          content: {
            type: "text" as const,
            text: `You are a compliance remediation specialist. Create a detailed, actionable remediation plan for the following compliance gap.

## Gap Assessment
${gap_description}
${severity ? `Severity: ${severity}` : ""}

## Regulatory Requirement
${regulation_text}

## Current Company Policy
${policy_text}

## Generate a Remediation Plan with:
1. **Executive summary**: One paragraph for leadership
2. **Remediation tasks**: Ordered list of specific actions, each with:
   - Title
   - Description (what exactly needs to change)
   - Effort estimate (hours or days)
   - Priority (critical/high/medium/low)
   - Suggested assignee role (e.g., "Security Engineer", "Legal Counsel")
3. **Policy changes**: Specific text additions or modifications to the policy
4. **Validation criteria**: How to verify the gap is closed
5. **Timeline**: Recommended timeline from start to audit-ready

Format your response as a structured JSON object.`,
          },
        },
      ],
    }),
  );
}
