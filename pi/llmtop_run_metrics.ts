/* llmtop 2.2.16 – globale Pi-Erweiterung für datensparsame Run-Metriken.
 * Installation: nach ~/.pi/agent/extensions/ kopieren und Pi neu starten oder /reload.
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

type Run = {
  run_id: string;
  model: string;
  provider: string;
  started_at: string;
  session_id?: string;
  context_limit?: number;
  metrics: Record<string, number>;
  context_reader?: () => number | undefined;
  last_progress_at?: number;
  heartbeat?: ReturnType<typeof setInterval>;
};

function collectorConfig(): { url?: string; token?: string } {
  const url = process.env.LLMTOP_COLLECTOR_URL?.replace(/\/$/, "");
  const token = process.env.LLMTOP_COLLECTOR_TOKEN;
  if (url && token) return { url, token };
  try {
    const stateHome = process.env.XDG_STATE_HOME || join(homedir(), ".local", "state");
    const state = JSON.parse(readFileSync(join(stateHome, "llmtop", "pi-collector.json"), "utf8"));
    return { url: typeof state.collector_url === "string" ? state.collector_url.replace(/\/$/, "") : undefined,
      token: typeof state.collector_token === "string" ? state.collector_token : undefined };
  } catch {
    return {};
  }
}

const collector = collectorConfig();
// Ein Agentenlauf umfasst alle Modellturns einer Nutzeranfrage in einer Pi-Session.
let active: Run | undefined;
let currentSessionId: string | undefined;

function now(): string {
  return new Date().toISOString();
}

function text(value: unknown, fallback: string): string {
  return typeof value === "string" && value ? value.slice(0, 120) : fallback;
}

function optionalText(value: unknown): string | undefined {
  return typeof value === "string" && value ? value.slice(0, 120) : undefined;
}

function sessionId(sessionManager: any): string | undefined {
  try {
    const direct = optionalText(sessionManager?.getSessionId?.());
    if (direct) return direct;
    const header = sessionManager?.getHeader?.();
    const headerId = optionalText(header?.id);
    if (headerId) return headerId;
    const sessionFile = optionalText(sessionManager?.getSessionFile?.());
    const match = sessionFile?.match(/_([A-Za-z0-9][A-Za-z0-9._-]*)\.jsonl$/);
    return match?.[1];
  } catch {
    return undefined;
  }
}

function number(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : undefined;
}

function eventRun(run: Run): Omit<Run, "heartbeat" | "metrics" | "context_reader"> {
  const { heartbeat: _heartbeat, metrics: _metrics, context_reader: _context_reader, ...event } = run;
  return event;
}

function contentTokens(content: any): number {
  if (typeof content === "string") return Math.ceil(content.length / 3.5);
  if (!Array.isArray(content)) return 0;
  return content.reduce((total, block) => {
    if (block?.type === "text") return total + Math.ceil(String(block.text || "").length / 3.5);
    if (block?.type === "thinking") return total + Math.ceil(String(block.thinking || "").length / 3.5);
    if (block?.type === "toolCall") return total + Math.ceil((String(block.name || "").length + JSON.stringify(block.arguments || {}).length) / 3.5);
    if (block?.type === "image") return total + 1200;
    return total;
  }, 0);
}

function messageTokens(message: any): number {
  if (!message || typeof message !== "object") return 0;
  if (message.role === "assistant" && message.usage) {
    const usage = message.usage;
    const exact = number(usage.totalTokens);
    if (exact !== undefined && exact > 0) return exact;
    const input = number(usage.input) || 0;
    const output = number(usage.output) || 0;
    const cacheRead = number(usage.cacheRead) || 0;
    const cacheWrite = number(usage.cacheWrite) || 0;
    if (input + output + cacheRead + cacheWrite > 0) return input + output + cacheRead + cacheWrite;
  }
  return contentTokens(message.content);
}

function sessionContextTokens(sessionManager: any): number | undefined {
  try {
    const projection = sessionManager?.buildSessionProjection?.();
    const messages = Array.isArray(projection?.messages) ? projection.messages : [];
    if (!messages.length) return 0;
    let latestUsageIndex = -1;
    let exactTokens = 0;
    for (let index = 0; index < messages.length; index++) {
      const message = messages[index];
      if (message?.role !== "assistant" || !message.usage) continue;
      const tokens = messageTokens(message);
      if (tokens > 0) {
        latestUsageIndex = index;
        exactTokens = tokens;
      }
    }
    if (latestUsageIndex >= 0) {
      return exactTokens + messages.slice(latestUsageIndex + 1).reduce(
        (total: number, message: any) => total + contentTokens(message?.content), 0);
    }
    return messages.reduce((total: number, message: any) => total + messageTokens(message), 0);
  } catch {
    return undefined;
  }
}

function usageMetrics(message: any): Record<string, number> {
  const usage = message?.usage;
  if (!usage || typeof usage !== "object") return {};
  const result: Record<string, number> = {};
  const first = (...names: string[]): number | undefined => {
    for (const name of names) {
      const value = number(usage[name]);
      if (value !== undefined) return value;
    }
    return undefined;
  };
  const input = first("input", "inputTokens", "input_tokens", "promptTokens", "prompt_tokens") || 0;
  const cacheRead = first("cacheRead", "cache_read", "cacheReadTokens", "cache_read_tokens") || 0;
  const output = first("output", "outputTokens", "output_tokens", "completionTokens", "completion_tokens") || 0;
  if (input || cacheRead || output || first("input", "inputTokens", "input_tokens", "promptTokens", "prompt_tokens") === 0) {
    // Pi trennt normalen Input und Cache-Reads; für den Kontextverbrauch zählen beide.
    result.prompt_tokens = input + cacheRead;
  }
  if (output || first("output", "outputTokens", "output_tokens", "completionTokens", "completion_tokens") === 0) {
    result.output_tokens = output;
  }
  if (result.prompt_tokens !== undefined && result.output_tokens !== undefined) {
    result.context_tokens = result.prompt_tokens + result.output_tokens;
  }
  return result;
}

function send(event: Record<string, unknown>): void {
  if (!collector.url || !collector.token) return;
  void fetch(collector.url + "/v1/runs/pi", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: "Bearer " + collector.token },
    body: JSON.stringify(event),
    signal: AbortSignal.timeout(500),
  }).catch(() => undefined);
}

export default function (pi: ExtensionAPI) {
  pi.on("session_start", (_event, ctx) => {
    currentSessionId = sessionId(ctx.sessionManager);
  });

  const progress = (run: Run, force = false) => {
    const current = Date.now();
    const contextTokens = run.context_reader?.();
    if (contextTokens !== undefined) run.metrics.context_tokens = contextTokens;
    if (!force && run.last_progress_at !== undefined && current - run.last_progress_at < 1000) return;
    run.last_progress_at = current;
    const duration = Math.max(0, (current - Date.parse(run.started_at)) / 1000);
    const metrics = { ...run.metrics, total_duration_s: duration };
    if (metrics.output_tokens !== undefined && duration > 0) metrics.eval_duration_s = duration;
    send({ schema: 2, event: "updated", source: "pi", ...eventRun(run),
      updated_at: now(), ...metrics });
  };

  const finish = (event: "completed" | "cancelled" | "error") => {
    const run = active;
    if (!run) return;
    active = undefined;
    if (run.heartbeat) clearInterval(run.heartbeat);
    const finished_at = now();
    const duration = Math.max(0, (Date.parse(finished_at) - Date.parse(run.started_at)) / 1000);
    const metrics = { ...run.metrics, total_duration_s: duration };
    if (metrics.output_tokens !== undefined && duration > 0) metrics.eval_duration_s = duration;
    send({ schema: 2, event, source: "pi", ...eventRun(run),
      updated_at: finished_at, finished_at, ...metrics });
  };

  pi.on("agent_start", (_event, ctx) => {
    // Ein vorheriger, nicht sauber beendeter Agentenlauf darf nicht verwaisen.
    finish("cancelled");
    const model = ctx.model as any;
    currentSessionId = sessionId(ctx.sessionManager) || currentSessionId;
    const run: Run = {
      run_id: randomUUID(),
      model: text(model?.id, "unknown"),
      provider: text(model?.provider, "unknown"),
      started_at: now(),
      ...(currentSessionId ? { session_id: currentSessionId } : {}),
      context_limit: number(model?.contextWindow ?? model?.context_window),
      metrics: {},
      context_reader: () => sessionContextTokens(ctx.sessionManager),
    };
    active = run;
    send({ schema: 2, event: "started", source: "pi", ...eventRun(run), updated_at: run.started_at });
    // Lange Cloud- oder lokale Agentenläufe dürfen nicht am Collector-Stale-Timeout verschwinden.
    // Session-Kontext kann sich auch ohne neue Provider-Usage durch Tool- und
    // Folgeturns ändern. Ein kurzer Takt hält die Anzeige aktuell.
    run.heartbeat = setInterval(() => progress(run, true), 1000);
  });

  pi.on("message_update", (event: any) => {
    if (!active) return;
    const metrics = usageMetrics(event?.message);
    if (Object.keys(metrics).length) active.metrics = { ...active.metrics, ...metrics };
    progress(active);
  });

  pi.on("turn_end", (event: any) => {
    if (!active) return;
    // Nur die jeweils letzte Modellantwort zählt: Bei agent_settled ist dies
    // die sichtbare Abschlussantwort, nicht ein interner Tool-Folgeturn.
    const metrics = usageMetrics(event?.message);
    if (Object.keys(metrics).length) active.metrics = { ...active.metrics, ...metrics };
    progress(active, true);
  });

  pi.on("agent_settled", (event: any) => {
    finish(event?.aborted ? "cancelled" : "completed");
  });

  pi.on("session_shutdown", () => finish("cancelled"));
}
