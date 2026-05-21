/**
 * auth.ts — JWT token discovery
 *
 * code-server is launched by Lab Manager with the user's JWT injected as the
 * environment variable AIBASE_JWT_TOKEN. We read it once at activation; if the
 * user re-authenticates the extension instructs them to reload the window.
 */

import * as vscode from "vscode";

let cachedToken: string | undefined;

/**
 * Returns the JWT used to call /api/v1/* endpoints.
 *
 * Resolution order:
 *   1. SecretStorage (if previously cached)
 *   2. AIBASE_JWT_TOKEN environment variable (injected by Lab Manager)
 *   3. Prompt the user once (fallback for dev / local testing)
 */
export async function getAuthToken(
  context: vscode.ExtensionContext
): Promise<string | undefined> {
  if (cachedToken) {
    return cachedToken;
  }

  const stored = await context.secrets.get("aibase.jwt");
  if (stored) {
    cachedToken = stored;
    return cachedToken;
  }

  const envToken = process.env.AIBASE_JWT_TOKEN;
  if (envToken) {
    cachedToken = envToken;
    await context.secrets.store("aibase.jwt", envToken);
    return cachedToken;
  }

  const entered = await vscode.window.showInputBox({
    title: "AI Base — JWT Token",
    prompt:
      "AIBASE_JWT_TOKEN env var not found. Paste your JWT (you can find it in browser localStorage 'jwt').",
    ignoreFocusOut: true,
    password: true,
  });

  if (entered) {
    cachedToken = entered;
    await context.secrets.store("aibase.jwt", entered);
  }
  return cachedToken;
}

/** Forget the cached token (debug command, currently not exposed). */
export async function clearAuthToken(
  context: vscode.ExtensionContext
): Promise<void> {
  cachedToken = undefined;
  await context.secrets.delete("aibase.jwt");
}
