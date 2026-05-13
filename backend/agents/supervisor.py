from __future__ import annotations

import json
import logging

from backend.agents.schemas import AgentState, Intent, SupervisorDecision
from backend.services.llm import generate_json

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a regulatory compliance query classifier. Given a user query, determine its intent and extract any regulation or policy references.

Intents:
- compliance_check: User wants to check if a policy complies with a specific regulation
- gap_analysis: User wants to identify gaps between their policies and regulations
- report_generation: User wants to generate a compliance report
- general_question: General question about regulations, compliance concepts, or the system

Output JSON with this exact structure:
{
  "intent": "<one of: compliance_check, gap_analysis, report_generation, general_question>",
  "reasoning": "<one sentence explaining why>",
  "regulation_refs": ["<extracted regulation references like GDPR-Art17, SOC2-CC1.1>"],
  "policy_refs": ["<extracted policy names or references>"]
}

Examples:

Query: "Does our data retention policy comply with GDPR Article 17?"
{
  "intent": "compliance_check",
  "reasoning": "User is asking about compliance of a specific policy against a specific GDPR article",
  "regulation_refs": ["GDPR-Art17"],
  "policy_refs": ["data retention policy"]
}

Query: "Find all gaps in our security policies against SOC 2"
{
  "intent": "gap_analysis",
  "reasoning": "User wants a comprehensive gap analysis across SOC 2 framework",
  "regulation_refs": ["SOC2"],
  "policy_refs": ["security policies"]
}

Query: "Generate a compliance report for GDPR"
{
  "intent": "report_generation",
  "reasoning": "User explicitly requests report generation for a framework",
  "regulation_refs": ["GDPR"],
  "policy_refs": []
}

Query: "What does Article 25 of GDPR mean?"
{
  "intent": "general_question",
  "reasoning": "User is asking for explanation of a regulation, not checking compliance",
  "regulation_refs": ["GDPR-Art25"],
  "policy_refs": []
}\
"""


async def classify_intent(state: AgentState) -> AgentState:
    """Supervisor node: classifies user query intent and extracts references."""
    try:
        result = await generate_json(
            prompt=f"Query: \"{state.query}\"",
            system_prompt=SYSTEM_PROMPT,
            temperature=0.1,
            prefer="ollama",
            agent_name="supervisor",
        )

        intent_str = result.get("intent", "general_question")
        try:
            intent = Intent(intent_str)
        except ValueError:
            intent = Intent.GENERAL_QUESTION

        decision = SupervisorDecision(
            intent=intent,
            reasoning=result.get("reasoning", ""),
            regulation_refs=result.get("regulation_refs", []),
            policy_refs=result.get("policy_refs", []),
        )

        state.intent = intent
        state.supervisor_decision = decision
        state.regulation_refs = decision.regulation_refs
        state.policy_refs = decision.policy_refs

        logger.info("Supervisor classified as %s: %s", intent.value, decision.reasoning)

    except (json.JSONDecodeError, KeyError) as e:
        logger.warning("Supervisor classification failed, defaulting to general_question: %s", e)
        state.intent = Intent.GENERAL_QUESTION
        state.supervisor_decision = SupervisorDecision(
            intent=Intent.GENERAL_QUESTION,
            reasoning=f"Classification failed: {e}",
        )

    return state
