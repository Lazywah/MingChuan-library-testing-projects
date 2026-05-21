/**
 * sseStream.ts — Server-Sent Events client
 *
 * Streams /api/v1/jobs/{job_id}/stream into a callback. Wraps node-fetch with
 * an AbortController so callers can cancel cleanly.
 *
 * The service layer emits frames like:
 *     data: {"log": "...", "progress": 23.5}
 *     data: {"status": "completed", "progress": 100, "output_path": "/..."}
 *     data: [DONE]
 */

import fetch, { Response } from "node-fetch";

export interface SsePayload {
  log?: string;
  progress?: number;
  status?: string;
  output_path?: string;
  error_message?: string;
}

export interface StreamHandlers {
  onPayload: (data: SsePayload) => void;
  onDone: () => void;
  onError: (err: Error) => void;
}

export class SseStream {
  private controller: AbortController | undefined;

  /**
   * Open a long-lived SSE connection. Returns immediately; events flow to handlers.
   */
  async open(
    url: string,
    token: string,
    handlers: StreamHandlers
  ): Promise<void> {
    this.controller = new AbortController();

    let resp: Response;
    try {
      resp = await fetch(url, {
        method: "GET",
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: "text/event-stream",
          "Cache-Control": "no-cache",
        },
        signal: this.controller.signal as any,
      });
    } catch (e: any) {
      handlers.onError(new Error(`SSE connect failed: ${e?.message ?? e}`));
      return;
    }

    if (!resp.ok) {
      handlers.onError(
        new Error(`SSE HTTP ${resp.status} ${resp.statusText}`)
      );
      return;
    }
    if (!resp.body) {
      handlers.onError(new Error("SSE response has no body"));
      return;
    }

    // node-fetch returns a Node Readable; iterate as bytes and assemble frames.
    let buffer = "";
    try {
      for await (const chunk of resp.body as any as AsyncIterable<Buffer>) {
        buffer += chunk.toString("utf-8");

        // Frames are separated by a blank line.
        let sep: number;
        while ((sep = buffer.indexOf("\n\n")) !== -1) {
          const frame = buffer.slice(0, sep);
          buffer = buffer.slice(sep + 2);
          this.handleFrame(frame, handlers);
        }
      }
      handlers.onDone();
    } catch (e: any) {
      if (this.controller?.signal.aborted) {
        handlers.onDone();
      } else {
        handlers.onError(new Error(`SSE stream error: ${e?.message ?? e}`));
      }
    }
  }

  /** Abort the stream — caller will receive onDone (not onError). */
  close(): void {
    this.controller?.abort();
    this.controller = undefined;
  }

  private handleFrame(frame: string, handlers: StreamHandlers): void {
    // A frame can have multiple `data:` lines; we only handle one per frame.
    const lines = frame.split("\n");
    for (const line of lines) {
      if (!line.startsWith("data:")) continue;
      const payload = line.slice(5).trim();
      if (!payload) continue;
      if (payload === "[DONE]") {
        handlers.onDone();
        return;
      }
      try {
        const parsed: SsePayload = JSON.parse(payload);
        handlers.onPayload(parsed);
      } catch {
        // Service layer may emit plain text frames; treat as log.
        handlers.onPayload({ log: payload });
      }
    }
  }
}
