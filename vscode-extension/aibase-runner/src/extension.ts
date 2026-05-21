/**
 * extension.ts — entrypoint for aibase-runner.
 *
 * Wires up:
 *   - Output Channel "AI Base GPU" (live SSE log)
 *   - Status Bar item showing current job / framework / node
 *   - Commands: Run on GPU, Run Selection, Run Notebook Cell, Stop, Pick Node/Framework
 *   - Heartbeat loop posting to /api/v1/lab/heartbeat (default every 5 min)
 */

import * as vscode from "vscode";
import {
  CompiledCell,
  cancelJob,
  compileInlineCode,
  listGpuNodes,
  postHeartbeat,
  submitJob,
} from "./jobRunner";
import { SseStream } from "./sseStream";
import { getAuthToken } from "./auth";

interface ActiveJob {
  jobId: string;
  stream: SseStream;
  startedAt: number;
  jobName: string;
}

let outputChannel: vscode.OutputChannel;
let statusBar: vscode.StatusBarItem;
let activeJob: ActiveJob | undefined;
let heartbeatTimer: NodeJS.Timeout | undefined;

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  outputChannel = vscode.window.createOutputChannel("AI Base GPU");
  statusBar = vscode.window.createStatusBarItem(
    vscode.StatusBarAlignment.Right,
    100
  );
  statusBar.command = "aibase.showOutputPanel";
  refreshStatusBar();
  statusBar.show();

  context.subscriptions.push(
    outputChannel,
    statusBar,
    vscode.commands.registerCommand("aibase.runOnGpu", () =>
      runActiveFile(context)
    ),
    vscode.commands.registerCommand("aibase.runSelectionOnGpu", () =>
      runActiveSelection(context)
    ),
    vscode.commands.registerCommand("aibase.runNotebookCellOnGpu", (cell) =>
      runNotebookCell(context, cell)
    ),
    vscode.commands.registerCommand("aibase.stopCurrentJob", () =>
      stopCurrentJob(context)
    ),
    vscode.commands.registerCommand("aibase.pickGpuNode", () =>
      pickGpuNode(context)
    ),
    vscode.commands.registerCommand("aibase.pickFramework", () =>
      pickFramework()
    ),
    vscode.commands.registerCommand("aibase.showOutputPanel", () =>
      outputChannel.show(true)
    ),
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (
        e.affectsConfiguration("aibase.framework") ||
        e.affectsConfiguration("aibase.preferredNode") ||
        e.affectsConfiguration("aibase.heartbeatIntervalSeconds")
      ) {
        refreshStatusBar();
        scheduleHeartbeat(context);
      }
    })
  );

  scheduleHeartbeat(context);

  outputChannel.appendLine(
    `[aibase-runner] activated — framework=${getConfig<string>(
      "framework"
    )} node=${getConfig<string>("preferredNode")}`
  );
}

export function deactivate(): void {
  if (heartbeatTimer) clearInterval(heartbeatTimer);
  activeJob?.stream.close();
}

// ────────────────────────────────────────────────────────────────────────────
// Command handlers
// ────────────────────────────────────────────────────────────────────────────

async function runActiveFile(context: vscode.ExtensionContext): Promise<void> {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    vscode.window.showWarningMessage("AI Base: no active editor.");
    return;
  }
  const text = editor.document.getText();
  const kind = guessCellKind(editor.document.languageId);
  const jobName = `file:${editor.document.fileName.split(/[\\/]/).pop()}`;
  await runCells(context, [{ kind, content: text }], jobName);
}

async function runActiveSelection(
  context: vscode.ExtensionContext
): Promise<void> {
  const editor = vscode.window.activeTextEditor;
  if (!editor || editor.selection.isEmpty) {
    vscode.window.showWarningMessage("AI Base: no selection.");
    return;
  }
  const text = editor.document.getText(editor.selection);
  const kind = guessCellKind(editor.document.languageId);
  await runCells(context, [{ kind, content: text }], "selection");
}

