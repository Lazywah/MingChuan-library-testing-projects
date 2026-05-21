/**
 * jobRunner.ts — Compile cell/file/selection into inline_code and submit Job.
 *
 * The service layer's worker compiles inline_code via `bash -eu /job_code/run.sh`,
 * so we wrap Python content in a heredoc and shell content inline (matching the
 * v1 compile_notebook behaviour).
 */

import fetch from "node-fetch";

export type CellKind = "code" | "shell" | "markdown";

export interface CompiledCell {
  kind: CellKind;
  content: string;
}

export interface JobSubmitOptions {
  serviceLayerUrl: string;
  token: string;
  jobName: string;
  dockerImage: string;
  preferredNode: string; // 'auto' or node_id
  cells: CompiledCell[];
}

export interface JobSubmitResponse {
  job_id: string;
  status: string;
}

/**
 * Compile a list of cells into a single shell script. code cells use a Python
 * heredoc; shell cells are appended inline.
 */
export function compileInlineCode(cells: CompiledCell[]): string {
  const lines: string[] = ["#!/bin/bash", "set -eu", ""];

  cells.forEach((cell, idx) => {
    if (cell.kind === "markdown") return;
    lines.push(`# ---- cell ${idx + 1} (${cell.kind}) ----`);

    if (cell.kind === "code") {
      lines.push("python3 -u - <<'__AIBASE_PYEOF__'");
      lines.push(cell.content);
      lines.push("__AIBASE_PYEOF__");
    } else {
      // shell
      lines.push(cell.content);
    }
    lines.push("");
  });

  return lines.join("\n");
}

/**
 * Submit a Job; returns the new job_id. Authentication uses the user JWT.
 */
export async function submitJob(
  opts: JobSubmitOptions
): Promise<JobSubmitResponse> {
  const inlineCode = compileInlineCode(opts.cells);

  const payload = {
    job_name: opts.jobName,
    model_name: "aibase-runner",
    gpu_required: 1,
    priority: 1,
    docker_image: opts.dockerImage,
    inline_code: inlineCode,
    preferred_node: opts.preferredNode === "auto" ? null : opts.preferredNode,
  };

  const url = `${opts.serviceLayerUrl.replace(/\/$/, "")}/api/v1/jobs`;
  const resp = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${opts.token}`,
    },
    body: JSON.stringify(payload),
  });

  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Submit failed: HTTP ${resp.status} — ${text.slice(0, 200)}`);
  }
  return (await resp.json()) as JobSubmitResponse;
}

/**
 * Cancel a running job. Best-effort; ignores 404 (already done).
 */
export async function cancelJob(
  serviceLayerUrl: string,
  token: string,
  jobId: string
): Promise<void> {
  const url = `${serviceLayerUrl.replace(/\/$/, "")}/api/v1/jobs/${jobId}`;
  const resp = await fetch(url, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!resp.ok && resp.status !== 404) {
    const text = await resp.text();
    throw new Error(`Cancel failed: HTTP ${resp.status} — ${text.slice(0, 200)}`);
  }
}

export interface GpuNode {
  node_id: string;
  available_gpus: string[];
  gpu_utilization: number;
  pool_type?: string;
}

export async function listGpuNodes(
  serviceLayerUrl: string,
  token: string
): Promise<GpuNode[]> {
  const url = `${serviceLayerUrl.replace(/\/$/, "")}/api/v1/lab/nodes`;
  const resp = await fetch(url, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!resp.ok) return [];
  return (await resp.json()) as GpuNode[];
}

export async function postHeartbeat(
  serviceLayerUrl: string,
  token: string
): Promise<void> {
  const url = `${serviceLayerUrl.replace(/\/$/, "")}/api/v1/lab/heartbeat`;
  try {
    await fetch(url, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {
    // Best-effort; lab manager re-evicts if heartbeats stop, no harm in skipping.
  }
}
