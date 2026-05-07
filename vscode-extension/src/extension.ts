import * as path from "path";
import * as vscode from "vscode";
import { ApiClient, languageFromExtension } from "./services/apiClient";
import { CompletionProvider } from "./providers/completionProvider";
import { ChatViewProvider } from "./views/sidebarProvider";

let apiClient: ApiClient;
let statusBarItem: vscode.StatusBarItem;
let healthCheckInterval: ReturnType<typeof setInterval>;

export function activate(context: vscode.ExtensionContext): void {
  apiClient = new ApiClient();
  context.subscriptions.push(vscode.workspace.onDidChangeConfiguration((e: vscode.ConfigurationChangeEvent) => {
    if (e.affectsConfiguration("aiCodeAssistant")) { apiClient.refreshConfig(); }
  }));
  statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  statusBarItem.text = "$(hubot) AI: checking...";
  statusBarItem.tooltip = "AI Code Assistant";
  statusBarItem.command = "ai-code-assistant.openChat";
  statusBarItem.show();
  context.subscriptions.push(statusBarItem);
  context.subscriptions.push(vscode.languages.registerInlineCompletionItemProvider({ pattern: "**" }, new CompletionProvider(apiClient)));
  context.subscriptions.push(vscode.window.registerWebviewViewProvider(ChatViewProvider.viewType, new ChatViewProvider(context.extensionUri, apiClient), { webviewOptions: { retainContextWhenHidden: true } }));

  context.subscriptions.push(vscode.commands.registerCommand("ai-code-assistant.explainCode", async () => {
    const editor = vscode.window.activeTextEditor;
    if (!editor) { vscode.window.showErrorMessage("No active editor."); return; }
    const selectedText = editor.document.getText(editor.selection);
    if (!selectedText.trim()) { vscode.window.showErrorMessage("Please select some code first."); return; }
    const ext = editor.document.fileName.split(".").pop() ?? "";
    const language = languageFromExtension(ext);
    const startLine = Math.max(0, editor.selection.start.line - 5);
    const contextBefore = editor.document.getText(new vscode.Range(startLine, 0, editor.selection.start.line, 0));
    const contextAfter = editor.document.getText(new vscode.Range(editor.selection.end.line + 1, 0, Math.min(editor.selection.end.line + 6, editor.document.lineCount), 0));
    await vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title: "AI is explaining code...", cancellable: false }, async () => {
      try {
        const result = await apiClient.explainCode(selectedText, language, "standard", contextBefore, contextAfter);
        const improvements = result.improvements.length > 0 ? "\n\n## Suggestions\n\n" + result.improvements.map((s: string, i: number) => `${i + 1}. ${s}`).join("\n") : "";
        const content = `# Code Explanation\n\n## Explanation\n\n${result.explanation}${improvements}\n\n---\n\`\`\`${language}\n${selectedText}\n\`\`\`\n`;
        const doc = await vscode.workspace.openTextDocument({ content, language: "markdown" });
        await vscode.window.showTextDocument(doc, { viewColumn: vscode.ViewColumn.Beside, preserveFocus: true });
      } catch (err: any) { vscode.window.showErrorMessage(`Explanation failed: ${err.message}`); }
    });
  }));

  context.subscriptions.push(vscode.commands.registerCommand("ai-code-assistant.searchCode", async () => {
    const editor = vscode.window.activeTextEditor;
    const selectedText = editor?.document.getText(editor.selection) ?? "";
    const query = await vscode.window.showInputBox({ prompt: "Search for similar code", placeHolder: "e.g. function that parses JSON", value: selectedText.trim() || undefined });
    if (!query?.trim()) { return; }
    await vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title: "Searching codebase...", cancellable: false }, async () => {
      try {
        const results = await apiClient.searchSimilarCode(query, 8);
        if (results.length === 0) { vscode.window.showInformationMessage("No similar code found. Try: AI: Index Workspace Files"); return; }
        const items = results.map((r) => ({ label: `$(file-code) ${path.basename(r.filepath)}`, description: `Lines ${r.start_line}-${r.end_line} - ${r.language} - ${(r.score * 100).toFixed(0)}%`, detail: r.content.split("\n").slice(0, 2).join(" | "), result: r }));
        const picked = await vscode.window.showQuickPick(items, { matchOnDescription: true, matchOnDetail: true, placeHolder: `${results.length} results found` });
        if (!picked) { return; }
        try {
          const doc = await vscode.workspace.openTextDocument(vscode.Uri.file(picked.result.filepath));
          const line = Math.max(0, picked.result.start_line - 1);
          await vscode.window.showTextDocument(doc, { selection: new vscode.Range(line, 0, line, 0) });
        } catch { vscode.window.showWarningMessage(`Could not open: ${picked.result.filepath}`); }
      } catch (err: any) { vscode.window.showErrorMessage(`Search failed: ${err.message}`); }
    });
  }));

  context.subscriptions.push(vscode.commands.registerCommand("ai-code-assistant.openChat", async () => {
    await vscode.commands.executeCommand("ai-code-assistant.chatView.focus");
  }));

  context.subscriptions.push(vscode.commands.registerCommand("ai-code-assistant.indexWorkspace", async () => {
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders?.length) { vscode.window.showErrorMessage("No workspace folder open."); return; }
    await vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title: "Indexing workspace...", cancellable: false }, async (progress: vscode.Progress<{ message?: string; increment?: number }>) => {
      try {
        progress.report({ message: "Finding source files..." });
        const files = await vscode.workspace.findFiles("**/*.{py,ts,js,tsx,jsx,java,go,rs,rb,cpp,c,php}", "{**/node_modules/**,**/.git/**,**/dist/**,**/out/**,**/__pycache__/**,**/.venv/**}");
        if (files.length === 0) { vscode.window.showInformationMessage("No source files found."); return; }
        const BATCH = 20;
        let totalIndexed = 0, totalChunks = 0;
        for (let i = 0; i < files.length; i += BATCH) {
          const batch = files.slice(i, i + BATCH);
          const payloads = await Promise.all(batch.map(async (uri: vscode.Uri) => {
            const bytes = await vscode.workspace.fs.readFile(uri);
            const content = Buffer.from(bytes).toString("utf8");
            const ext = uri.fsPath.split(".").pop() ?? "";
            return { filepath: uri.fsPath, content, language: languageFromExtension(ext) };
          }));
          progress.report({ message: `Batch ${Math.floor(i / BATCH) + 1}/${Math.ceil(files.length / BATCH)}...`, increment: (BATCH / files.length) * 100 });
          const result = await apiClient.indexFiles(payloads, false);
          totalIndexed += result.indexed_files; totalChunks += result.total_chunks;
        }
        vscode.window.showInformationMessage(`Indexed ${totalIndexed} files, ${totalChunks} chunks.`);
        updateStatusBar();
      } catch (err: any) { vscode.window.showErrorMessage(`Indexing failed: ${err.message}`); }
    });
  }));

  context.subscriptions.push(vscode.workspace.onDidSaveTextDocument(async (doc: vscode.TextDocument) => {
    const ext = doc.fileName.split(".").pop() ?? "";
    const language = languageFromExtension(ext);
    if (language === "unknown") { return; }
    try { await apiClient.indexFiles([{ filepath: doc.fileName, content: doc.getText(), language }], false); } catch { }
  }));

  updateStatusBar();
  healthCheckInterval = setInterval(updateStatusBar, 60000);
  context.subscriptions.push({ dispose: () => clearInterval(healthCheckInterval) });
  vscode.window.showInformationMessage("AI Code Assistant is ready!");
}

export function deactivate(): void { clearInterval(healthCheckInterval); }

async function updateStatusBar(): Promise<void> {
  try {
    const health = await apiClient.checkHealth();
    if (health.status === "ok") {
      statusBarItem.text = `$(hubot) AI: ready (${health.indexed_chunks} chunks)`;
      statusBarItem.backgroundColor = undefined;
      statusBarItem.tooltip = `${health.ollama_model} - ${health.indexed_chunks} chunks`;
    } else {
      statusBarItem.text = "$(hubot) AI: degraded";
      statusBarItem.backgroundColor = new vscode.ThemeColor("statusBarItem.warningBackground");
      statusBarItem.tooltip = `Ollama: ${health.ollama} | ChromaDB: ${health.chromadb}`;
    }
  } catch {
    statusBarItem.text = "$(hubot) AI: offline";
    statusBarItem.backgroundColor = new vscode.ThemeColor("statusBarItem.errorBackground");
    statusBarItem.tooltip = "Backend unreachable - run: uvicorn app.main:app";
  }
}
