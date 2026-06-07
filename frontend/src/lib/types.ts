export interface Framework {
  id: string;
  name: string;
  version: string;
  source_url: string | null;
  ingested_at: string;
}

export interface FrameworkStatus {
  framework: Framework;
  total_requirements: number;
  assessed: number;
  compliant: number;
  partial: number;
  non_compliant: number;
  coverage_pct: number;
}

export interface Gap {
  id: string;
  requirement_id: string;
  policy_id: string;
  status: "compliant" | "partial" | "non-compliant";
  explanation: string;
  evidence: Record<string, unknown> | null;
  confidence_score: number;
  detected_at: string;
  requirement_article: string | null;
  requirement_section: string | null;
  framework_name: string | null;
  policy_filename: string | null;
}

export interface GapList {
  gaps: Gap[];
  total: number;
}

export interface RemediationTask {
  id: string;
  gap_id: string;
  title: string;
  description: string | null;
  priority: "low" | "medium" | "high" | "critical";
  effort_estimate: string | null;
  assignee: string | null;
  status: "open" | "in-progress" | "done";
  created_at: string;
  completed_at: string | null;
}

export interface Policy {
  id: string;
  filename: string;
  upload_date: string;
  parsed_text_path: string | null;
}

export interface PolicyUploadResult {
  policy: Policy;
  chunks_created: number;
}

export interface ProviderUsage {
  provider: string;
  model: string;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost: number;
}

export interface AgentUsage {
  agent_name: string | null;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost: number;
}

export interface UsageSummary {
  total_cost: number;
  total_input_tokens: number;
  total_output_tokens: number;
  by_provider: ProviderUsage[];
  by_agent: AgentUsage[];
}

export interface ChatSSEEvent {
  event: "status" | "interpretations" | "gaps" | "text" | "error" | "done";
  data: string;
}
