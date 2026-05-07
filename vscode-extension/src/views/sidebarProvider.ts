const HTML_CONTENT = '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="UTF-8">\n<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; script-src \'unsafe-inline\';">\n<title>AI Code Assistant</title>\n<style>\n*{box-sizing:border-box;margin:0;padding:0}\nbody{font-family:var(--vscode-font-family,system-ui);font-size:13px;color:var(--vscode-foreground);background:var(--vscode-sideBar-background);display:flex;flex-direction:column;height:100vh;overflow:hidden}\n.header{display:flex;align-items:center;justify-content:space-between;padding:8px 10px;border-bottom:1px solid var(--vscode-sideBarSectionHeader-border,#333);flex-shrink:0}\n.header-title{font-weight:600;font-size:11px;text-transform:uppercase;opacity:.8}\n.clear-btn{background:none;border:none;cursor:pointer;color:var(--vscode-foreground);opacity:.6;font-size:11px;padding:2px 6px;border-radius:3px}\n#chat-container{flex:1;overflow-y:auto;padding:10px 8px;display:flex;flex-direction:column;gap:10px}\n.message{max-width:92%;padding:8px 11px;border-radius:10px;line-height:1.5;word-wrap:break-word;white-space:pre-wrap;font-size:12.5px}\n.message.user{align-self:flex-end;background:var(--vscode-button-background,#0e639c);color:var(--vscode-button-foreground,#fff);border-bottom-right-radius:3px}\n.message.assistant{align-self:flex-start;background:var(--vscode-editorWidget-background,#2d2d2d);color:var(--vscode-foreground);border:1px solid var(--vscode-editorWidget-border,#454545);border-bottom-left-radius:3px}\n.message.error{align-self:flex-start;background:#5a1d1d;color:#f48771;border:1px solid #be1100;border-bottom-left-radius:3px}\n.message pre{background:rgba(0,0,0,.3);padding:8px;border-radius:5px;overflow-x:auto;margin:4px 0;white-space:pre}\n.message code{font-family:var(--vscode-editor-font-family,monospace);font-size:11.5px;background:rgba(0,0,0,.3);padding:0 4px;border-radius:3px}\n.message pre code{background:none;padding:0}\n.typing-indicator{align-self:flex-start;display:flex;gap:4px;padding:10px 14px;background:var(--vscode-editorWidget-background,#2d2d2d);border-radius:10px;border:1px solid var(--vscode-editorWidget-border,#454545)}\n.typing-indicator span{width:7px;height:7px;background:var(--vscode-foreground);border-radius:50%;opacity:.4;animation:bounce 1.2s infinite ease-in-out}\n.typing-indicator span:nth-child(2){animation-delay:.2s}.typing-indicator span:nth-child(3){animation-delay:.4s}\n@keyframes bounce{0%,60%,100%{transform:translateY(0);opacity:.4}30%{transform:translateY(-5px);opacity:1}}\n.welcome{align-self:center;text-align:center;opacity:.55;padding:20px 10px;font-size:12px;line-height:1.6}\n.welcome .icon{font-size:28px;margin-bottom:8px}\n.input-area{display:flex;gap:6px;padding:8px;border-top:1px solid var(--vscode-sideBarSectionHeader-border,#333);flex-shrink:0;align-items:flex-end}\n#message-input{flex:1;resize:none;background:var(--vscode-input-background,#3c3c3c);color:var(--vscode-input-foreground,#ccc);border:1px solid var(--vscode-input-border,#3c3c3c);border-radius:5px;padding:7px 9px;font-family:inherit;font-size:12.5px;min-height:36px;max-height:120px;outline:none}\n#message-input:focus{border-color:var(--vscode-focusBorder,#007fd4)}\n#send-btn{background:var(--vscode-button-background,#0e639c);color:var(--vscode-button-foreground,#fff);border:none;border-radius:5px;padding:7px 12px;cursor:pointer;font-size:13px;height:36px;flex-shrink:0}\n#send-btn:disabled{opacity:.5;cursor:not-allowed}\n</style></head><body>\n<div class="header"><span class="header-title">AI Assistant</span><button class="clear-btn" id="clear-btn">Clear</button></div>\n<div id="chat-container"><div class="welcome" id="welcome"><div class="icon">&#x1F916;</div><strong>AI Code Assistant</strong><br>Ask me anything about your code.</div></div>\n<div class="input-area"><textarea id="message-input" placeholder="Ask about your code..." rows="1"></textarea><button id="send-btn">&#x2191;</button></div>\n<script>\nconst vscode=acquireVsCodeApi();\nconst chat=document.getElementById(\'chat-container\');\nconst input=document.getElementById(\'message-input\');\nconst sendBtn=document.getElementById(\'send-btn\');\nconst clearBtn=document.getElementById(\'clear-btn\');\nconst welcome=document.getElementById(\'welcome\');\nlet waiting=false,typingEl=null;\ninput.addEventListener(\'input\',function(){input.style.height=\'auto\';input.style.height=Math.min(input.scrollHeight,120)+\'px\';});\ninput.addEventListener(\'keydown\',function(e){if(e.key===\'Enter\'&&!e.shiftKey){e.preventDefault();send();}});\nsendBtn.addEventListener(\'click\',send);\nclearBtn.addEventListener(\'click\',function(){chat.innerHTML=\'\';chat.appendChild(welcome);welcome.style.display=\'\';vscode.postMessage({type:\'clearChat\'});});\nfunction send(){var t=input.value.trim();if(!t||waiting)return;welcome.style.display=\'none\';addMsg(\'user\',t);showTyping();setWait(true);vscode.postMessage({type:\'sendMessage\',text:t});input.value=\'\';input.style.height=\'auto\';}\nfunction addMsg(r,t){var d=document.createElement(\'div\');d.className=\'message \'+r;if(r===\'assistant\'){d.innerHTML=md(t);}else{d.textContent=t;}chat.appendChild(d);chat.scrollTop=chat.scrollHeight;}\nfunction showTyping(){typingEl=document.createElement(\'div\');typingEl.className=\'typing-indicator\';typingEl.innerHTML=\'<span></span><span></span><span></span>\';chat.appendChild(typingEl);chat.scrollTop=chat.scrollHeight;}\nfunction hideTyping(){if(typingEl){typingEl.remove();typingEl=null;}}\nfunction setWait(w){waiting=w;sendBtn.disabled=w;input.disabled=w;}\nfunction md(t){var s=t.replace(/&/g,\'&amp;\').replace(/</g,\'&lt;\').replace(/>/g,\'&gt;\');s=s.replace(/```[\\w]*\\n?([\\s\\S]*?)```/g,function(m,c){return \'<pre><code>\'+c.trim()+\'</code></pre>\';});s=s.replace(/`([^`]+)`/g,\'<code>$1</code>\');s=s.replace(/\\*\\*(.+?)\\*\\*/g,\'<strong>$1</strong>\');s=s.replace(/\\n/g,\'<br>\');return s;}\nwindow.addEventListener(\'message\',function(e){var m=e.data;if(m.type===\'addMessage\'){hideTyping();setWait(false);addMsg(m.role,m.text);}});\n</script></body></html>';
import * as vscode from "vscode";
import { ApiClient, ChatMessage, languageFromExtension } from "../services/apiClient";

