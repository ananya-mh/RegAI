from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, StateGraph

from backend.agents.schemas import AgentState, Intent
from backend.agents.gap_analyzer import analyze_gaps
from backend.agents.interpreter import interpret_requirements
from backend.agents.remediation_planner import plan_remediation
from backend.agents.report_writer import write_report
from backend.agents.supervisor import classify_intent

logger = logging.getLogger(__name__)


def _route_after_supervisor(state: AgentState) -> str:
    if state.error:
        return "respond"

    match state.intent:
        case Intent.COMPLIANCE_CHECK | Intent.GAP_ANALYSIS:
            if state.regulation_refs:
                return "interpreter"
            return "respond"
        case Intent.REPORT_GENERATION:
            if state.regulation_refs:
                return "interpreter"
            return "respond"
        case Intent.GENERAL_QUESTION:
            if state.regulation_refs:
                return "interpreter"
            return "respond"
        case _:
            return "respond"


def _route_after_interpreter(state: AgentState) -> str:
    if state.error:
        return "respond"

    match state.intent:
        case Intent.COMPLIANCE_CHECK | Intent.GAP_ANALYSIS:
            return "gap_analyzer"
        case Intent.REPORT_GENERATION:
            return "gap_analyzer"
        case _:
            return "respond"


def _route_after_gap_analyzer(state: AgentState) -> str:
    if state.error:
        return "respond"

    match state.intent:
        case Intent.COMPLIANCE_CHECK | Intent.GAP_ANALYSIS:
            return "remediation_planner"
        case Intent.REPORT_GENERATION:
            return "remediation_planner"
        case _:
            return "respond"


def _route_after_remediation(state: AgentState) -> str:
    if state.error:
        return "respond"

    match state.intent:
        case Intent.REPORT_GENERATION:
            return "report_writer"
        case Intent.COMPLIANCE_CHECK | Intent.GAP_ANALYSIS:
            return "report_writer"
        case _:
            return "respond"


async def _respond(state: AgentState) -> AgentState:
    if state.response:
        return state

    if state.error:
        state.response = f"An error occurred: {state.error}"
        return state

    if state.interpretations:
        parts = []
        for interp in state.interpretations:
            parts.append(
                f"## {interp.regulation_id}\n\n"
                f"**Summary:** {interp.plain_language_summary}\n\n"
                f"**Operational meaning:** {interp.operational_meaning}\n\n"
                f"**Evidence of compliance:** {interp.evidence_of_compliance}"
            )
        state.response = "\n\n---\n\n".join(parts)
        return state

    state.response = "I can help with regulatory compliance questions. Try asking about a specific regulation (e.g., 'What does GDPR Article 17 require?') or request a gap analysis."
    return state


def build_graph() -> StateGraph:
    """Full compliance agent pipeline:
    Supervisor → Interpreter → Gap Analyzer → Remediation Planner → Report Writer → Respond
    """
    graph = StateGraph(AgentState)

    graph.add_node("supervisor", classify_intent)
    graph.add_node("interpreter", interpret_requirements)
    graph.add_node("gap_analyzer", analyze_gaps)
    graph.add_node("remediation_planner", plan_remediation)
    graph.add_node("report_writer", write_report)
    graph.add_node("respond", _respond)

    graph.set_entry_point("supervisor")

    graph.add_conditional_edges("supervisor", _route_after_supervisor, {
        "interpreter": "interpreter",
        "respond": "respond",
    })

    graph.add_conditional_edges("interpreter", _route_after_interpreter, {
        "gap_analyzer": "gap_analyzer",
        "respond": "respond",
    })

    graph.add_conditional_edges("gap_analyzer", _route_after_gap_analyzer, {
        "remediation_planner": "remediation_planner",
        "respond": "respond",
    })

    graph.add_conditional_edges("remediation_planner", _route_after_remediation, {
        "report_writer": "report_writer",
        "respond": "respond",
    })

    graph.add_edge("report_writer", "respond")
    graph.add_edge("respond", END)

    return graph


_compiled_graph = None


def get_graph() -> Any:
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph().compile()
    return _compiled_graph


async def run_query(query: str) -> AgentState:
    graph = get_graph()
    initial_state = AgentState(query=query)
    result = await graph.ainvoke(initial_state)
    if isinstance(result, dict):
        return AgentState(**result)
    return result
