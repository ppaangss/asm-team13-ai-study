/**
 * SSE 파싱 유틸리티 단위 테스트
 * RED → GREEN → REFACTOR 사이클
 */
import { describe, it, expect } from "vitest";
import { parseSSEChunk, routeDebugEvent } from "./utils";


// ── parseSSEChunk ─────────────────────────────────────────────────────────────

describe("parseSSEChunk", () => {
  it("data: 프리픽스가 있는 SSE 청크를 ChatEvent 객체로 파싱한다", () => {
    const chunk = 'data: {"token":"안녕","node":"investor","done":false,"is_final":false}';
    const event = parseSSEChunk(chunk);
    expect(event).not.toBeNull();
    expect(event?.token).toBe("안녕");
    expect(event?.node).toBe("investor");
    expect(event?.done).toBe(false);
  });

  it("data: 프리픽스가 없는 청크는 null을 반환한다", () => {
    const chunk = 'event: message\n{"token":"test"}';
    expect(parseSSEChunk(chunk)).toBeNull();
  });

  it("빈 문자열은 null을 반환한다", () => {
    expect(parseSSEChunk("")).toBeNull();
  });

  it("멀티라인 SSE 청크에서 data: 줄만 파싱한다", () => {
    const chunk = [
      "id: 1",
      'data: {"token":"토큰","node":"cto","done":false,"is_final":false}',
      "",
    ].join("\n");
    const event = parseSSEChunk(chunk);
    expect(event?.token).toBe("토큰");
    expect(event?.node).toBe("cto");
  });

  it("done:true 이벤트를 올바르게 파싱한다", () => {
    const chunk = 'data: {"token":"","node":"","done":true,"is_final":true}';
    const event = parseSSEChunk(chunk);
    expect(event?.done).toBe(true);
    expect(event?.is_final).toBe(true);
  });

  it("debug 필드가 포함된 이벤트를 파싱한다", () => {
    const debugPayload = {
      token: "",
      node: "dev",
      done: false,
      is_final: false,
      debug: { type: "verification", items: [] },
    };
    const chunk = `data: ${JSON.stringify(debugPayload)}`;
    const event = parseSSEChunk(chunk);
    expect(event?.node).toBe("dev");
    expect(event?.debug?.type).toBe("verification");
  });

  it("JSON이 잘못된 경우 null을 반환한다", () => {
    const chunk = "data: {broken json}";
    expect(parseSSEChunk(chunk)).toBeNull();
  });
});


// ── routeDebugEvent ───────────────────────────────────────────────────────────

describe("routeDebugEvent", () => {
  it("verification 이벤트는 'verification' 라우트를 반환한다", () => {
    const event = { type: "verification" as const, items: [] };
    expect(routeDebugEvent(event)).toBe("verification");
  });

  it("data_verification 이벤트는 'data_verification' 라우트를 반환한다", () => {
    const event = { type: "data_verification" as const, items: [] };
    expect(routeDebugEvent(event)).toBe("data_verification");
  });

  it("report 이벤트는 'report' 라우트를 반환한다", () => {
    const event = {
      type: "report" as const,
      summary: "요약",
      overall_score: 75,
      weaknesses: [],
      closing: "마무리",
    };
    expect(routeDebugEvent(event)).toBe("report");
  });

  it("followup_judge 이벤트는 'log' 라우트를 반환한다", () => {
    const event = {
      type: "followup_judge" as const,
      followup_count: 0,
      score: 55,
      threshold: 30,
      needs_followup: false,
      reason: "충분한 답변",
      question: "질문",
      answer: "답변",
    };
    expect(routeDebugEvent(event)).toBe("log");
  });
});
