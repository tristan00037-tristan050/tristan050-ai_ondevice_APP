/**
 * CS HUD
 * R8-S1: 레이아웃과 네비게이션만 구성
 * R9-S1: CS 티켓 리스트 API 연동
 */

import React, { useState, useEffect, useMemo, useRef } from "react";
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  FlatList,
  ActivityIndicator,
  TouchableOpacity,
} from "react-native";
import { getSuggestEngine, suggestWithEngine } from "../hud/engines/index";
import type { ClientCfg as EnginesClientCfg } from "../hud/engines/index";
import type {
  SuggestContext,
  SuggestInput,
  CsSuggestContext,
} from "../hud/engines/types";
import type { ClientCfg } from "../hud/accounting-api";
import { isMock } from "../hud/accounting-api";
import { fetchCsTickets, type CsTicket } from "../hud/cs-api";
import { sendLlmUsageEvent } from "../hud/telemetry/llmUsage";
import { applyLlmTextPostProcess } from "../hud/engines/llmPostProcess";
import { recordLlmUsage } from "../os/telemetry/osTelemetry";
import { resolveBffBaseUrl } from "../os/bff";

type Props = { cfg?: ClientCfg };

const QA_TRIGGER = process.env.EXPO_PUBLIC_QA_TRIGGER_LLM_USAGE === "1";