export class ChatViewProvider implements vscode.WebviewViewProvider {
  public static readonly viewType = "ai-code-assistant.chatView";
  private _view?: vscode.WebviewView;
  private _chatHistory: ChatMessage[] = [];

  constructor(private readonly _extensionUri: vscode.Uri, private readonly _apiClient: ApiClient) {}

  resolveWebviewView(webviewView: vscode.WebviewView, _context: vscode.WebviewViewResolveContext, _token: vscode.CancellationToken): void {
    this._view = webviewView;
    webviewView.webview.options = { enableScripts: true, localResourceRoots: [this._extensionUri] };
    webviewView.webview.html = this._getHtmlContent();
    webviewView.webview.onDidReceiveMessage(async (message: any) => {
      if (message.type === "sendMessage") {
        const userText: string = message.text?.trim();
        if (!userText) { return; }
        this._chatHistory.push({ role: "user", content: userText });
        let activeFileContent: string | undefined;
        let activeFileLang: string | undefined;
        const editor = vscode.window.activeTextEditor;
        if (editor) {
          activeFileContent = editor.document.getText();
          const ext = editor.document.fileName.split(".").pop() ?? "";
          activeFileLang = languageFromExtension(ext);
          const lines = activeFileContent.split("\n");
          if (lines.length > 100) { activeFileContent = lines.slice(-100).join("\n"); }
        }
        try {
          const reply = await this._apiClient.chatMessage(this._chatHistory, activeFileContent, activeFileLang);
          this._chatHistory.push({ role: "assistant", content: reply });
          webviewView.webview.postMessage({ type: "addMessage", role: "assistant", text: reply });
        } catch (err: any) {
          webviewView.webview.postMessage({ type: "addMessage", role: "error", text: `Error: ${err.message}` });
          this._chatHistory.pop();
        }
      } else if (message.type === "clearChat") {
        this._chatHistory = [];
      }
    });
  }
  private _getHtmlContent(): string { return HTML_CONTENT; }
}
