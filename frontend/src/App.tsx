import { DragEvent, FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { parseSSEChunk, routeDebugEvent } from "./utils";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  ClipboardCheck,
  FileText,
  Loader2,
  MessageSquareText,
  RefreshCw,
  Send,
  ShieldCheck,
  Sparkles,
  Upload,
} from "lucide-react";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

type Persona = "investor" | "cto" | "mentor" | "reporter" | "user";

type Message = {
  id: string;
  role: "assistant" | "user";
  persona: Persona;
  content: string;
};

type VerificationItem = {
  label: string;
  status: "pass" | "warn" | "fail";
  reason: string;
};

type DataVerificationItem = {
  claim: string;
  status: "confirmed" | "unconfirmed" | "contradicted";
  reason: string;
  source: string;
};

type WeaknessItem = {
  section: string;
  issue: string;
  risk: "상" | "중" | "하";
  risk_score: number;
  suggestion: string;
};

type FinalReport = {
  type: "report";
  summary: string;
  overall_score: number;
  weaknesses: WeaknessItem[];
  closing: string;
};

type VerificationDebug = {
  type: "verification";
  items: VerificationItem[];
};

type DataVerificationDebug = {
  type: "data_verification";
  items: DataVerificationItem[];
};

type FollowupDebug = {
  type: "followup_judge";
  followup_count: number;
  score: number | null;
  threshold: number;
  needs_followup: boolean;
  reason: string;
  question: string;
  answer: string;
  followup_question?: string;
};

type DebugEvent = VerificationDebug | DataVerificationDebug | FollowupDebug | FinalReport;
type InsightTab = "verification" | "answer" | "report" | "log";
type ThresholdMode = "strict" | "normal" | "easy";

const THRESHOLD_MODES: Record<ThresholdMode, { label: string; value: number; hint: string }> = {
  strict: { label: "엄격", value: 60, hint: "꼬리질문 자주" },
  normal: { label: "보통", value: 30, hint: "기본값" },
  easy:   { label: "순함", value: 0,  hint: "꼬리질문 없음" },
};

type ChatEvent = {
  token: string;
  node: Persona | "dev" | "";
  done: boolean;
  is_final: boolean;
  debug?: DebugEvent | null;
};

const PERSONAS: Record<Persona, { label: string; icon: string; className: string }> = {
  investor: { label: "깐깐한 투자자", icon: "💼", className: "persona-investor" },
  cto: { label: "냉철한 CTO", icon: "💻", className: "persona-cto" },
  mentor: { label: "예리한 멘토", icon: "🦉", className: "persona-mentor" },
  reporter: { label: "오케스트레이터", icon: "🤖", className: "persona-reporter" },
  user: { label: "나", icon: "👤", className: "persona-user" },
};

const WORKFLOW_STEPS = [
  { title: "업로드", detail: "파일 준비" },
  { title: "검증", detail: "사전 체크" },
  { title: "심사", detail: "질문 응답" },
  { title: "리포트", detail: "결과 확인" },
] as const;

const SUPPORTED_FILE_EXTENSIONS = [".txt", ".md", ".pdf", ".docx"];

const MOCK_VERIFICATION: VerificationItem[] = [
  {
    label: "문제 구체성",
    status: "pass",
    reason: "대상 사용자와 해결하려는 불편이 명확하게 드러난 것으로 가정했습니다.",
  },
  {
    label: "BM 명확성",
    status: "warn",
    reason: "수익화 방식은 보이지만 가격 정책과 전환율 근거가 더 필요합니다.",
  },
  {
    label: "MVP 범위",
    status: "fail",
    reason: "초기 출시 범위가 넓어 보이며 핵심 기능 우선순위가 필요합니다.",
  },
];

const MOCK_DATA_VERIFICATION: DataVerificationItem[] = [
  {
    claim: "시장 수요가 빠르게 증가하고 있다",
    status: "unconfirmed",
    reason: "데모 모드에서는 외부 검색을 수행하지 않아 출처 확인이 필요합니다.",
    source: "Mock verification",
  },
  {
    claim: "초기 사용자 30명 확보가 가능하다",
    status: "unconfirmed",
    reason: "획득 채널과 전환 가정이 아직 충분히 검증되지 않았습니다.",
    source: "Mock verification",
  },
];

