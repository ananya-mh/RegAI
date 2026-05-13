from __future__ import annotations

import json
import logging

from backend.agents.schemas import AgentState, RequirementInterpretation
from backend.services.llm import generate_json
from backend.services.mcp_client import extract_json, get_mcp_client

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a regulatory compliance expert who translates legal requirements into actionable guidance.

Given a regulatory requirement (full legal text), produce a structured interpretation with:
1. A plain-language summary accessible to non-lawyers
2. What this means operationally for a company
3. What evidence of compliance looks like (documents, processes, technical controls)
4. Key legal terms that need precise understanding
5. Related requirements that should be checked alongside this one

Output JSON with this exact structure:
{
  "plain_language_summary": "<clear, jargon-free summary>",
  "operational_meaning": "<what a company must do in practice>",
  "evidence_of_compliance": "<concrete evidence that proves compliance>",
  "key_terms": ["<term1>", "<term2>"],
  "related_requirements": ["<ref1>", "<ref2>"]
}

Examples:

Requirement: GDPR Article 17 — Right to Erasure ("Right to be forgotten")
"The data subject shall have the right to obtain from the controller the erasure of personal data concerning him or her without undue delay..."
{
  "plain_language_summary": "Individuals can request that an organization delete all their personal data. The organization must do so promptly unless there is a legal reason to keep it (like legal obligations or public interest).",
  "operational_meaning": "Organizations must implement a process to receive, verify, and fulfill data deletion requests within 30 days. This requires knowing where all personal data is stored across systems, having automated or manual deletion workflows, and notifying any third parties who received the data.",
  "evidence_of_compliance": "A documented data deletion procedure, records of deletion requests and their fulfillment, data inventory/mapping showing all storage locations, third-party data processing agreements with deletion clauses, technical capability to delete data across all systems.",
  "key_terms": ["data subject", "controller", "erasure", "undue delay", "personal data"],
  "related_requirements": ["GDPR-Art12", "GDPR-Art13", "GDPR-Art30"]
}

Requirement: GDPR Article 25 — Data Protection by Design and by Default
"The controller shall implement appropriate technical and organisational measures... designed to implement data-protection principles..."
{
  "plain_language_summary": "Organizations must build privacy protections into their systems and processes from the start, not add them later. By default, only the minimum necessary personal data should be collected and processed.",
  "operational_meaning": "Every new system, product, or process that handles personal data must include a privacy impact assessment during design. Default settings must be the most privacy-friendly. Data minimization must be enforced: only collect what is strictly needed for the stated purpose.",
  "evidence_of_compliance": "Privacy impact assessments for all systems handling personal data, system architecture documentation showing privacy controls, default configuration audits showing minimal data collection, development guidelines requiring privacy review before launch.",
  "key_terms": ["data protection by design", "data protection by default", "appropriate technical measures", "data minimisation"],
  "related_requirements": ["GDPR-Art5", "GDPR-Art32", "GDPR-Art35"]
}

Requirement: SOC 2 CC1.1 — COSO Principle 1: Demonstrates Commitment to Integrity and Ethical Values
"The entity demonstrates a commitment to integrity and ethical values."
{
  "plain_language_summary": "The organization must show it takes honesty and ethics seriously through formal policies and visible leadership behavior, not just words.",
  "operational_meaning": "Establish a code of conduct, enforce it consistently, provide ethics training, create whistleblower channels, and ensure leadership visibly models ethical behavior. Board or equivalent body must oversee ethics compliance.",
  "evidence_of_compliance": "Written code of conduct signed by all employees, annual ethics training records, whistleblower/hotline reports and resolution tracking, board meeting minutes discussing ethical matters, disciplinary action records for violations.",
  "key_terms": ["integrity", "ethical values", "tone at the top", "code of conduct"],
  "related_requirements": ["SOC2-CC1.2", "SOC2-CC1.3", "SOC2-CC2.1"]
}\
"""


async def interpret_requirements(state: AgentState) -> AgentState:
    """Regulatory Interpreter node: looks up and interprets each regulation reference."""
    mcp = get_mcp_client()
    interpretations: list[RequirementInterpretation] = []

    for ref in state.regulation_refs:
        try:
            tool_result = await mcp.call_tool("lookup_requirement", {"regulation_id": ref})
            requirement_data = extract_json(tool_result)

            if not requirement_data.get("found", True) is False:
                requirements = requirement_data.get("requirements", [])
                full_text = "\n\n".join(
                    r.get("full_text", "") for r in requirements
                )
                framework = requirement_data.get("framework", ref.split("-")[0])

                prompt = (
                    f"Requirement: {framework} {ref}\n"
                    f'"{full_text[:3000]}"'
                )

                result = await generate_json(
                    prompt=prompt,
                    system_prompt=SYSTEM_PROMPT,
                    temperature=0.2,
                    prefer="gemini",
                    agent_name="regulatory_interpreter",
                )

                raw_citations = requirement_data.get("citation", [])
                if isinstance(raw_citations, dict):
                    raw_citations = [raw_citations]

                interpretation = RequirementInterpretation(
                    regulation_id=ref,
                    framework=framework,
                    article=ref.split("-", 1)[-1] if "-" in ref else ref,
                    plain_language_summary=result.get("plain_language_summary", ""),
                    operational_meaning=result.get("operational_meaning", ""),
                    evidence_of_compliance=result.get("evidence_of_compliance", ""),
                    key_terms=result.get("key_terms", []),
                    related_requirements=result.get("related_requirements", []),
                    citations=raw_citations,
                )
                interpretations.append(interpretation)
                logger.info("Interpreted %s: %s", ref, interpretation.plain_language_summary[:80])
            else:
                logger.warning("Requirement %s not found in database", ref)
                interpretations.append(
                    RequirementInterpretation(
                        regulation_id=ref,
                        framework=ref.split("-")[0] if "-" in ref else ref,
                        article=ref.split("-", 1)[-1] if "-" in ref else "",
                        plain_language_summary=f"Requirement {ref} was not found in the database.",
                        operational_meaning="Unable to interpret — requirement not ingested.",
                        evidence_of_compliance="N/A",
                    )
                )

        except Exception as e:
            logger.error("Failed to interpret %s: %s", ref, e, exc_info=True)
            interpretations.append(
                RequirementInterpretation(
                    regulation_id=ref,
                    framework=ref.split("-")[0] if "-" in ref else ref,
                    article=ref.split("-", 1)[-1] if "-" in ref else "",
                    plain_language_summary=f"Error interpreting {ref}: {e}",
                    operational_meaning="Interpretation failed due to an error.",
                    evidence_of_compliance="N/A",
                )
            )

    state.interpretations = interpretations

    if state.intent and state.intent.value == "general_question" and interpretations:
        parts = []
        for interp in interpretations:
            parts.append(
                f"## {interp.regulation_id}\n\n"
                f"**Summary:** {interp.plain_language_summary}\n\n"
                f"**What it means operationally:** {interp.operational_meaning}\n\n"
                f"**Evidence of compliance:** {interp.evidence_of_compliance}\n\n"
                f"**Key terms:** {', '.join(interp.key_terms)}\n\n"
                f"**Related:** {', '.join(interp.related_requirements)}"
            )
        state.response = "\n\n---\n\n".join(parts)

    return state
