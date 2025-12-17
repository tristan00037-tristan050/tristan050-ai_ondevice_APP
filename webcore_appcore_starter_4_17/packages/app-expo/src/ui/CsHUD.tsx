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
      { eventType: "cs_hud_demo", suggestionLength: 0 }
    )
      .then(() => console.log("[QA] llm-usage trigger: done"))
      .catch((e) => console.warn("[QA] llm-usage trigger: failed", e));
  }, [clientCfg.mode, clientCfg.tenantId]);

  // CS 응답 추천 요청 핸들러
  const handleSuggest = async (ticket: CsTicket) => {
    setSelectedTicket(ticket);
    setSuggesting(true);
    setSuggestionResult(null);

    try {
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

      // suggestWithEngine은 SuggestContext를 받지만, CsSuggestContext는 호환 가능
      // 타입 단언을 사용하여 전달
      const result = await suggestWithEngine(
        enginesCfg,
        ctx as SuggestContext,
        {
          text: ticket.subject,
          meta: {
            ticketId: ticket.id,
            status: ticket.status,
            createdAt: ticket.createdAt,
          },
        }
      );
      setSuggestionResult(result);

      // R10-S3: 추천 생성 성공 시 shown 이벤트 전송
      if (result.items && result.items.length > 0) {
        const firstSuggestion = result.items[0];
        const suggestionText =
          firstSuggestion.description || firstSuggestion.title || "";
        const shownText = normalizeForCompare(suggestionText);

        // OS 공통 Telemetry로 KPI/Audit 이벤트 전송
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
          }
        ).catch((e) => {
          console.warn("[CsHUD] Failed to record suggestion_shown:", e);
        });

        // 이전 추천이 있었는데 아직 확정 이벤트가 없다면, 새 추천 생성은 "기존 추천을 버린 것"으로 간주
        if (
          suggestionSessionRef.current &&
          !suggestionSessionRef.current.finalized
        ) {
          await sendLlmUsageEvent(clientCfg, engine, {
            tenantId: clientCfg.tenantId!,
            userId: enginesCfg.userId || "hud-user-1",
            domain: "cs",
            eventType: "rejected",
            feature: "cs_reply_suggest",
            timestamp: new Date().toISOString(),
            suggestionLength:
              suggestionSessionRef.current.shownTextNormalized.length,
          }).catch((e) => {
            console.warn("[CsHUD] Failed to send rejected event:", e);
          });
        }

        // 새 추천 세션 시작
        suggestionSessionRef.current = {
          shownTextNormalized: shownText,
          finalized: false,
        };

        // shown 이벤트 전송
        await sendLlmUsageEvent(clientCfg, engine, {
          tenantId: clientCfg.tenantId!,
          userId: enginesCfg.userId || "hud-user-1",
          domain: "cs",
          eventType: "shown",
          feature: "cs_reply_suggest",
          timestamp: new Date().toISOString(),
          suggestionLength: shownText.length,
        }).catch((e) => {
          console.warn("[CsHUD] Failed to send shown event:", e);
        });
      }
    } catch (err: any) {
      console.error("[CsHUD] Suggest error:", err);
      setError(err.message || "응답 추천을 생성하는데 실패했습니다.");

      // R10-S3: 에러 이벤트 전송
      await sendLlmUsageEvent(clientCfg, engine, {
        tenantId: clientCfg.tenantId!,
        userId: enginesCfg.userId || "hud-user-1",
        domain: "cs",
        eventType: "error",
        feature: "cs_reply_suggest",
        timestamp: new Date().toISOString(),
        suggestionLength: 0,
      }).catch((e) => {
        console.warn("[CsHUD] Failed to send error event:", e);
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
    const eventType =
      finalText === sess.shownTextNormalized ? "accepted_as_is" : "edited";

    await sendLlmUsageEvent(clientCfg, engine, {
      tenantId: clientCfg.tenantId!,
      userId: enginesCfg.userId || "hud-user-1",
      domain: "cs",
      eventType,
      feature: "cs_reply_suggest",
      timestamp: new Date().toISOString(),
      suggestionLength: finalText.length,
    }).catch((e) => {
      console.warn("[CsHUD] Failed to send usage event:", e);
    });

    suggestionSessionRef.current = { ...sess, finalized: true };

    // TODO: 실제 답변 전송 로직 구현
    console.log("[CsHUD] Sending reply:", finalTextRaw);
  };

  // R10-S3: 추천 닫기/무시 핸들러 (rejected)
  const handleDismissSuggestion = async () => {
    const sess = suggestionSessionRef.current;
    if (sess && !sess.finalized) {
      await sendLlmUsageEvent(clientCfg, engine, {
        tenantId: clientCfg.tenantId!,
        userId: enginesCfg.userId || "hud-user-1",
        domain: "cs",
        eventType: "rejected",
        feature: "cs_reply_suggest",
        timestamp: new Date().toISOString(),
        suggestionLength: sess.shownTextNormalized.length,
      }).catch((e) => {
        console.warn("[CsHUD] Failed to send rejected event:", e);
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
            isSelected && suggesting && styles.suggestButtonActive,
          ]}
          onPress={() => handleSuggest(item)}
          disabled={suggesting}
        >
          <Text style={styles.suggestButtonText}>
            {suggesting && isSelected ? "추천 중..." : "요약/추천"}
          </Text>
        </TouchableOpacity>
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
});