export function CsHUD({ cfg }: Props = {}) {
  const qaTriggeredRef = useRef(false);
  // defaultCfg를 useMemo로 메모이제이션하여 무한 루프 방지
  const defaultCfg: ClientCfg = useMemo(() => {
    // OS 공통 resolveBffBaseUrl 사용 (하드코딩 URL 금지)
    return {
      baseUrl: (
        process.env.EXPO_PUBLIC_BFF_BASE_URL ||
        process.env.EXPO_PUBLIC_BFF_URL ||
        resolveBffBaseUrl()
      ).replace(/\/$/, ""),
      tenantId: process.env.EXPO_PUBLIC_TENANT_ID || "default",
      apiKey: process.env.EXPO_PUBLIC_API_KEY || "collector-key:operator",
      mode: (process.env.EXPO_PUBLIC_DEMO_MODE === "mock" ? "mock" : "live") as
        | "mock"
        | "live",
    };
  }, []);

  // clientCfg도 메모이제이션
  const clientCfg = useMemo(() => cfg || defaultCfg, [cfg, defaultCfg]);

  // engines/index.ts의 ClientCfg로 변환 (메모이제이션)
  const enginesCfg: EnginesClientCfg = useMemo(
    () => ({
      mode: clientCfg.mode || "live",
      tenantId: clientCfg.tenantId,
      userId: "hud-user-1",
      baseUrl: clientCfg.baseUrl,
      apiKey: clientCfg.apiKey,
    }),
    [clientCfg.mode, clientCfg.tenantId, clientCfg.baseUrl, clientCfg.apiKey]
  );

  const engine = useMemo(() => getSuggestEngine(enginesCfg), [enginesCfg]);
  const engineLabel =
    engine.id === "local-llm-v1" ? "On-device (LLM Stub)" : "On-device (Rule)";

  // 티켓 리스트 상태
  const [tickets, setTickets] = useState<CsTicket[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // SuggestEngine 관련 상태
  const [suggesting, setSuggesting] = useState(false);
  const [suggestionResult, setSuggestionResult] = useState<any>(null);
  const [selectedTicket, setSelectedTicket] = useState<CsTicket | null>(null);
  
  // ✅ P0-2: 스트리밍 출력 상태
  const [streamingText, setStreamingText] = useState<string>("");
  const [isStreaming, setIsStreaming] = useState(false);
  
  // ✅ P0-2: 취소 신호 관리
  const abortControllerRef = useRef<AbortController | null>(null);

  // ✅ E06-3: 모델 로딩 Progress 상태
  const [modelLoading, setModelLoading] = useState(false);
  const [modelLoadProgress, setModelLoadProgress] = useState<{
    progress: number;
    text: string;
  } | null>(null);

  // R10-S3: 추천 세션 추적 (중복 전송 방지)
  type SuggestionSession = {
    shownTextNormalized: string;
    finalized: boolean; // accepted/edited/rejected 중 하나라도 찍었으면 true
  };
  const suggestionSessionRef = useRef<SuggestionSession | null>(null);

  // 텍스트 정규화 함수 (비교용)
  function normalizeForCompare(text: string): string {
    if (!text) return "";
    return applyLlmTextPostProcess(
      {
        domain: "cs",
        engineMeta: engine.meta,
        mode: engine.meta.type,
      },
      text
    );
  }

  // 티켓 리스트 로드
  useEffect(() => {
    let cancelled = false;

    async function loadTickets() {
      try {
        setLoading(true);
        setError(null);

        console.log("[CsHUD] Loading tickets, clientCfg:", {
          mode: clientCfg.mode,
          tenantId: clientCfg.tenantId,
        });
        const response = await fetchCsTickets(clientCfg, {
          limit: 20,
          offset: 0,
        });

        console.log("[CsHUD] Received response:", response);

        if (!cancelled) {
          if (response && response.items) {
            setTickets(response.items);
            setLoading(false);
          } else {
            throw new Error("Invalid response format: missing items");
          }
        }
      } catch (err: any) {
        if (!cancelled) {
          console.error("[CsHUD] Failed to load tickets:", err);
          console.error("[CsHUD] Error details:", {
            message: err?.message,
            code: err?.code,
            errno: err?.errno,
            stack: err?.stack,
            toString: err?.toString(),
            string: String(err),
          });
          const errorMessage =
            err?.message ||
            err?.toString() ||
            String(err) ||
            "티켓을 불러오는데 실패했습니다.";
          setError(errorMessage);
          setLoading(false);
        }
      }
    }
    loadTickets();

    return () => {
      cancelled = true;
    };
  }, [clientCfg.mode, clientCfg.tenantId, clientCfg.baseUrl]); // clientCfg 객체 대신 구체적인 값들을 의존성으로 사용

  // QA 트리거는 제품 플로우가 아니라 QA 증빙용. ENV=1일 때만 1회 실행.
  useEffect(() => {
    if (!QA_TRIGGER) return;
    if (clientCfg.mode !== "live") return;
    if (qaTriggeredRef.current) return;

    qaTriggeredRef.current = true;

    console.log("[QA] llm-usage trigger: start");

    void recordLlmUsage(
      "live",
      {
        tenantId: clientCfg.tenantId ?? "default",
        userId: "hud-user-1",
        userRole: "operator",
        apiKey: "collector-key:operator",
      },
      { eventType: "qa_trigger_llm_usage", suggestionLength: 0 }
    )
      .then(() => console.log("[QA] llm-usage trigger: done"))
      .catch((e) => console.warn("[QA] llm-usage trigger: failed", e));
  }, [clientCfg.mode, clientCfg.tenantId]);

  // CS 응답 추천 요청 핸들러
  const handleSuggest = async (ticket: CsTicket) => {
    // ✅ P0-2: 중복 요청 방지
    if (suggesting || modelLoading) {
      console.warn("[CsHUD] Suggest already in progress, ignoring duplicate request");
      return;
    }

    // ✅ P0-2: 이전 요청 취소
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    abortControllerRef.current = new AbortController();

    setSelectedTicket(ticket);
    setSuggesting(true);
    setSuggestionResult(null);
    setModelLoading(false);
    setModelLoadProgress(null);
    setStreamingText("");
    setIsStreaming(false);

    // ✅ P0-3: 성능 메타 수집 시작
    const perfMeta = {
      modelLoadStart: 0,
      modelLoadEnd: 0,
      inferenceStart: 0,
      inferenceEnd: 0,
      firstTokenTime: 0,
      backend: engine.meta.stub ? ("stub" as const) : ("real" as const),
      cancelled: false,
      fallback: false,
    };

    try {
      // ✅ E06-3: 엔진 초기화 (모델 로딩 포함)
      if (!engine.isReady && engine.initialize) {
        setModelLoading(true);
        setModelLoadProgress({ progress: 0, text: "모델 초기화 중..." });
        perfMeta.modelLoadStart = Date.now();

        try {
          await engine.initialize();
          perfMeta.modelLoadEnd = Date.now();
          setModelLoadProgress({ progress: 100, text: "모델 로딩 완료" });
          // Progress 완료 후 약간의 지연 후 초기화 (UX 개선)
          await new Promise((resolve) => setTimeout(resolve, 300));
        } catch (initError: any) {
          perfMeta.modelLoadEnd = Date.now();
          perfMeta.fallback = true;
          // ✅ E06-3: 초기화 실패 시 suggestion_error + stub fallback
          console.warn("[CsHUD] Engine initialization failed:", initError);
          const modelLoadMs = perfMeta.modelLoadEnd - perfMeta.modelLoadStart;
          void recordLlmUsage(
            clientCfg.mode,
            {
              tenantId: clientCfg.tenantId ?? "default",
              userId: enginesCfg.userId || "hud-user-1",
              userRole: "operator",
              apiKey: clientCfg.apiKey || "collector-key:operator",
            },
            {
              eventType: "suggestion_error",
              suggestionLength: 0,
              modelLoadMs,
              backend: perfMeta.backend,
              success: false,
              fallback: true,
            }
          ).catch(() => {});

          // 초기화 실패해도 suggest는 계속 진행 (엔진이 자체적으로 stub fallback 처리)
        } finally {
          setModelLoading(false);
          setModelLoadProgress(null);
        }
      }
      const ctx: CsSuggestContext = {
        domain: "cs",
        tenantId: clientCfg.tenantId,
        ticket: {
          id: ticket.id,
          subject: ticket.subject,
          body: ticket.body,
          status: ticket.status,
          createdAt: ticket.createdAt,
        },
      };

      // ✅ P0-2: 스트리밍 출력을 위해 엔진을 직접 사용
      // (suggestWithEngine은 스트리밍 콜백을 지원하지 않으므로 직접 호출)
      setIsStreaming(true);
      setStreamingText("");
      perfMeta.inferenceStart = Date.now();
      let firstTokenReceived = false;

      // 스트리밍 콜백: 토큰이 올 때마다 UI 업데이트
      const onToken = (token: string) => {
        if (!abortControllerRef.current?.signal.aborted) {
          // ✅ P0-3: 첫 토큰 시간 기록
          if (!firstTokenReceived) {
            perfMeta.firstTokenTime = Date.now();
            firstTokenReceived = true;
          }
          setStreamingText((prev) => prev + token);
        }
      };

      const result = await engine.suggest(ctx as SuggestContext, {
        text: ticket.subject,
        meta: {
          ticketId: ticket.id,
          status: ticket.status,
          createdAt: ticket.createdAt,
          // ✅ P0-2: 스트리밍 콜백 및 취소 신호 전달
          onToken,
          signal: abortControllerRef.current.signal,
        },
      });

      perfMeta.inferenceEnd = Date.now();
      setIsStreaming(false);
      
      // ✅ P0-2: 스트리밍 완료 후 최종 텍스트로 결과 설정
      // (스트리밍 중 텍스트가 있으면 그것을 사용, 없으면 결과 사용)
      if (streamingText) {
        // 스트리밍 텍스트를 결과에 반영
        if (result.items && result.items.length > 0) {
          result.items[0].description = streamingText;
          result.items[0].title = streamingText.split("\n")[0] || streamingText;
        }
      }
      
      setSuggestionResult(result);
      setStreamingText(""); // 스트리밍 텍스트 초기화

      // R10-S3: 추천 생성 성공 시 shown 이벤트 전송
      if (result.items && result.items.length > 0) {
        const firstSuggestion = result.items[0];
        const suggestionText =
          firstSuggestion.description || firstSuggestion.title || "";
        const shownText = normalizeForCompare(suggestionText);

        // ✅ P0-2 + P0-3: OS 공통 Telemetry로 KPI/Audit 이벤트 전송 (메타 only + 성능 메타)
        const modelLoadMs = perfMeta.modelLoadEnd > 0
          ? perfMeta.modelLoadEnd - perfMeta.modelLoadStart
          : undefined;
        const inferenceMs = perfMeta.inferenceEnd - perfMeta.inferenceStart;
        const firstByteMs = perfMeta.firstTokenTime > 0
          ? perfMeta.firstTokenTime - perfMeta.inferenceStart
          : undefined;

        void recordLlmUsage(
          clientCfg.mode,
          {
            tenantId: clientCfg.tenantId ?? "default",
            userId: enginesCfg.userId || "hud-user-1",
            userRole: "operator",
            apiKey: clientCfg.apiKey || "collector-key:operator",
          },
          {
            eventType: "suggestion_shown",
            suggestionLength: shownText.length,
            modelLoadMs,
            inferenceMs,
            firstByteMs,
            backend: perfMeta.backend,
            success: true,
            fallback: perfMeta.fallback,
            cancelled: false,
          }
        ).catch((e) => {
          console.warn("[CsHUD] Failed to record suggestion_shown:", e);
        });

        // 이전 추천이 있었는데 아직 확정 이벤트가 없다면, 새 추천 생성은 "기존 추천을 버린 것"으로 간주
        if (
          suggestionSessionRef.current &&
          !suggestionSessionRef.current.finalized
        ) {
          // ✅ P0-2: OS 공통 Telemetry 사용 (메타 only)
          void recordLlmUsage(
            clientCfg.mode,
            {
              tenantId: clientCfg.tenantId ?? "default",
              userId: enginesCfg.userId || "hud-user-1",
              userRole: "operator",
              apiKey: clientCfg.apiKey || "collector-key:operator",
            },
            {
              eventType: "suggestion_rejected",
              suggestionLength:
                suggestionSessionRef.current.shownTextNormalized.length,
            }
          ).catch((e) => {
            console.warn("[CsHUD] Failed to record rejected event:", e);
          });
        }

        // 새 추천 세션 시작
        suggestionSessionRef.current = {
          shownTextNormalized: shownText,
          finalized: false,
        };
      }
    } catch (err: any) {
      // ✅ P0-2: 취소된 요청은 에러로 처리하지 않음
      if (err?.message === "GENERATION_ABORTED" || abortControllerRef.current?.signal.aborted) {
        console.log("[CsHUD] Suggest cancelled by user");
        perfMeta.cancelled = true;
        setIsStreaming(false);
        setStreamingText("");
        setSuggesting(false);

        // ✅ P0-3: 취소 이벤트 기록 (성능 메타 포함)
        const inferenceMs = perfMeta.inferenceEnd > 0
          ? perfMeta.inferenceEnd - perfMeta.inferenceStart
          : Date.now() - perfMeta.inferenceStart;
        const modelLoadMs = perfMeta.modelLoadEnd > 0
          ? perfMeta.modelLoadEnd - perfMeta.modelLoadStart
          : undefined;

        void recordLlmUsage(
          clientCfg.mode,
          {
            tenantId: clientCfg.tenantId ?? "default",
            userId: enginesCfg.userId || "hud-user-1",
            userRole: "operator",
            apiKey: clientCfg.apiKey || "collector-key:operator",
          },
          {
            eventType: "suggestion_error",
            suggestionLength: 0,
            modelLoadMs,
            inferenceMs,
            backend: perfMeta.backend,
            success: false,
            cancelled: true,
          }
        ).catch(() => {});
        return;
      }

      console.error("[CsHUD] Suggest error:", err);
      setError(err.message || "응답 추천을 생성하는데 실패했습니다.");
      setIsStreaming(false);
      setStreamingText("");

      // ✅ P0-2 + P0-3: OS 공통 Telemetry 사용 (메타 only + 성능 메타)
      const inferenceMs = perfMeta.inferenceEnd > 0
        ? perfMeta.inferenceEnd - perfMeta.inferenceStart
        : Date.now() - perfMeta.inferenceStart;
      const modelLoadMs = perfMeta.modelLoadEnd > 0
        ? perfMeta.modelLoadEnd - perfMeta.modelLoadStart
        : undefined;

      void recordLlmUsage(
        clientCfg.mode,
        {
          tenantId: clientCfg.tenantId ?? "default",
          userId: enginesCfg.userId || "hud-user-1",
          userRole: "operator",
          apiKey: clientCfg.apiKey || "collector-key:operator",
        },
        {
          eventType: "suggestion_error",
          suggestionLength: 0,
          modelLoadMs,
          inferenceMs,
          backend: perfMeta.backend,
          success: false,
          fallback: perfMeta.fallback,
          cancelled: false,
        }
      ).catch((e) => {
        console.warn("[CsHUD] Failed to record error event:", e);
      });
    } finally {
      setSuggesting(false);
    }
  };

  // R10-S3: 답변 전송 핸들러 (accepted_as_is vs edited)
  const handleSendReply = async (finalTextRaw: string) => {
    const sess = suggestionSessionRef.current;
    if (!sess || sess.finalized) {
      // 추천 세션이 없거나 이미 확정된 경우, 이벤트 전송 없이 전송만 수행
      // TODO: 실제 답변 전송 로직 구현
      console.log(
        "[CsHUD] Sending reply (no suggestion session):",
        finalTextRaw
      );
      return;
    }

    const finalText = normalizeForCompare(finalTextRaw);
    // ✅ P0-2: eventType 세분화 (메타 only)
    const eventType =
      finalText === sess.shownTextNormalized
        ? "suggestion_used_as_is"
        : "suggestion_edited";

    // OS 공통 Telemetry 사용 (메타 only)
    void recordLlmUsage(
      clientCfg.mode,
      {
        tenantId: clientCfg.tenantId ?? "default",
        userId: enginesCfg.userId || "hud-user-1",
        userRole: "operator",
        apiKey: clientCfg.apiKey || "collector-key:operator",
      },
      {
        eventType,
        suggestionLength: finalText.length,
      }
    ).catch((e) => {
      console.warn("[CsHUD] Failed to record usage event:", e);
    });

    suggestionSessionRef.current = { ...sess, finalized: true };

    // TODO: 실제 답변 전송 로직 구현
    console.log("[CsHUD] Sending reply:", finalTextRaw);
  };

  // R10-S3: 추천 닫기/무시 핸들러 (rejected)
  const handleDismissSuggestion = async () => {
    // ✅ P0-2: 진행 중인 요청 취소
    if (abortControllerRef.current && (suggesting || isStreaming)) {
      abortControllerRef.current.abort();
      setIsStreaming(false);
      setStreamingText("");
      setSuggesting(false);
    }

    const sess = suggestionSessionRef.current;
    if (sess && !sess.finalized) {
      // ✅ P0-2: OS 공통 Telemetry 사용 (메타 only)
      void recordLlmUsage(
        clientCfg.mode,
        {
          tenantId: clientCfg.tenantId ?? "default",
          userId: enginesCfg.userId || "hud-user-1",
          userRole: "operator",
          apiKey: clientCfg.apiKey || "collector-key:operator",
        },
        {
          eventType: "suggestion_rejected",
          suggestionLength: sess.shownTextNormalized.length,
        }
      ).catch((e) => {
        console.warn("[CsHUD] Failed to record rejected event:", e);
      });
      suggestionSessionRef.current = { ...sess, finalized: true };
    }

    // UI 상태 정리
    setSuggestionResult(null);
  };

  const renderTicket = ({ item }: { item: CsTicket }) => {
    const statusColor =
      item.status === "open"
        ? "#28a745"
        : item.status === "pending"
        ? "#ffc107"
        : "#6c757d";
    const statusText =
      item.status === "open"
        ? "열림"
        : item.status === "pending"
        ? "대기"
        : "닫힘";
    const createdAt = new Date(item.createdAt).toLocaleDateString("ko-KR");
    const isSelected = selectedTicket?.id === item.id;

    return (
      <View style={styles.ticketItem}>
        <View style={styles.ticketHeader}>
          <Text style={styles.ticketSubject}>{item.subject}</Text>
          <View style={[styles.statusBadge, { backgroundColor: statusColor }]}>
            <Text style={styles.statusText}>{statusText}</Text>
          </View>
        </View>
        <Text style={styles.ticketDate}>생성일: {createdAt}</Text>
        <TouchableOpacity
          style={[
            styles.suggestButton,
            isSelected &&
              (suggesting || modelLoading) &&
              styles.suggestButtonActive,
          ]}
          onPress={() => handleSuggest(item)}
          disabled={suggesting || modelLoading}
        >
          <Text style={styles.suggestButtonText}>
            {modelLoading && isSelected
              ? modelLoadProgress?.text || "모델 로딩 중..."
              : suggesting && isSelected
              ? "추천 중..."
              : "요약/추천"}
          </Text>
        </TouchableOpacity>
        {/* ✅ E06-3: 모델 로딩 Progress 표시 */}
        {isSelected && modelLoading && modelLoadProgress && (
          <View style={styles.progressContainer}>
            <View style={styles.progressBar}>
              <View
                style={[
                  styles.progressFill,
                  { width: `${modelLoadProgress.progress}%` },
                ]}
              />
            </View>
            <Text style={styles.progressText}>
              {modelLoadProgress.text} ({modelLoadProgress.progress}%)
            </Text>
          </View>
        )}
        {isSelected && suggestionResult && (
          <View style={styles.suggestionResult}>
            <View style={styles.suggestionHeader}>
              <Text style={styles.suggestionTitle}>응답 추천:</Text>
              <TouchableOpacity
                style={styles.dismissButton}
                onPress={handleDismissSuggestion}
              >
                <Text style={styles.dismissButtonText}>닫기</Text>
              </TouchableOpacity>
            </View>
            {suggestionResult.items.map((item: any, idx: number) => {
              const suggestionText = item.description || item.title || "";

              return (
                <View key={idx} style={styles.suggestionItem}>
                  <Text style={styles.suggestionText}>{item.title}</Text>
                  {item.description && (
                    <Text style={styles.suggestionDesc}>
                      {item.description}
                    </Text>
                  )}
                  {/* R10-S3: 전송 버튼 추가 */}
                  <View style={styles.suggestionActions}>
                    <TouchableOpacity
                      style={[styles.actionButton, styles.primaryButton]}
                      onPress={() => handleSendReply(suggestionText)}
                    >
                      <Text
                        style={[
                          styles.actionButtonText,
                          styles.primaryButtonText,
                        ]}
                      >
                        전송
                      </Text>
                    </TouchableOpacity>
                  </View>
                </View>
              );
            })}
          </View>
        )}
      </View>
    );
  };

  return (
    <ScrollView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>CS HUD</Text>
        <Text style={styles.engineLabel}>Engine: {engineLabel}</Text>
      </View>

      {isMock(clientCfg) && (
        <View style={styles.mockBanner}>
          <Text style={styles.mockText}>
            ⓘ Mock 모드: 네트워크 요청이 발생하지 않습니다.
          </Text>
        </View>
      )}

      <View style={styles.content}>
        <Text style={styles.sectionTitle}>최근 티켓</Text>

        {loading && (
          <View style={styles.centerContainer}>
            <ActivityIndicator size="small" color="#007AFF" />
            <Text style={styles.loadingText}>불러오는 중...</Text>
          </View>
        )}

        {error && (
          <View style={styles.errorContainer}>
            <Text style={styles.errorText}>❌ {error}</Text>
          </View>
        )}

        {!loading && !error && tickets.length === 0 && (
          <View style={styles.centerContainer}>
            <Text style={styles.emptyText}>티켓이 없습니다.</Text>
          </View>
        )}

        {!loading && !error && tickets.length > 0 && (
          <FlatList
            data={tickets}
            renderItem={renderTicket}
            keyExtractor={(item) => String(item.id)}
            scrollEnabled={false}
            style={styles.ticketList}
          />
        )}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 16,
  },
  header: {
    marginBottom: 16,
  },
  title: {
    fontSize: 24,
    fontWeight: "bold",
    color: "#333",
  },
  engineLabel: {
    fontSize: 12,
    color: "#666",
    marginTop: 4,
  },
  content: {
    marginTop: 16,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: "600",
    color: "#333",
    marginBottom: 12,
  },
  mockBanner: {
    backgroundColor: "#fff3cd",
    padding: 12,
    borderRadius: 4,
    marginTop: 16,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: "#ffc107",
  },
  mockText: {
    fontSize: 12,
    color: "#856404",
  },
  centerContainer: {
    alignItems: "center",
    justifyContent: "center",
    padding: 32,
  },
  loadingText: {
    marginTop: 8,
    fontSize: 14,
    color: "#666",
  },
  errorContainer: {
    backgroundColor: "#f8d7da",
    padding: 12,
    borderRadius: 4,
    borderWidth: 1,
    borderColor: "#f5c6cb",
  },
  errorText: {
    fontSize: 14,
    color: "#721c24",
  },
  emptyText: {
    fontSize: 14,
    color: "#666",
    fontStyle: "italic",
  },
  ticketList: {
    marginTop: 8,
  },
  ticketItem: {
    backgroundColor: "#f8f9fa",
    padding: 12,
    borderRadius: 4,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: "#dee2e6",
  },
  ticketHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 4,
  },
  ticketSubject: {
    fontSize: 16,
    fontWeight: "500",
    color: "#333",
    flex: 1,
    marginRight: 8,
  },
  statusBadge: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 12,
  },
  statusText: {
    fontSize: 12,
    color: "#fff",
    fontWeight: "600",
  },
  ticketDate: {
    fontSize: 12,
    color: "#666",
    marginTop: 4,
  },
  suggestButton: {
    backgroundColor: "#007AFF",
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 4,
    marginTop: 8,
    alignItems: "center",
  },
  suggestButtonActive: {
    backgroundColor: "#0056b3",
    opacity: 0.7,
  },
  suggestButtonText: {
    color: "#fff",
    fontSize: 14,
    fontWeight: "600",
  },
  suggestionResult: {
    marginTop: 12,
    padding: 12,
    backgroundColor: "#e7f3ff",
    borderRadius: 4,
    borderWidth: 1,
    borderColor: "#b3d9ff",
  },
  suggestionTitle: {
    fontSize: 14,
    fontWeight: "600",
    color: "#333",
    marginBottom: 8,
  },
  suggestionItem: {
    marginBottom: 8,
  },
  suggestionText: {
    fontSize: 14,
    color: "#333",
    marginBottom: 4,
  },
  suggestionDesc: {
    fontSize: 12,
    color: "#666",
    fontStyle: "italic",
  },
  suggestionHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 8,
  },
  dismissButton: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 4,
    backgroundColor: "#e9ecef",
    borderWidth: 1,
    borderColor: "#dee2e6",
  },
  dismissButtonText: {
    fontSize: 12,
    color: "#333",
    fontWeight: "500",
  },
  suggestionActions: {
    flexDirection: "row",
    justifyContent: "flex-end",
    marginTop: 8,
    gap: 8,
  },
  actionButton: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 4,
    backgroundColor: "#e9ecef",
    borderWidth: 1,
    borderColor: "#dee2e6",
  },
  primaryButton: {
    backgroundColor: "#007AFF",
    borderColor: "#007AFF",
  },
  actionButtonText: {
    fontSize: 12,
    color: "#333",
    fontWeight: "500",
  },
  primaryButtonText: {
    color: "#fff",
  },
  progressContainer: {
    marginTop: 8,
    padding: 8,
    backgroundColor: "#f0f0f0",
    borderRadius: 4,
  },
  progressBar: {
    height: 4,
    backgroundColor: "#e0e0e0",
    borderRadius: 2,
    overflow: "hidden",
    marginBottom: 4,
  },
  progressFill: {
    height: "100%",
    backgroundColor: "#007AFF",
    borderRadius: 2,
    transition: "width 0.3s ease",
  },
  progressText: {
    fontSize: 12,
    color: "#666",
    textAlign: "center",
  },
  streamingCursor: {
    color: "#007AFF",
    fontWeight: "bold",
    animation: "blink 1s infinite",
  },
});