async function runNotebookCell(
  context: vscode.ExtensionContext,
  cell: vscode.NotebookCell | undefined
): Promise<void> {
  // VS Code passes the cell when invoked from the cell title bar; otherwise
  // fall back to the focused notebook cell.
  if (!cell) {
    const editor = vscode.window.activeNotebookEditor;
    if (!editor) {
      vscode.window.showWarningMessage("AI Base: no active notebook.");
      return;
    }
    const sel = editor.selection;
    cell = editor.notebook.cellAt(sel.start);
  }
  if (!cell) return;

  let kind: CompiledCell["kind"] = "code";
  if (cell.kind === vscode.NotebookCellKind.Markup) {
    kind = "markdown";
  } else if (cell.document.languageId === "shellscript") {
    kind = "shell";
  }
  const content = cell.document.getText();
  if (!content.trim()) {
    vscode.window.showInformationMessage("AI Base: cell is empty.");
    return;
  }
  await runCells(context, [{ kind, content }], `cell:${cell.index + 1}`);
}

async function stopCurrentJob(
  context: vscode.ExtensionContext
): Promise<void> {
  if (!activeJob) {
    vscode.window.showInformationMessage("AI Base: no active job.");
    return;
  }
  const token = await getAuthToken(context);
  if (!token) return;

  const { jobId } = activeJob;
  activeJob.stream.close();
  try {
    await cancelJob(getConfig<string>("serviceLayerUrl"), token, jobId);
    outputChannel.appendLine(`[aibase-runner] cancelled job ${jobId}`);
  } catch (e: any) {
    outputChannel.appendLine(`[aibase-runner] cancel failed: ${e.message}`);
  }
  activeJob = undefined;
  refreshStatusBar();
}

async function pickGpuNode(context: vscode.ExtensionContext): Promise<void> {
  const token = await getAuthToken(context);
  if (!token) return;
  const nodes = await listGpuNodes(
    getConfig<string>("serviceLayerUrl"),
    token
  );
  const items: vscode.QuickPickItem[] = [
    {
      label: "auto",
      description: "Let the scheduler pick (recommended)",
    },
    ...nodes.map((n) => ({
      label: n.node_id,
      description: `${n.available_gpus.length} GPU free · util ${n.gpu_utilization}% · ${n.pool_type ?? "batch"}`,
    })),
  ];
  const picked = await vscode.window.showQuickPick(items, {
    placeHolder: "Pick a GPU node",
  });
  if (!picked) return;
  await vscode.workspace
    .getConfiguration("aibase")
    .update("preferredNode", picked.label, vscode.ConfigurationTarget.Global);
}

async function pickFramework(): Promise<void> {
  const schema = vscode.workspace.getConfiguration("aibase").inspect("framework");
  const values: string[] = (schema as any)?.defaultValue
    ? // Pull enum from the JSON schema via the configuration’s description
      [
        "aibase/pytorch:2026-spring",
        "aibase/pytorch-legacy:2026-spring",
        "aibase/tensorflow:2026-spring",
        "aibase/huggingface:2026-spring",
        "aibase/llamacpp:2026-spring",
        "aibase/vllm:2026-spring",
        "aibase/dev-tools:2026-spring",
      ]
    : [];
  const picked = await vscode.window.showQuickPick(values, {
    placeHolder: "Pick a framework image",
  });
  if (!picked) return;
  await vscode.workspace
    .getConfiguration("aibase")
    .update("framework", picked, vscode.ConfigurationTarget.Global);
}

// ────────────────────────────────────────────────────────────────────────────
// Job execution path
// ────────────────────────────────────────────────────────────────────────────

