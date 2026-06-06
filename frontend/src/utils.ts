type DebugEventType = "verification" | "data_verification" | "report" | "log";

export type DebugEvent = {
  type: string;
  [key: string]: unknown;
};

export type ChatEvent = {
  token: string;
  node: string;
  done: boolean;
  is_final: boolean;
  debug?: DebugEvent | null;
};

export function parseSSEChunk(chunk: string): ChatEvent | null {
  if (!chunk) return null;
  const line = chunk.split("\n").find((l) => l.startsWith("data: "));
  if (!line) return null;
  try {
    return JSON.parse(line.slice(6)) as ChatEvent;
  } catch {
    return null;
  }
}

export function routeDebugEvent(event: DebugEvent): DebugEventType {
  if (event.type === "verification") return "verification";
  if (event.type === "data_verification") return "data_verification";
  if (event.type === "report") return "report";
  return "log";
}