const MOCK_QUESTIONS: Array<{ persona: Exclude<Persona, "user">; content: string }> = [
  {
    persona: "investor",
    content: "초기 유료 전환이 일어난다고 가정했는데, 사용자가 실제로 돈을 낼 만한 순간은 정확히 언제인가요?",
  },
  {
    persona: "cto",
    content: "MVP에서 반드시 구현해야 하는 AI 기능과 나중으로 미뤄도 되는 기능을 어떻게 나눌 건가요?",
  },
  {
    persona: "mentor",
    content: "첫 사용자 30명을 어디서 데려오고, 그들이 남긴 피드백을 어떤 기준으로 제품 결정에 반영할 건가요?",
  },
];

const MOCK_REPORT: FinalReport = {
  type: "report",
  summary: "데모 심사 기준으로는 문제 의식은 보이지만 MVP 범위와 수익화 근거가 아직 약합니다. 발표 전에는 핵심 사용자, 첫 기능, 유료 전환 근거를 더 좁히는 편이 좋습니다.",
  overall_score: 67,
  weaknesses: [
    {
      section: "수익 모델",
      issue: "유료 전환 시점과 가격 근거가 부족합니다.",
      risk: "중",
      risk_score: 68,
      suggestion: "초기 고객 인터뷰나 경쟁 서비스 가격을 기준으로 첫 가격 가설을 제시하세요.",
    },
    {
      section: "MVP 범위",
      issue: "초기 기능이 넓어 개발 리스크가 커질 수 있습니다.",
      risk: "상",
      risk_score: 82,
      suggestion: "첫 검증에 필요한 기능 2~3개만 남기고 나머지는 후순위로 분리하세요.",
    },
  ],
  closing: "지금은 더 많이 보여주기보다 더 정확히 검증하는 쪽이 설득력 있습니다.",
};

