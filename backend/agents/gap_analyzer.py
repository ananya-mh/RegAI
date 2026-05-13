from __future__ import annotations

import json
import logging
from itertools import product as cartesian

from backend.agents.schemas import AgentState, GapAssessment
from backend.services.llm import generate_json
from backend.services.mcp_client import extract_json, get_mcp_client

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a regulatory compliance gap analyst. Given a regulation requirement and a company policy excerpt, determine whether the policy satisfies the requirement.

Perform chain-of-thought reasoning:
1. Read the regulation text carefully — identify each specific obligation
2. Read the policy text carefully — identify what it addresses
3. For each obligation, determine if the policy covers it fully, partially, or not at all
4. Assess confidence based on how clearly the evidence supports your conclusion

Output JSON with this exact structure:
{
  "status": "<compliant | partial | non-compliant>",
  "chain_of_thought": "<your step-by-step reasoning>",
  "explanation": "<concise summary of the assessment>",
  "regulation_evidence": ["<exact quotes from the regulation that define the obligations>"],
  "policy_evidence": ["<exact quotes from the policy that address (or fail to address) those obligations>"],
  "confidence_score": <0.0 to 1.0>,
  "gaps_identified": ["<specific gaps found, empty if compliant>"]
}

Assessment criteria:
- "compliant": The policy explicitly addresses ALL obligations in the requirement with specific, actionable measures
- "partial": The policy addresses SOME obligations but misses others, OR addresses them vaguely without specifics
- "non-compliant": The policy does not address the requirement at all, or contradicts it

Confidence scoring:
- 0.9–1.0: Clear, unambiguous evidence in both regulation and policy
- 0.7–0.89: Strong evidence but some interpretation required
- 0.5–0.69: Moderate evidence, reasonable people could disagree
- Below 0.5: Weak evidence, assessment is uncertain

Examples:

Regulation: "The controller shall implement appropriate technical and organisational measures to ensure a level of security appropriate to the risk, including encryption of personal data."
Policy: "All personal data at rest is encrypted using AES-256. Data in transit uses TLS 1.3. Key management follows NIST SP 800-57."
{
  "status": "compliant",
  "chain_of_thought": "The regulation requires: (1) technical measures appropriate to risk, (2) specifically mentions encryption. The policy provides: (1) AES-256 encryption at rest (technical measure), (2) TLS 1.3 in transit, (3) NIST-compliant key management. All obligations are met with specific, industry-standard measures.",
  "explanation": "The policy fully addresses the encryption requirement with AES-256 at rest, TLS 1.3 in transit, and NIST-compliant key management, exceeding the minimum standard.",
  "regulation_evidence": ["implement appropriate technical and organisational measures", "encryption of personal data"],
  "policy_evidence": ["All personal data at rest is encrypted using AES-256", "Data in transit uses TLS 1.3", "Key management follows NIST SP 800-57"],
  "confidence_score": 0.95,
  "gaps_identified": []
}

Regulation: "Data subjects have the right to obtain from the controller a copy of their personal data in a structured, commonly used and machine-readable format."
Policy: "Users can request their data by emailing support@company.com. We will respond within 60 days."
{
  "status": "partial",
  "chain_of_thought": "The regulation requires: (1) right to obtain a copy, (2) structured format, (3) commonly used format, (4) machine-readable format. The policy provides: (1) a mechanism to request data (email), (2) a response timeline (60 days, but GDPR requires 30 days). Missing: no mention of structured/machine-readable format, response time exceeds legal requirement.",
  "explanation": "The policy acknowledges the right to data access but lacks specifics on data format (must be structured and machine-readable) and the 60-day response time exceeds the GDPR's 30-day requirement.",
  "regulation_evidence": ["right to obtain from the controller a copy", "structured, commonly used and machine-readable format"],
  "policy_evidence": ["Users can request their data by emailing support@company.com", "We will respond within 60 days"],
  "confidence_score": 0.85,
  "gaps_identified": ["No specification of machine-readable format for data export", "Response time (60 days) exceeds GDPR 30-day requirement"]
}

