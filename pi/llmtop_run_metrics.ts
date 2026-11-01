/* llmtop 2.1.0 – globale Pi-Erweiterung für datensparsame Run-Metriken.
 * Installation: nach ~/.pi/agent/extensions/ kopieren und Pi neu starten oder /reload.
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { randomUUID } from "node:crypto";

type Run = {
  run_id: string;
  model: string;
  provider: string;
  started_at: string;
  heartbeat?: ReturnType<typeof setInterval>;
};

const url = process.env.LLMTOP_COLLECTOR_URL?.replace(/\/$/, "");
const token = process.env.LLMTOP_COLLECTOR_TOKEN;
const active: Run[] = [];

function now(): string {
  return new Date().toISOString();
}

function text(value: unknown, fallback: string): string {
  return typeof value === "string" && value ? value.slice(0, 120) : fallback;
}

function number(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : undefined;
}

function eventRun(run: Run): Omit<Run, "heartbeat"> {
  const { heartbeat: _heartbeat, ...event } = run;
  return event;
}

function usageMetrics(message: any): Record<string, number> {
  const usage = message?.usage;
  if (!usage || typeof usage !== "object") return {};
  const result: Record<string, number> = {};
  const aliases: Array<[string, string]> = [
    ["input", "prompt_tokens"], ["inputTokens", "prompt_tokens"], ["input_tokens", "prompt_tokens"], ["promptTokens", "prompt_tokens"],
    ["output", "output_tokens"], ["outputTokens", "output_tokens"], ["output_tokens", "output_tokens"], ["completionTokens", "output_tokens"],
    ["totalTokens", "context_tokens"], ["total_tokens", "context_tokens"],
  ];
  for (const [from, to] of aliases) {
    const value = number(usage[from]);
    if (value !== undefined) result[to] = value;
  }
  return result;
}

function send(event: Record<string, unknown>): void {
  if (!url || !token) return;
  void fetch(url + "/v1/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: "Bearer " + token },
    body: JSON.stringify(event),
    signal: AbortSignal.timeout(500),
  }).catch(() => undefined);
}

export default function (pi: ExtensionAPI) {
  pi.on("turn_start", (_event, ctx) => {
    const model = ctx.model as any;
    const run: Run = {
      run_id: randomUUID(),
      model: text(model?.id, "unknown"),
      provider: text(model?.provider, "unknown"),
      started_at: now(),
    };
    active.push(run);
    send({ schema: 2, event: "started", source: "pi", ...eventRun(run), updated_at: run.started_at });
    // Lange Cloud- oder lokale Turns dürfen nicht am Collector-Stale-Timeout verschwinden.
    run.heartbeat = setInterval(() => send({ schema: 2, event: "updated", source: "pi",
      ...eventRun(run), updated_at: now() }), 30_000);
  });

  pi.on("turn_end", (event: any) => {
    const run = active.shift();
    if (!run) return;
    if (run.heartbeat) clearInterval(run.heartbeat);
    const finished_at = now();
    const stop = text(event?.message?.stopReason, "completed");
    send({
      schema: 2,
      event: stop === "error" ? "error" : stop === "aborted" ? "cancelled" : "completed",
      source: "pi",
      ...eventRun(run),
      updated_at: finished_at,
      finished_at,
      ...usageMetrics(event?.message),
    });
  });

  pi.on("agent_settled", (event: any) => {
    if (!event?.aborted) return;
    const finished_at = now();
    while (active.length) {
      const run = active.shift()!;
      if (run.heartbeat) clearInterval(run.heartbeat);
      send({ schema: 2, event: "cancelled", source: "pi", ...eventRun(run),
        updated_at: finished_at, finished_at });
    }
  });

  pi.on("session_shutdown", () => {
    const finished_at = now();
    while (active.length) {
      const run = active.shift()!;
      if (run.heartbeat) clearInterval(run.heartbeat);
      send({ schema: 2, event: "cancelled", source: "pi", ...eventRun(run),
        updated_at: finished_at, finished_at });
    }
  });
}
