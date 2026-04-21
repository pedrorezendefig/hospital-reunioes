export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  timestamp: string; // frontend-only, not sent to the API
}

/** Shape sent to POST /chat-correcao — no timestamp */
export interface ChatMessagePayload {
  role: "user" | "assistant";
  content: string;
}

export interface CorrectionItem {
  field: string;
  action: "update" | "delete" | "add";
  description: string;
}

export interface ChatCorrecaoResponse {
  reply: string;
  correction_plan: CorrectionItem[];
}