Regulation: "The controller shall carry out a data protection impact assessment where processing is likely to result in a high risk to the rights and freedoms of natural persons."
Policy: "We collect user email addresses for newsletter delivery."
{
  "status": "non-compliant",
  "chain_of_thought": "The regulation requires: (1) a data protection impact assessment (DPIA), (2) specifically for high-risk processing. The policy: (1) describes a data collection practice, (2) makes no mention of DPIAs, risk assessments, or any evaluation of processing risk. There is a complete absence of any DPIA process.",
  "explanation": "The policy contains no reference to data protection impact assessments or any risk evaluation process for data processing activities.",
  "regulation_evidence": ["carry out a data protection impact assessment", "processing is likely to result in a high risk"],
  "policy_evidence": ["We collect user email addresses for newsletter delivery"],
  "confidence_score": 0.92,
  "gaps_identified": ["No DPIA process defined", "No risk assessment methodology for data processing", "No criteria for identifying high-risk processing"]
}\
"""


async def analyze_gaps(state: AgentState) -> AgentState:
    """Gap Analyzer node: assesses compliance gaps for each regulation-policy pair."""
    mcp = get_mcp_client()
    assessments: list[GapAssessment] = []

    reg_refs = state.regulation_refs or []
    pol_refs = state.policy_refs or []

    if not pol_refs:
        pol_refs = ["all"]

    pairs = list(cartesian(reg_refs, pol_refs))

    for reg_ref, pol_ref in pairs:
        try:
            tool_result = await mcp.call_tool("analyze_gap", {
                "requirement_ref": reg_ref,
                "policy_ref": pol_ref,
            })
            gap_data = extract_json(tool_result)

            reg_text = _extract_regulation_text(gap_data, state, reg_ref)
            pol_text = _extract_policy_text(gap_data)
            citations = gap_data.get("citation", gap_data.get("citations", []))

            prompt = (
                f"Regulation ({reg_ref}):\n\"{reg_text[:2000]}\"\n\n"
                f"Policy ({pol_ref}):\n\"{pol_text[:2000]}\""
            )

            result = await generate_json(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT,
                temperature=0.2,
                prefer="gemini",
                agent_name="gap_analyzer",
            )

            assessment = GapAssessment(
                requirement_id=reg_ref,
                policy_id=pol_ref,
                status=result.get("status", "non-compliant"),
                explanation=result.get("explanation", ""),
                regulation_evidence=result.get("regulation_evidence", []),
                policy_evidence=result.get("policy_evidence", []),
                confidence_score=min(1.0, max(0.0, result.get("confidence_score", 0.5))),
                citations=[citations] if isinstance(citations, dict) else citations,
            )
            assessments.append(assessment)

            logger.info(
                "Gap analysis %s vs %s: %s (%.0f%% confidence)",
                reg_ref, pol_ref, assessment.status, assessment.confidence_score * 100,
            )

        except Exception as e:
            logger.error("Gap analysis failed for %s vs %s: %s", reg_ref, pol_ref, e, exc_info=True)
            assessments.append(GapAssessment(
                requirement_id=reg_ref,
                policy_id=pol_ref,
                status="non-compliant",
                explanation=f"Gap analysis failed: {e}",
                confidence_score=0.0,
            ))

    state.gap_assessments = assessments

    parts = []
    for a in assessments:
        status_icon = {"compliant": "COMPLIANT", "partial": "PARTIAL", "non-compliant": "NON-COMPLIANT"}.get(
            a.status, a.status.upper()
        )
        section = (
            f"### {a.requirement_id} vs {a.policy_id} — **{status_icon}** "
            f"(confidence: {a.confidence_score:.0%})\n\n"
            f"{a.explanation}\n"
        )
        if a.regulation_evidence:
            section += "\n**Regulation evidence:**\n"
            section += "\n".join(f"- \"{e}\"" for e in a.regulation_evidence)
        if a.policy_evidence:
            section += "\n\n**Policy evidence:**\n"
            section += "\n".join(f"- \"{e}\"" for e in a.policy_evidence)
        parts.append(section)

    state.response = "\n\n---\n\n".join(parts)
    return state


def _extract_regulation_text(
    gap_data: dict, state: AgentState, reg_ref: str
) -> str:
    """Pull regulation text from MCP result or fall back to interpreter output."""
    reg_chunks = gap_data.get("regulatory_chunks", [])
    if reg_chunks:
        return "\n\n".join(
            c.get("text", "") if isinstance(c, dict) else str(c)
            for c in reg_chunks[:5]
        )
    for interp in state.interpretations:
        if interp.regulation_id == reg_ref:
            return (
                f"{interp.plain_language_summary}\n\n"
                f"Operational meaning: {interp.operational_meaning}\n\n"
                f"Evidence of compliance: {interp.evidence_of_compliance}"
            )
    return f"Regulation reference: {reg_ref}"


def _extract_policy_text(gap_data: dict) -> str:
    """Pull policy text from MCP result."""
    pol_chunks = gap_data.get("policy_chunks", [])
    if pol_chunks:
        return "\n\n".join(
            c.get("text", "") if isinstance(c, dict) else str(c)
            for c in pol_chunks[:5]
        )
    return gap_data.get("policy_text", "No policy text available.")
