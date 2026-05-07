import * as vscode from "vscode";
import { ApiClient, languageFromExtension } from "../services/apiClient";

const DEBOUNCE_MS = 600;

export class CompletionProvider implements vscode.InlineCompletionItemProvider {
  private apiClient: ApiClient;
  private debounceTimer: ReturnType<typeof setTimeout> | undefined;
  private lastPrefix = "";
  private lastResult = "";

  constructor(apiClient: ApiClient) { this.apiClient = apiClient; }

  async provideInlineCompletionItems(
    document: vscode.TextDocument, position: vscode.Position,
    _context: vscode.InlineCompletionContext, token: vscode.CancellationToken
  ): Promise<vscode.InlineCompletionList | null> {
    const config = vscode.workspace.getConfiguration("aiCodeAssistant");
    if (!config.get<boolean>("enableInlineCompletion", true)) { return null; }
    const lineText = document.lineAt(position).text.trimEnd();
    if (lineText.trim().length < 3) { return null; }
    const prefix = document.getText(new vscode.Range(new vscode.Position(0, 0), position));
    const suffix = document.getText(new vscode.Range(position, new vscode.Position(document.lineCount, 0)));
    if (prefix === this.lastPrefix && this.lastResult) { return this._makeList(this.lastResult, position); }
    if (this.debounceTimer) { clearTimeout(this.debounceTimer); }
    return new Promise((resolve) => {
      this.debounceTimer = setTimeout(async () => {
        if (token.isCancellationRequested) { resolve(null); return; }
        const ext = document.fileName.split(".").pop() ?? "";
        const language = languageFromExtension(ext);
        try {
          const completion = await this.apiClient.getCompletion(prefix, suffix, language);
          if (!completion || token.isCancellationRequested) { resolve(null); return; }
          this.lastPrefix = prefix; this.lastResult = completion;
          resolve(this._makeList(completion, position));
        } catch { resolve(null); }
      }, DEBOUNCE_MS);
    });
  }
  private _makeList(text: string, position: vscode.Position): vscode.InlineCompletionList {
    const item = new vscode.InlineCompletionItem(text, new vscode.Range(position, position));
    return new vscode.InlineCompletionList([item]);
  }
}
