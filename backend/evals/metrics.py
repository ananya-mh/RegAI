from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

agent_latency_seconds = Histogram(
    "regai_agent_latency_seconds",
    "Agent execution latency in seconds",
    labelnames=["agent_name"],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
)

llm_cost_total = Counter(
    "regai_llm_cost_total",
    "Cumulative LLM cost in USD",
    labelnames=["provider", "model"],
)

gap_analysis_accuracy = Gauge(
    "regai_gap_analysis_accuracy",
    "Current gap analysis accuracy from eval suite",
)

retrieval_pairs_total = Counter(
    "regai_retrieval_pairs_total",
    "Total regulation-policy pairs retrieved",
)


def record_agent_latency(agent_name: str, seconds: float) -> None:
    agent_latency_seconds.labels(agent_name=agent_name).observe(seconds)


def record_llm_cost(provider: str, model: str, cost: float) -> None:
    llm_cost_total.labels(provider=provider, model=model).inc(cost)