function App() {
  const reduceMotion = useReducedMotion();
  const [file, setFile] = useState<File | null>(null);
  const [threadId, setThreadId] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [verificationResults, setVerificationResults] = useState<VerificationItem[]>([]);
  const [dataVerificationResults, setDataVerificationResults] = useState<DataVerificationItem[]>([]);
  const [debugLog, setDebugLog] = useState<DebugEvent[]>([]);
  const [finalReport, setFinalReport] = useState<FinalReport | null>(null);
  const [maxRounds, setMaxRounds] = useState(3);
  const [thresholdMode, setThresholdMode] = useState<ThresholdMode>("normal");
  const [isUploading, setIsUploading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isDone, setIsDone] = useState(false);
  const [isDemoMode, setIsDemoMode] = useState(false);
  const [activePersona, setActivePersona] = useState<Persona>("reporter");
  const [answer, setAnswer] = useState("");
  const [error, setError] = useState("");
  const [activeInsightTab, setActiveInsightTab] = useState<InsightTab>("verification");
  const streamMessageRef = useRef<string | null>(null);
  const demoRoundRef = useRef(0);

  const phase = finalReport || isDone ? 3 : threadId ? 2 : verificationResults.length ? 1 : 0;
  const followupEvents = debugLog.filter(isFollowupDebug);
  const latestFollowup = followupEvents.at(-1) ?? null;

  const verificationCounts = useMemo(() => {
    return verificationResults.reduce(
      (acc, item) => ({ ...acc, [item.status]: acc[item.status] + 1 }),
      { pass: 0, warn: 0, fail: 0 },
    );
  }, [verificationResults]);

  useEffect(() => {
    if (finalReport) {
      setActiveInsightTab("report");
      return;
    }
    if (latestFollowup) {
      setActiveInsightTab("answer");
      return;
    }
    if (verificationResults.length || dataVerificationResults.length) {
      setActiveInsightTab("verification");
    }
  }, [dataVerificationResults.length, finalReport, latestFollowup, verificationResults.length]);

  async function uploadPlan() {
    if (!file) return;
    setError("");
    setIsUploading(true);
    setMessages([]);
    setVerificationResults([]);
    setDataVerificationResults([]);
    setDebugLog([]);
    setFinalReport(null);
    setIsDone(false);
    setIsDemoMode(false);

    try {
      const formData = new FormData();
      formData.append("file", file);
      const response = await fetch(`${API_BASE}/upload`, {
        method: "POST",
        body: formData,
      });
      if (!response.ok) {
        const detail = await readError(response);
        throw new Error(detail || "업로드에 실패했습니다.");
      }
      const data = (await response.json()) as { thread_id: string };
      setThreadId(data.thread_id);
      setActivePersona("reporter");
      setMessages([
        {
          id: crypto.randomUUID(),
          role: "assistant",
          persona: "reporter",
          content: "기획서 파싱이 끝났습니다. 심사위원들이 빈틈을 찾는 중입니다.",
        },
      ]);
      await streamChat("/chat/start", { thread_id: data.thread_id, message: "", max_rounds: maxRounds, followup_threshold: THRESHOLD_MODES[thresholdMode].value });
    } catch (err) {
      const reason = err instanceof Error ? err.message : "백엔드 연결 실패";
      await startDemoReview(file.name, reason);
    } finally {
      setIsUploading(false);
    }
  }

  async function submitAnswer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = answer.trim();
    if (!trimmed || !threadId || isStreaming) return;
    setAnswer("");
    setError("");
    setMessages((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        role: "user",
        persona: "user",
        content: trimmed,
      },
    ]);
    if (isDemoMode) {
      await continueDemoReview(trimmed);
      return;
    }
    await streamChat("/chat", { thread_id: threadId, message: trimmed });
  }

  async function streamChat(path: "/chat/start" | "/chat", body: { thread_id: string; message: string; max_rounds?: number; followup_threshold?: number }) {
    setIsStreaming(true);
    streamMessageRef.current = null;

    try {
      const response = await fetch(`${API_BASE}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!response.ok || !response.body) {
        const detail = await readError(response);
        throw new Error(detail || "스트리밍 연결에 실패했습니다.");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() ?? "";
        for (const chunk of chunks) {
          const event = parseSSEChunk(chunk);
          if (!event) continue;
          handleChatEvent(event as ChatEvent);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "스트리밍 처리 중 오류가 발생했습니다.");
    } finally {
      setIsStreaming(false);
      streamMessageRef.current = null;
    }
  }

  function handleChatEvent(event: ChatEvent) {
    if (event.done) {
      if (event.is_final) setIsDone(true);
      return;
    }

    if (event.node === "dev" && event.debug) {
      handleDebugEvent(event.debug);
      return;
    }

    if (!event.token || !event.node) return;
    const persona = normalizePersona(event.node);
    setActivePersona(persona);
    // ref 읽기/쓰기를 함수형 업데이트 바깥에서 처리 — StrictMode double-invocation 방지
    const existingId = streamMessageRef.current;
    if (existingId) {
      setMessages((prev) =>
        prev.map((message) =>
          message.id === existingId
            ? { ...message, content: message.content + event.token }
            : message,
        )
      );
    } else {
      const id = crypto.randomUUID();
      streamMessageRef.current = id;
      setMessages((prev) => [
        ...prev,
        { id, role: "assistant", persona, content: event.token },
      ]);
    }
  }

  function handleDebugEvent(event: DebugEvent) {
    const route = routeDebugEvent(event);
    if (route === "verification") {
      setVerificationResults((event as VerificationDebug).items);
      return;
    }
    if (route === "data_verification") {
      setDataVerificationResults((event as DataVerificationDebug).items);
      setDebugLog((prev) => [...prev, event]);
      return;
    }
    if (route === "report") {
      setFinalReport(event as FinalReport);
      setIsDone(true);
      setDebugLog((prev) => [...prev, event]);
      return;
    }
    setDebugLog((prev) => [...prev, event]);
  }

  function resetSession() {
    setThreadId("");
    setFile(null);
    setMessages([]);
    setVerificationResults([]);
    setDataVerificationResults([]);
    setDebugLog([]);
    setFinalReport(null);
    setIsDone(false);
    setIsDemoMode(false);
    setError("");
    setAnswer("");
    setActivePersona("reporter");
    setActiveInsightTab("verification");
    demoRoundRef.current = 0;
  }

  async function startDemoReview(fileName: string, reason: string) {
    setIsDemoMode(true);
    setThreadId(`demo-${crypto.randomUUID()}`);
    setActivePersona("reporter");
    setError(`백엔드 연결 없이 데모 모드로 실행 중입니다. 원인: ${reason}`);
    demoRoundRef.current = 0;
    setMessages([
      {
        id: crypto.randomUUID(),
        role: "assistant",
        persona: "reporter",
        content: `${fileName} 파일을 기준으로 데모 심사를 시작합니다. 실제 API 연결 없이 UI 흐름을 확인할 수 있습니다.`,
      },
    ]);
    setVerificationResults(MOCK_VERIFICATION);
    setDataVerificationResults(MOCK_DATA_VERIFICATION);
    setDebugLog([{ type: "data_verification", items: MOCK_DATA_VERIFICATION }]);
    await askNextDemoQuestion();
  }

  async function continueDemoReview(userAnswer: string) {
    const round = demoRoundRef.current;
    setDebugLog((prev) => [
      ...prev,
      {
        type: "followup_judge",
        followup_count: Math.max(0, round - 1),
        score: Math.min(88, 42 + userAnswer.length),
        threshold: round === 1 ? 30 : 15,
        needs_followup: round < MOCK_QUESTIONS.length,
        reason:
          userAnswer.length > 24
            ? "답변에 의도와 근거가 일부 포함되어 다음 관점으로 넘어갑니다."
            : "답변이 짧아 실제 심사에서는 추가 근거 요청이 발생할 수 있습니다.",
        question: messages[messages.length - 1]?.content ?? "",
        answer: userAnswer,
      },
    ]);

    if (demoRoundRef.current < MOCK_QUESTIONS.length) {
      await askNextDemoQuestion();
      return;
    }

    await finishDemoReport();
  }

  async function askNextDemoQuestion() {
    const question = MOCK_QUESTIONS[demoRoundRef.current];
    if (!question) return;
    demoRoundRef.current += 1;
    await streamMockAssistant(question.persona, question.content);
  }

  async function finishDemoReport() {
    setIsStreaming(true);
    await sleep(360);
    setFinalReport(MOCK_REPORT);
    setIsDone(true);
    setDebugLog((prev) => [...prev, MOCK_REPORT]);
    setMessages((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        role: "assistant",
        persona: "reporter",
        content: MOCK_REPORT.summary,
      },
    ]);
    setActivePersona("reporter");
    setIsStreaming(false);
  }

  async function streamMockAssistant(persona: Exclude<Persona, "user">, content: string) {
    setIsStreaming(true);
    setActivePersona(persona);
    const id = crypto.randomUUID();
    setMessages((prev) => [...prev, { id, role: "assistant", persona, content: "" }]);
    for (const token of content.split(/(\s+)/)) {
      await sleep(45);
      setMessages((prev) =>
        prev.map((message) =>
          message.id === id ? { ...message, content: message.content + token } : message,
        ),
      );
    }
    setIsStreaming(false);
  }

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <p className="eyebrow">AI Planning Review</p>
          <h1>기획서 검증 에이전트</h1>
        </div>
        <button className="icon-text-button secondary" onClick={resetSession} type="button">
          <RefreshCw size={16} />
          새 심사
        </button>
      </header>

      <main className="app-shell">
        <section className="main-column">
          <WorkflowStepper current={phase} />

          {!threadId ? (
            <motion.section
              className="upload-workspace"
              initial={reduceMotion ? false : { opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
            >
              <div className="workspace-heading">
                <div>
                  <p className="eyebrow">Upload</p>
                  <h2>기획서를 올리고 모의 심사를 시작하세요</h2>
                </div>
                <ShieldCheck aria-hidden size={28} />
              </div>

              <div className="persona-grid">
                <PersonaCard persona="investor" detail="시장성, 차별화, 수익 모델을 압박합니다." />
                <PersonaCard persona="cto" detail="기술 구현 가능성과 LLM 적정성을 점검합니다." />
                <PersonaCard persona="mentor" detail="문제 정의, PMF, MVP 범위를 좁혀 묻습니다." />
              </div>

              <FileDropzone file={file} isUploading={isUploading} onFile={setFile} onReject={setError} />

              <div className="session-settings">
                <label className="settings-field">
                  <span>최대 질문 수</span>
                  <input
                    type="number"
                    min={1}
                    max={6}
                    value={maxRounds}
                    disabled={isUploading}
                    onChange={(e) => setMaxRounds(Math.min(6, Math.max(1, Number(e.target.value))))}
                  />
                </label>
                <div className="settings-field">
                  <span>꼬리질문 강도</span>
                  <div className="threshold-toggle" role="group" aria-label="꼬리질문 강도 선택">
                    {(Object.keys(THRESHOLD_MODES) as ThresholdMode[]).map((mode) => (
                      <button
                        key={mode}
                        type="button"
                        className={`threshold-option${thresholdMode === mode ? " active" : ""}`}
                        disabled={isUploading}
                        onClick={() => setThresholdMode(mode)}
                      >
                        <strong>{THRESHOLD_MODES[mode].label}</strong>
                        <small>{THRESHOLD_MODES[mode].hint}</small>
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <button className="primary-action" disabled={!file || isUploading} onClick={uploadPlan} type="button">
                {isUploading ? <Loader2 className="spin" size={18} /> : <Upload size={18} />}
                {isUploading ? "업로드 중" : "심사 시작"}
              </button>
            </motion.section>
          ) : (
            <section className="review-workspace">
              <div className="workspace-heading">
                <div>
                  <p className="eyebrow">Review</p>
                  <h2>{isDemoMode ? "데모 심사 진행 중" : "페르소나 심사 진행 중"}</h2>
                </div>
                {isDemoMode && (
                  <div className="heading-actions">
                    <span className="demo-badge">Mock mode</span>
                  </div>
                )}
              </div>

              <ChatTranscript messages={messages} isStreaming={isStreaming} latestFollowup={latestFollowup} />

              <form className="answer-bar" onSubmit={submitAnswer}>
                <label className="sr-only" htmlFor="answer-input">
                  답변 입력
                </label>
                <input
                  id="answer-input"
                  value={answer}
                  onChange={(event) => setAnswer(event.target.value)}
                  placeholder={isDone ? "심사가 완료되었습니다" : "답변을 입력하세요"}
                  disabled={isStreaming || isDone}
                />
                <button className="send-button" disabled={!answer.trim() || isStreaming || isDone} aria-label="답변 보내기">
                  {isStreaming ? <Loader2 className="spin" size={18} /> : <Send size={18} />}
                </button>
              </form>
            </section>
          )}

          <AnimatePresence>
            {error && (
              <motion.div
                className="error-banner"
                initial={reduceMotion ? false : { opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
              >
                <AlertTriangle size={18} />
                {error}
              </motion.div>
            )}
          </AnimatePresence>
        </section>

        <aside className="side-column">
          <InsightPanel
            activeTab={activeInsightTab}
            onTabChange={setActiveInsightTab}
            verificationCounts={verificationCounts}
            verificationResults={verificationResults}
            dataVerificationResults={dataVerificationResults}
            latestFollowup={latestFollowup}
            followupEvents={followupEvents}
            finalReport={finalReport}
            isStreaming={isStreaming}
            isDone={isDone}
          />
        </aside>
      </main>
    </div>
  );
}

function InsightPanel({
  activeTab,
  onTabChange,
  verificationCounts,
  verificationResults,
  dataVerificationResults,
  latestFollowup,
  followupEvents,
  finalReport,
  isStreaming,
  isDone,
}: {
  activeTab: InsightTab;
  onTabChange: (tab: InsightTab) => void;
  verificationCounts: { pass: number; warn: number; fail: number };
  verificationResults: VerificationItem[];
  dataVerificationResults: DataVerificationItem[];
  latestFollowup: FollowupDebug | null;
  followupEvents: FollowupDebug[];
  finalReport: FinalReport | null;
  isStreaming: boolean;
  isDone: boolean;
}) {
  const answerScore = latestFollowup?.score;
  const riskyClaims = dataVerificationResults.filter((item) => item.status !== "confirmed").length;

  return (
    <section className="panel insight-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Insight</p>
          <h3>심사 인사이트</h3>
        </div>
        <BarChart3 size={22} />
      </div>

      <div className="insight-summary">
        <MetricCard label="검증 이슈" value={`${verificationCounts.warn + verificationCounts.fail}`} tone={verificationCounts.fail ? "fail" : verificationCounts.warn ? "warn" : "pass"} />
        <MetricCard label="답변 품질" value={answerScore == null ? "대기" : `${answerScore}`} tone={answerScore != null && answerScore >= 60 ? "pass" : "warn"} />
        <MetricCard label="수치 검증" value={`${riskyClaims}`} tone={riskyClaims ? "warn" : "pass"} />
      </div>

      <div className="insight-tabs" role="tablist" aria-label="심사 인사이트 탭">
        <button className={activeTab === "verification" ? "active" : ""} onClick={() => onTabChange("verification")} type="button">
          검증
        </button>
        <button className={activeTab === "answer" ? "active" : ""} onClick={() => onTabChange("answer")} type="button">
          답변
        </button>
        <button className={activeTab === "report" ? "active" : ""} onClick={() => onTabChange("report")} type="button">
          리포트
        </button>
        <button className={activeTab === "log" ? "active" : ""} onClick={() => onTabChange("log")} type="button">
          로그
        </button>
      </div>

      <div className="insight-scroll">
        {activeTab === "verification" && (
          <VerificationPanel counts={verificationCounts} items={verificationResults} dataItems={dataVerificationResults} />
        )}
        {activeTab === "answer" && <AnswerQualityPanel event={latestFollowup} isStreaming={isStreaming} />}
        {activeTab === "report" &&
          (finalReport ? (
            <ReportPanel report={finalReport} />
          ) : (
            <ProgressPanel isStreaming={isStreaming} isDone={isDone} />
          ))}
        {activeTab === "log" && (
          <section className="panel debug-panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Developer</p>
                <h3>판정 로그</h3>
              </div>
            </div>
            <DebugLog events={followupEvents} />
          </section>
        )}
      </div>
    </section>
  );
}

function FileDropzone({
  file,
  isUploading,
  onFile,
  onReject,
}: {
  file: File | null;
  isUploading: boolean;
  onFile: (file: File | null) => void;
  onReject: (message: string) => void;
}) {
  const [isDragging, setIsDragging] = useState(false);

  function acceptFile(nextFile: File | null) {
    if (!nextFile) return;
    const extension = `.${nextFile.name.split(".").pop()?.toLowerCase() ?? ""}`;
    if (!SUPPORTED_FILE_EXTENSIONS.includes(extension)) {
      onFile(null);
      onReject("TXT, MD, PDF, DOCX 파일만 업로드할 수 있습니다.");
      return;
    }
    onReject("");
    onFile(nextFile);
  }

  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setIsDragging(false);
    if (isUploading) return;
    acceptFile(event.dataTransfer.files[0] ?? null);
  }

  return (
    <label
      className={`file-dropzone ${file ? "has-file" : ""} ${isDragging ? "is-dragging" : ""}`}
      onDragEnter={(event) => {
        event.preventDefault();
        if (!isUploading) setIsDragging(true);
      }}
      onDragOver={(event) => {
        event.preventDefault();
        if (!isUploading) event.dataTransfer.dropEffect = "copy";
      }}
      onDragLeave={(event) => {
        event.preventDefault();
        if (event.currentTarget.contains(event.relatedTarget as Node | null)) return;
        setIsDragging(false);
      }}
      onDrop={handleDrop}
    >
      <input
        type="file"
        accept=".txt,.md,.pdf,.docx"
        disabled={isUploading}
        onChange={(event) => acceptFile(event.target.files?.[0] ?? null)}
      />
      <span className="dropzone-icon">
        {file ? <CheckCircle2 size={28} /> : isDragging ? <Upload size={28} /> : <FileText size={28} />}
      </span>
      <span>{file ? file.name : isDragging ? "여기에 놓으면 파일이 선택됩니다" : "파일을 드래그하거나 클릭해서 선택"}</span>
      <small>{file ? `${formatBytes(file.size)} · 준비 완료` : "TXT, MD, PDF, DOCX 지원"}</small>
    </label>
  );
}

function PersonaCard({ persona, detail }: { persona: Exclude<Persona, "user">; detail: string }) {
  return (
    <article className={`persona-card ${PERSONAS[persona].className}`}>
      <span className="persona-card-icon">{PERSONAS[persona].icon}</span>
      <strong>{PERSONAS[persona].label}</strong>
      <p>{detail}</p>
    </article>
  );
}

function PersonaBadge({ persona }: { persona: Persona }) {
  const item = PERSONAS[persona];
  return (
    <span className={`persona-badge ${item.className}`}>
      <span aria-hidden>{item.icon}</span>
      {item.label}
    </span>
  );
}

function WorkflowStepper({ current }: { current: number }) {
  return (
    <nav className="workflow-stepper" aria-label="심사 단계">
      <div className="stepper-rail" aria-hidden />
      {WORKFLOW_STEPS.map((step, index) => {
        const state = index < current ? "complete" : index === current ? "active" : "pending";
        return (
          <div key={step.title} className={`workflow-step ${state}`}>
            <span className="step-marker">
              {state === "complete" ? <CheckCircle2 size={16} /> : index + 1}
            </span>
            <span className="step-copy">
              <strong>{step.title}</strong>
              <small>{step.detail}</small>
            </span>
          </div>
        );
      })}
    </nav>
  );
}

function ChatTranscript({
  messages,
  isStreaming,
  latestFollowup,
}: {
  messages: Message[];
  isStreaming: boolean;
  latestFollowup: FollowupDebug | null;
}) {
  const lastUserMessageId = [...messages].reverse().find((message) => message.role === "user")?.id;

  return (
    <div className="chat-transcript">
      <AnimatePresence initial={false}>
        {messages.map((message) => (
          <motion.article
            key={message.id}
            className={`chat-message ${message.role === "user" ? "from-user" : "from-assistant"} ${
              PERSONAS[message.persona].className
            }`}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
          >
            {message.role === "assistant" && <PersonaBadge persona={message.persona} />}
            <p>{message.content}</p>
            {latestFollowup && message.id === lastUserMessageId && (
              <AnswerFeedbackChip event={latestFollowup} />
            )}
          </motion.article>
        ))}
      </AnimatePresence>
      {isStreaming && (
        <div className="typing-indicator">
          <Loader2 className="spin" size={15} />
          답변 생성 중
        </div>
      )}
    </div>
  );
}

function AnswerFeedbackChip({ event }: { event: FollowupDebug }) {
  const quality = getAnswerQuality(event.score, event.reason);

  return (
    <motion.div
      className={`answer-feedback-chip insight-${quality.status}`}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
    >
      <span>AI 판정</span>
      <strong>{event.score ?? "?"}</strong>
      <em>{quality.label}</em>
    </motion.div>
  );
}

function VerificationPanel({
  counts,
  items,
  dataItems,
}: {
  counts: { pass: number; warn: number; fail: number };
  items: VerificationItem[];
  dataItems: DataVerificationItem[];
}) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Verification</p>
          <h3>사전 검증</h3>
        </div>
        <ClipboardCheck size={22} />
      </div>

      <div className="status-summary">
        <StatusPill status="pass" label={`통과 ${counts.pass}`} />
        <StatusPill status="warn" label={`주의 ${counts.warn}`} />
        <StatusPill status="fail" label={`미흡 ${counts.fail}`} />
      </div>

      {items.length ? (
        <div className="item-list">
          {items.map((item) => (
            <div className="verification-item" key={item.label}>
              <StatusPill status={item.status} label={statusLabel(item.status)} />
              <strong>{item.label}</strong>
              <p>{item.reason}</p>
            </div>
          ))}
        </div>
      ) : (
        <p className="empty-text">분석이 시작되면 체크리스트 결과가 표시됩니다.</p>
      )}

      <div className="divider" />

      <h4>수치 주장 검증</h4>
      {dataItems.length ? (
        <div className="item-list">
          {dataItems.map((item) => (
            <div className="verification-item" key={item.claim}>
              <StatusPill status={item.status} label={dataStatusLabel(item.status)} />
              <strong>{item.claim}</strong>
              <p>{item.reason}</p>
              <small>{item.source}</small>
            </div>
          ))}
        </div>
      ) : (
        <p className="empty-text">검증 가능한 수치가 발견되면 출처와 함께 표시됩니다.</p>
      )}
    </section>
  );
}

function ProgressPanel({ isStreaming, isDone }: { isStreaming: boolean; isDone: boolean }) {
  return (
    <section className="panel progress-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Session</p>
          <h3>심사 상태</h3>
        </div>
        <MessageSquareText size={22} />
      </div>
      <div className="large-status">
        {isDone ? <CheckCircle2 size={30} /> : isStreaming ? <Loader2 className="spin" size={30} /> : <Sparkles size={30} />}
        <div>
          <strong>{isDone ? "심사 완료" : isStreaming ? "응답 생성 중" : "답변 대기"}</strong>
          <p>{isDone ? "최종 리포트를 확인하세요." : "질문에 답하면 다음 판단으로 이어집니다."}</p>
        </div>
      </div>
    </section>
  );
}

function AnswerQualityPanel({ event, isStreaming }: { event: FollowupDebug | null; isStreaming: boolean }) {
  const score = event?.score ?? null;
  const quality = getAnswerQuality(score, event?.reason);
  const impact = getAnswerImpact(score);

  return (
    <section className="panel answer-quality-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Answer Quality</p>
          <h3>답변 영향력</h3>
        </div>
        <MessageSquareText size={22} />
      </div>

      {event ? (
        <>
          <div className="quality-hero">
            <div className={`quality-score quality-${quality.status}`}>
              <span>{score ?? "?"}</span>
              <small>{score === null ? "측정불가" : "/ 100"}</small>
            </div>
            <div>
              <strong>{quality.label}</strong>
              <p>{quality.description}</p>
            </div>
          </div>

          <div className="quality-meter" aria-label={`답변 품질 점수 ${score ?? 0}`}>
            <span style={{ width: `${score ?? 0}%` }} />
          </div>

          <div className="quality-grid">
            <MetricCard label="임계값" value={`${event.threshold}`} tone={event.needs_followup ? "warn" : "pass"} />
            <MetricCard label="영향력" value={impact} tone={score !== null && score >= event.threshold ? "pass" : "warn"} />
          </div>

          <p className="quality-reason">{event.reason}</p>
          {event.followup_question && (
            <div className="followup-callout">
              <strong>생성된 꼬리질문</strong>
              <p>{event.followup_question}</p>
            </div>
          )}
        </>
      ) : (
        <p className="empty-text">
          {isStreaming ? "답변 품질을 판정하는 중입니다." : "답변을 제출하면 점수와 영향력이 표시됩니다."}
        </p>
      )}
    </section>
  );
}

function ReportPanel({ report }: { report: FinalReport }) {
  return (
    <section className="panel report-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Report</p>
          <h3>최종 리포트</h3>
        </div>
        <BarChart3 size={22} />
      </div>

      <div className="score-block">
        <span>{report.overall_score}</span>
        <div>
          <strong>{getReportGrade(report.overall_score)}</strong>
        </div>
      </div>

      <h4>핵심 취약점</h4>
      <div className="item-list">
        {report.weaknesses.map((weakness) => (
          <article className="weakness-item" key={`${weakness.section}-${weakness.issue}`}>
            <div>
              <strong>{weakness.section}</strong>
              <StatusPill status={riskStatus(weakness.risk)} label={`위험도 ${weakness.risk}`} />
            </div>
            <p>{weakness.issue}</p>
            <div className="safety-meter" aria-label={`섹션 완성도 ${100 - weakness.risk_score}`}>
              <span style={{ width: `${100 - weakness.risk_score}%` }} />
              <em>{100 - weakness.risk_score}</em>
            </div>
            <small>{weakness.suggestion}</small>
          </article>
        ))}
      </div>
    </section>
  );
}

function DebugLog({ events }: { events: FollowupDebug[] }) {
  if (!events.length) {
    return <p className="empty-text">아직 꼬리질문 판정 로그가 없습니다.</p>;
  }
  return (
    <div className="item-list">
      {events.map((event, index) => (
        <article className="debug-item" key={`${event.type}-${index}`}>
          <div>
            <strong>#{index + 1} {event.needs_followup ? "꼬리질문" : "다음 라운드"}</strong>
            <span>{event.score ?? "오류"} / {event.threshold}</span>
          </div>
          <p>{event.reason}</p>
          {event.followup_question && <small>{event.followup_question}</small>}
        </article>
      ))}
    </div>
  );
}

function StatusPill({ status, label }: { status: string; label: string }) {
  return <span className={`status-pill status-${status}`}>{label}</span>;
}

function MetricCard({ label, value, tone }: { label: string; value: string; tone: "pass" | "warn" | "fail" }) {
  return (
    <div className={`metric-card metric-${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function normalizePersona(node: string): Persona {
  if (node === "investor" || node === "cto" || node === "mentor" || node === "reporter") {
    return node;
  }
  return "reporter";
}

function isFollowupDebug(event: DebugEvent): event is FollowupDebug {
  return event.type === "followup_judge";
}

function statusLabel(status: VerificationItem["status"]) {
  return { pass: "통과", warn: "주의", fail: "미흡" }[status];
}

function dataStatusLabel(status: DataVerificationItem["status"]) {
  return { confirmed: "확인", unconfirmed: "불확실", contradicted: "상충" }[status];
}

function riskStatus(risk: WeaknessItem["risk"]) {
  return risk === "상" ? "fail" : risk === "중" ? "warn" : "pass";
}

function getAnswerQuality(score: number | null, reason?: string) {
  if (score === null) {
    const isError = reason?.includes("오류");
    return {
      status: isError ? "fail" : "warn",
      label: isError ? "판정 오류" : "측정 불가",
      description: isError ? "LLM 판정 호출에 문제가 있었습니다." : "점수를 산정할 수 없는 답변입니다.",
    };
  }
  if (score >= 75) {
    return { status: "pass", label: "강한 답변", description: "질문 의도에 대한 근거와 실행 계획이 설득력을 만듭니다." };
  }
  if (score >= 45) {
    return { status: "warn", label: "보완 가능한 답변", description: "핵심 방향은 있으나 수치, 사례, 우선순위가 더 필요합니다." };
  }
  return { status: "fail", label: "약한 답변", description: "질문의 핵심을 충분히 덮지 못해 꼬리질문 가능성이 높습니다." };
}

function getAnswerImpact(score: number | null) {
  if (score === null) return "불명확";
  if (score >= 75) return "높음";
  if (score >= 45) return "중간";
  return "낮음";
}

function getAverageAnswerScore(events: FollowupDebug[]) {
  const scores = events.map((event) => event.score).filter((score): score is number => typeof score === "number");
  if (!scores.length) return null;
  return Math.round(scores.reduce((sum, score) => sum + score, 0) / scores.length);
}

function getReportGrade(score: number) {
  if (score >= 80) return "발표 준비도가 높습니다";
  if (score >= 60) return "핵심 보강 후 설득력이 올라갑니다";
  return "기획 가설 재정리가 필요합니다";
}

function formatBytes(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function readError(response: Response) {
  try {
    const data = await response.json();
    return data.detail ?? data.message ?? response.statusText;
  } catch {
    return response.statusText;
  }
}

export default App;