async function runCells(
  context: vscode.ExtensionContext,
  cells: CompiledCell[],
  jobName: string
): Promise<void> {
  if (activeJob) {
    const choice = await vscode.window.showWarningMessage(
      `A job (${activeJob.jobName}) is still running. Stop it first?`,
      "Stop & run new",
      "Cancel"
    );
    if (choice !== "Stop & run new") return;
    await stopCurrentJob(context);
  }

  const token = await getAuthToken(context);
  if (!token) {
    vscode.window.showErrorMessage(
      "AI Base: no JWT token available. Set AIBASE_JWT_TOKEN or paste one when prompted."
    );
    return;
  }

  const serviceLayerUrl = getConfig<string>("serviceLayerUrl");
  const dockerImage = getConfig<string>("framework");
  const preferredNode = getConfig<string>("preferredNode");

  outputChannel.show(true);
  outputChannel.appendLine(
    `\n────────────────────────────────────────────────────────────`
  );
  outputChannel.appendLine(
    `[aibase-runner] submitting ${jobName} → ${dockerImage} (node=${preferredNode})`
  );
  outputChannel.appendLine(
    `--- compiled script preview (${
      compileInlineCode(cells).split("\n").length
    } lines) ---`
  );

  let submission;
  try {
    submission = await submitJob({
      serviceLayerUrl,
      token,
      jobName,
      dockerImage,
      preferredNode,
      cells,
    });
  } catch (e: any) {
    outputChannel.appendLine(`[aibase-runner] submit failed: ${e.message}`);
    vscode.window.showErrorMessage(`AI Base submit failed: ${e.message}`);
    return;
  }

  const jobId = submission.job_id;
  outputChannel.appendLine(
    `[aibase-runner] job_id=${jobId} status=${submission.status} — streaming…`
  );

  const stream = new SseStream();
  activeJob = {
    jobId,
    stream,
    startedAt: Date.now(),
    jobName,
  };
  refreshStatusBar();

  stream
    .open(
      `${serviceLayerUrl.replace(/\/$/, "")}/api/v1/jobs/${jobId}/stream`,
      token,
      {
        onPayload: (data) => {
          if (data.log) outputChannel.appendLine(data.log);
          if (typeof data.progress === "number") {
            updateStatusBarProgress(data.progress);
          }
          if (data.status && ["completed", "failed", "cancelled"].includes(data.status)) {
            outputChannel.appendLine(
              `[aibase-runner] job ${jobId} → ${data.status}` +
                (data.error_message ? ` (${data.error_message})` : "") +
                (data.output_path ? ` output=${data.output_path}` : "")
            );
          }
        },
        onDone: () => {
          outputChannel.appendLine(`[aibase-runner] stream closed for ${jobId}`);
          activeJob = undefined;
          refreshStatusBar();
        },
        onError: (err) => {
          outputChannel.appendLine(`[aibase-runner] stream error: ${err.message}`);
          activeJob = undefined;
          refreshStatusBar();
        },
      }
    )
    .catch((e: any) => {
      outputChannel.appendLine(`[aibase-runner] stream crashed: ${e.message}`);
      activeJob = undefined;
      refreshStatusBar();
    });
}

// ────────────────────────────────────────────────────────────────────────────
// Status bar
// ────────────────────────────────────────────────────────────────────────────

function refreshStatusBar(): void {
  const framework = (getConfig<string>("framework") || "").split("/").pop() ?? "?";
  const node = getConfig<string>("preferredNode");
  if (activeJob) {
    const elapsed = Math.round((Date.now() - activeJob.startedAt) / 1000);
    statusBar.text = `$(sync~spin) AI Base · ${activeJob.jobName} · ${elapsed}s`;
    statusBar.tooltip = `Job ${activeJob.jobId} running on ${node}\nClick to open output panel`;
  } else {
    statusBar.text = `$(rocket) AI Base · ${framework} · ${node}`;
    statusBar.tooltip = "Click to open output panel";
  }
}

function updateStatusBarProgress(progress: number): void {
  if (!activeJob) return;
  const pct = Math.round(progress);
  statusBar.text = `$(sync~spin) AI Base · ${activeJob.jobName} · ${pct}%`;
}

// ────────────────────────────────────────────────────────────────────────────
// Heartbeat
// ────────────────────────────────────────────────────────────────────────────

function scheduleHeartbeat(context: vscode.ExtensionContext): void {
  if (heartbeatTimer) clearInterval(heartbeatTimer);
  const seconds = Math.max(60, getConfig<number>("heartbeatIntervalSeconds") || 300);
  heartbeatTimer = setInterval(async () => {
    const token = await getAuthToken(context);
    if (!token) return;
    await postHeartbeat(getConfig<string>("serviceLayerUrl"), token);
  }, seconds * 1000);
}

// ────────────────────────────────────────────────────────────────────────────
// Helpers
// ────────────────────────────────────────────────────────────────────────────

function getConfig<T>(key: string): T {
  return vscode.workspace.getConfiguration("aibase").get<T>(key) as T;
}

function guessCellKind(languageId: string): CompiledCell["kind"] {
  if (languageId === "shellscript") return "shell";
  if (languageId === "markdown") return "markdown";
  return "code";
}
