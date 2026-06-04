from __future__ import annotations

import logging
from typing import Any

from backend.agents.schemas import AgentState
from backend.services.llm import generate_json
from backend.services.mcp_client import extract_json, get_mcp_client

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a compliance report writer. Synthesize gap analysis findings into a structured report section.

Output JSON:
{
  "title": "<report section title>",
  "executive_summary": "<2-3 sentence overview of findings>",
  "overall_risk_level": "<low|medium|high|critical>",
  "findings": [
    {
      "requirement": "<regulation reference>",
      "status": "<compliant|partial|non-compliant>",
      "explanation": "<concise finding>",
      "recommendation": "<what to do about it>"
    }
  ],
  "remediation_roadmap": "<prioritized summary of next steps>"
}

Risk level criteria:
- critical: any non-compliant findings on core requirements
- high: multiple partial findings or non-compliant on secondary requirements
- medium: mostly compliant with minor partial gaps
- low: fully or nearly fully compliant\
"""


async def write_report(state: AgentState) -> AgentState:
    """Report Writer node: synthesizes findings into structured report sections."""
    if not state.gap_assessments and not state.interpretations:
        return state

    findings_text = ""
    for gap in state.gap_assessments:
        findings_text += (
            f"- {gap.requirement_id}: {gap.status} ({gap.confidence_score:.0%}) "
            f"— {gap.explanation[:200]}\n"
        )

    tasks_text = ""
    for task in state.remediation_tasks:
        tasks_text += (
            f"- [{task.get('priority', 'medium')}] {task.get('title', 'N/A')}: "
            f"{task.get('description', '')[:150]}\n"
        )

    prompt = (
        f"Generate a compliance report section.\n\n"
        f"Gap Analysis Findings:\n{findings_text or 'No gaps analyzed.'}\n\n"
        f"Remediation Tasks:\n{tasks_text or 'No tasks planned.'}\n\n"
        f"Interpretations covered: {', '.join(i.regulation_id for i in state.interpretations)}"
    )

    try:
        result = await generate_json(
            prompt=prompt,
            system_prompt=SYSTEM_PROMPT,
            temperature=0.2,
            prefer="gemini",
            agent_name="report_writer",
        )
        state.report_sections.append(result)

        logger.info(
            "Report section generated: %s (risk: %s)",
            result.get("title", "Untitled"),
            result.get("overall_risk_level", "unknown"),
        )

    except Exception as e:
        logger.error("Report generation failed: %s", e)
        state.report_sections.append({
            "title": "Compliance Report",
            "executive_summary": f"Report generation encountered an error: {e}",
            "overall_risk_level": "unknown",
            "findings": [],
            "remediation_roadmap": "Manual review required.",
        })

    if not state.response:
        _build_response(state)

    return state


def _build_response(state: AgentState) -> None:
    """Build a markdown response from all accumulated state."""
    parts: list[str] = []

    for section in state.report_sections:
        parts.append(f"# {section.get('title', 'Compliance Report')}")
        parts.append(f"\n**Risk Level:** {section.get('overall_risk_level', 'N/A').upper()}")
        parts.append(f"\n{section.get('executive_summary', '')}")

        findings = section.get("findings", [])
        if findings:
            parts.append("\n## Findings\n")
            for f in findings:
                status = f.get("status", "unknown")
                icon = {"compliant": "COMPLIANT", "partial": "PARTIAL", "non-compliant": "NON-COMPLIANT"}.get(
                    status, status.upper()
                )
                parts.append(
                    f"### {f.get('requirement', 'N/A')} — **{icon}**\n"
                    f"{f.get('explanation', '')}\n\n"
                    f"**Recommendation:** {f.get('recommendation', 'N/A')}\n"
                )

        roadmap = section.get("remediation_roadmap")
        if roadmap:
            parts.append(f"\n## Remediation Roadmap\n\n{roadmap}")

    if state.remediation_tasks:
        parts.append("\n## Remediation Tasks\n")
        for task in state.remediation_tasks:
            priority = task.get("priority", "medium").upper()
            parts.append(
                f"- **[{priority}]** {task.get('title', 'N/A')} "
                f"(effort: {task.get('effort_estimate', 'TBD')})"
            )

    parts.append(
        "\n\n---\n*AI-generated assessment for informational purposes only. "
        "Does not constitute legal advice.*"
    )

    state.response = "\n".join(parts)
