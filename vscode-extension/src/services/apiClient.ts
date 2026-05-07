import * as vscode from "vscode";

export interface SearchResult {
  chunk_id: string; content: string; filepath: string;
  start_line: number; end_line: number; language: string; score: number;
}
export interface IndexResult {
  indexed_files: number; total_chunks: number; skipped_files: number;
  errors: Array<{ filepath: string; error: string }>;
}
export interface ChatMessage { role: "user" | "assistant" | "system"; content: string; }
export interface HealthStatus {
  status: "ok" | "degraded" | "unavailable";
  ollama: "ok" | "degraded" | "unavailable";
  chromadb: "ok" | "degraded" | "unavailable";
  embedding_model: "ok" | "degraded" | "unavailable";
  ollama_model: string; indexed_chunks: number;
}
export interface IndexFilePayload { filepath: string; content: string; language: string; }

async function fetchWithTimeout(url: string, options: RequestInit, timeoutMs: number): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    return response;
  } catch (err: any) {
    if (err.name === "AbortError") { throw new Error(`Request timed out after ${timeoutMs / 1000}s. Is the backend running?`); }
    throw new Error(`Network error: ${err.message}. Is the backend running?`);
  } finally { clearTimeout(timer); }
}

export function languageFromExtension(ext: string): string {
  const map: Record<string, string> = {
    py: "python", js: "javascript", ts: "typescript", tsx: "typescript",
    jsx: "javascript", java: "java", cpp: "cpp", cc: "cpp", cxx: "cpp",
    c: "c", go: "go", rs: "rust", rb: "ruby", php: "php",
  };
  return map[ext.toLowerCase()] ?? "unknown";
}

export class ApiClient {
  private baseUrl: string;
  constructor() {
    const config = vscode.workspace.getConfiguration("aiCodeAssistant");
    this.baseUrl = config.get<string>("backendUrl", "http://127.0.0.1:8000");
  }
  refreshConfig(): void {
    const config = vscode.workspace.getConfiguration("aiCodeAssistant");
    this.baseUrl = config.get<string>("backendUrl", "http://127.0.0.1:8000");
  }
  async checkHealth(): Promise<HealthStatus> {
    const response = await fetchWithTimeout(`${this.baseUrl}/health`, { method: "GET", headers: { Accept: "application/json" } }, 8000);
    if (!response.ok) { throw new Error(`Health check failed: HTTP ${response.status}`); }
    return response.json() as Promise<HealthStatus>;
  }
  async explainCode(code: string, language: string, detailLevel: "brief" | "standard" | "detailed" = "standard", contextBefore = "", contextAfter = ""): Promise<{ explanation: string; improvements: string[] }> {
    const response = await fetchWithTimeout(`${this.baseUrl}/explanation/explain`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, language, detail_level: detailLevel, context_before: contextBefore, context_after: contextAfter }),
    }, 120000);
    if (!response.ok) { const err = await response.json().catch(() => ({})); throw new Error((err as any).detail ?? `Explanation failed: HTTP ${response.status}`); }
    const data = (await response.json()) as { explanation: string; suggested_improvements: string[]; model: string };
    return { explanation: data.explanation, improvements: data.suggested_improvements ?? [] };
  }
  async searchSimilarCode(query: string, topK = 5): Promise<SearchResult[]> {
    const response = await fetchWithTimeout(`${this.baseUrl}/search/similar`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, top_k: topK }),
    }, 15000);
    if (!response.ok) { const err = await response.json().catch(() => ({})); throw new Error((err as any).detail ?? `Search failed: HTTP ${response.status}`); }
    const data = (await response.json()) as { results: SearchResult[] };
    return data.results;
  }
  async indexFiles(files: IndexFilePayload[], fullReindex = false): Promise<IndexResult> {
    const response = await fetchWithTimeout(`${this.baseUrl}/search/index/files`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ files, full_reindex: fullReindex }),
    }, 120000);
    if (!response.ok) { const err = await response.json().catch(() => ({})); throw new Error((err as any).detail ?? `Indexing failed: HTTP ${response.status}`); }
    return response.json() as Promise<IndexResult>;
  }
  async chatMessage(messages: ChatMessage[], activeFileContent?: string, activeFileLanguage?: string): Promise<string> {
    const body: any = { messages, stream: false };
    if (activeFileContent) { body.active_file = { content: activeFileContent, language: activeFileLanguage ?? "unknown" }; }
    const response = await fetchWithTimeout(`${this.baseUrl}/explanation/chat`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }, 60000);
    if (!response.ok) { const err = await response.json().catch(() => ({})); throw new Error((err as any).detail ?? `Chat failed: HTTP ${response.status}`); }
    const data = (await response.json()) as { message: ChatMessage };
    return data.message.content;
  }
  async getCompletion(prefix: string, suffix: string, language: string): Promise<string> {
    const response = await fetchWithTimeout(`${this.baseUrl}/completion/inline`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prefix, suffix, language, n_completions: 1 }),
    }, 20000);
    if (!response.ok) { return ""; }
    const data = (await response.json()) as { choices: Array<{ text: string }> };
    return data.choices?.[0]?.text ?? "";
  }
}
