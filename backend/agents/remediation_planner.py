from __future__ import annotations

import logging

from backend.agents.schemas import AgentState
from backend.services.llm import generate_json
from backend.services.mcp_client import extract_json, get_mcp_client

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a compliance remediation planner. Given a gap assessment, generate actionable remediation tasks.

For each gap, produce one or more tasks with:
- title: concise action item
- description: what specifically needs to be done
- priority: critical (legal risk, active violation), high (significant gap), medium (partial compliance), low (minor improvement)
- effort_estimate: realistic time estimate (e.g. "2-3 days", "1 week", "2-4 hours")

Output JSON:
{
  "tasks": [
    {
      "title": "<action item>",
      "description": "<detailed steps>",
      "priority": "<critical|high|medium|low>",
      "effort_estimate": "<time estimate>"
    }
  ]
}

Priority mapping:
- non-compliant gaps → critical or high priority
- partial gaps → medium or high priority
- compliant gaps → no tasks needed (return empty tasks array)

Be specific. "Update privacy policy" is bad. "Add data deletion request procedure to privacy policy Section 4, including 30-day response timeline and machine-readable export format" is good.\
"""


async def plan_remediation(state: AgentState) -> AgentState:
    """Remediation Planner node: generates tasks from gap assessments."""
    if not state.gap_assessments:
        return state

    mcp = get_mcp_client()
    all_tasks: list[dict] = []

    for gap in state.gap_assessments:
        if gap.status == "compliant":
            continue

        try:
            prompt = (
                f"Gap: {gap.requirement_id} vs {gap.policy_id}\n"
                f"Status: {gap.status}\n"
                f"Explanation: {gap.explanation}\n"
                f"Confidence: {gap.confidence_score:.0%}\n"
                f"Regulation evidence: {'; '.join(gap.regulation_evidence[:3])}\n"
                f"Policy evidence: {'; '.join(gap.policy_evidence[:3])}"
            )

            result = await generate_json(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT,
                temperature=0.3,
                prefer="ollama",
                agent_name="remediation_planner",
            )

            tasks = result.get("tasks", [])
            for task in tasks:
                task["gap_id"] = gap.requirement_id
                task["gap_status"] = gap.status
                all_tasks.append(task)

                logger.info(
                    "Planned task for %s: %s (%s)",
                    gap.requirement_id, task.get("title", ""), task.get("priority", ""),
                )

        except Exception as e:
            logger.error("Remediation planning failed for %s: %s", gap.requirement_id, e)
            all_tasks.append({
                "gap_id": gap.requirement_id,
                "title": f"Review and remediate {gap.requirement_id} gap",
                "description": f"Automated planning failed: {e}. Manual review required.",
                "priority": "high" if gap.status == "non-compliant" else "medium",
                "effort_estimate": "TBD",
            })

    state.remediation_tasks = all_tasks
    return state
