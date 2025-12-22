/**
 * LocalLLMEngineV1 구현
 * R8-S2: 실제 온디바이스 엔진 어댑터 Stub
 *
 * 실제 LLM은 아직 연결하지 않고, 로딩·추론 지연까지 흉내 내는 더미로 구현
 */

import type {
  SuggestEngine,
  SuggestContext,
  SuggestInput,
  SuggestResult,
  SuggestEngineMeta,
} from "./types";
import type { ClientCfg } from "./index";
import type {
  SuggestEngine as OldSuggestEngine,
  SuggestItem as OldSuggestItem,
} from "../accounting-api";
import { localRuleEngineV1 as oldLocalRuleEngineV1 } from "../accounting-api";
import { getDomainLLMService } from "../../os/llm/registry";
import type { DomainId } from "../../os/llm/types";
import { recordLlmUsage } from "../../os/telemetry/osTelemetry";
import { getInferenceAdapter } from "../../os/llm/inference";

export interface LocalLLMEngineOptions {
  cfg: ClientCfg;
}

/**
 * 온디바이스 LLM 어댑터 인터페이스 (R8-S2)
 * 실제 LLM 라이브러리와의 연결을 위한 추상화 계층
 */
export interface OnDeviceLLMAdapter {
  /**
   * 모델 초기화
   */
  initialize(): Promise<void>;

  /**
   * 추론 수행
   * @param context LLM 컨텍스트 (도메인, 언어, 힌트 등)
   * @param input 입력 텍스트
   * @returns 추론 결과
   */
  infer(
    context: {
      domain: "accounting" | "cs";
      locale?: string;
      hints?: string[];
    },
    input: string
  ): Promise<{
    suggestions: Array<{
      id: string;
      title: string;
      description?: string;
      score: number;
    }>;
    explanation?: string;
  }>;
}

/**
 * 더미 LLM 어댑터 (임시 구현)
 * 실제 LLM 라이브러리 연동 전까지 사용
 */
class DummyLLMAdapter implements OnDeviceLLMAdapter {
  private initialized = false;

  async initialize(): Promise<void> {
    if (this.initialized) return;
    // 모델 로딩 시뮬레이션
    await new Promise((resolve) => setTimeout(resolve, 1500));
    this.initialized = true;
  }

  async infer(
    context: {
      domain: "accounting" | "cs";
      locale?: string;
      hints?: string[];
    },
    input: string
  ): Promise<{
    suggestions: Array<{
      id: string;
      title: string;
      description?: string;
      score: number;
    }>;
    explanation?: string;
  }> {
    if (!this.initialized) {
      throw new Error("Adapter not initialized");
    }

    // 추론 지연 시뮬레이션
    await new Promise((resolve) => setTimeout(resolve, 600));

    // 더미 응답 생성
    const label = context.domain === "accounting" ? "회계" : "CS";
    return {
      suggestions: [
        {
          id: "llm-suggestion-1",
          title: `[LLM] ${label} 추론 결과`,
          description: `온디바이스 LLM이 "${input}"을 분석한 결과입니다.`,
          score: 0.85,
        },
      ],
      explanation: `더미 LLM 어댑터가 생성한 추론 결과입니다. 실제 LLM은 R8-S2 이후 연동 예정입니다.`,
    };
  }
}

/**
 * LocalLLMEngineV1
 * 온디바이스 LLM 엔진 구현
 * R10-S3: 실제 모델 PoC 지원 (E06-1)
 */
export class LocalLLMEngineV1 implements SuggestEngine {
  readonly id = "local-llm-v1";
  readonly mode = "local-only" as const;

  public meta: SuggestEngineMeta;

  public isReady = false;

  private readonly cfg: ClientCfg;
  private readonly adapter: OnDeviceLLMAdapter;
  private readonly useRealModel: boolean;
  private readonly inferenceAdapter: ReturnType<typeof getInferenceAdapter>;

  constructor(options: LocalLLMEngineOptions) {
    this.cfg = options.cfg;

    // R10-S3: 실제 모델 라이브러리 연동 전까지는 항상 Stub 사용
    // 실제 모델 사용 여부는 환경변수로 제어 (EXPO_PUBLIC_USE_REAL_LLM=1)
    const useRealLLMEnv = process.env.EXPO_PUBLIC_USE_REAL_LLM === "1";
    const isMockMode = options.cfg.mode === "mock";

    // RealLLMAdapter가 실제로 구현되기 전까지는 항상 stub=true 유지
    // 실제 모델 스위치가 켜져도 아직 RealLLMAdapter가 없으면 stub=true
    this.useRealModel = useRealLLMEnv && !isMockMode;

    // 어댑터 선택: 현재는 항상 DummyLLMAdapter 사용
    // TODO: 실제 모델 라이브러리 연동 후 RealLLMAdapter 추가
    this.adapter = new DummyLLMAdapter();

    // ✅ E06-2: Inference adapter 초기화 (Mock 강제 stub 포함)
    this.inferenceAdapter = getInferenceAdapter({
      demoMode: isMockMode ? "mock" : "live",
    });

    // 메타 정보 설정
    // ✅ E06-2: Real backend 사용 여부에 따라 stub 플래그 설정
    const isRealBackend = this.inferenceAdapter.backend === "real";
    const variant = isMockMode ? "local-llm-v0" : "local-llm-v1";
    const stub = !isRealBackend; // Real backend 사용 시 stub=false

    this.meta = {
      type: "local-llm",
      label: stub ? "On-device LLM (Stub)" : "On-device LLM",
      variant,
      stub,
      supportedDomains: ["accounting", "cs"],
    };
  }

  async initialize(): Promise<void> {
    if (this.isReady) return;

    const modelType = this.meta.stub ? "Stub (simulated)" : "Real model";
    console.log(`[LocalLLMEngineV1] loading on-device model (${modelType})...`);
    await this.adapter.initialize();
    this.isReady = true;
    console.log(
      `[LocalLLMEngineV1] model loaded (variant: ${this.meta.variant}, stub: ${this.meta.stub})`
    );
  }

  canHandleDomain(domain: "accounting" | "cs"): boolean {
    return this.meta.supportedDomains?.includes(domain) ?? true;
  }

  async suggest<TPayload = unknown>(
    ctx: SuggestContext,
    input: SuggestInput
  ): Promise<SuggestResult<TPayload>> {
    if (!this.isReady) {
      throw new Error(
        "LocalLLMEngineV1 is not ready. Call initialize() first."
      );
    }

    try {
      // ✅ P0-1: Domain Registry 패턴으로 도메인별 분기 제거
      const domain = ctx.domain as DomainId;

      // ✅ P0-H: fail-closed 처리 (도메인 미지원 시 suggestion_error로 수렴)
      let service;
      try {
        service = getDomainLLMService(domain);
      } catch (e: any) {
        // 메타-only KPI: 실패를 표준 이벤트로 수렴
        void recordLlmUsage(
          this.cfg.mode,
          {
            tenantId: this.cfg.tenantId ?? "default",
            userId: this.cfg.userId || "hud-user-1",
            userRole: "operator",
            apiKey: this.cfg.apiKey || "collector-key:operator",
          },
          { eventType: "suggestion_error", suggestionLength: 0 }
        ).catch(() => {
          // 로깅 실패는 무시 (이중 실패 방지)
        });

        // 온디바이스 UI 메시지(서버 전송 금지)
        return {
          items: [
            {
              id: "error-unsupported-domain",
              title: "현재 도메인에서는 추천 기능이 지원되지 않습니다.",
              description: e?.message || "Unsupported domain",
              score: 0,
              source: "local-llm" as const,
            },
          ],
          engine: "local-llm-v1",
          confidence: 0,
        };
      }

      // 도메인별 컨텍스트 구성 (원문은 온디바이스에서만 사용)
      const domainContext = service.buildContext({
        tickets:
          ctx.domain === "cs"
            ? (ctx as any).ticket
              ? [(ctx as any).ticket]
              : []
            : undefined,
        hint: ctx.domain === "accounting" ? input.text : undefined,
      });

      // ✅ E06-2: Inference adapter 사용 (Real backend일 때만 prompt 경로)
      let suggestionText: string;
      const useRealBackend = this.inferenceAdapter.backend === "real";

      if (useRealBackend) {
        try {
          // Real 모델: prompt 생성 → adapter.generate
          const prompt = service.buildPrompt(domainContext);
          // ✅ E06-3: Progress 콜백은 엔진 레벨에서 처리하지 않고, adapter 내부에서만 사용
          // (UI는 HUD 레벨에서 별도 상태로 관리)
          await this.inferenceAdapter.load();
          
          // ✅ P0-2: 스트리밍 지원 (onToken 콜백 전달)
          // input.meta에서 스트리밍 콜백을 받아 adapter에 전달
          const onToken = (input.meta as any)?.onToken as
            | ((token: string) => void)
            | undefined;
          const signal = (input.meta as any)?.signal as
            | AbortSignal
            | undefined;

          suggestionText = await this.inferenceAdapter.generate(prompt, {
            maxTokens: 512,
            onToken,
            signal,
          });
        } catch (error: any) {
          // ✅ E06-2: Real inference 실패 시 suggestion_error로 수렴
          console.warn(
            "[LocalLLMEngineV1] Real inference failed, falling back to stub:",
            error
          );

          // 메타-only KPI: 실패를 표준 이벤트로 수렴
          void recordLlmUsage(
            this.cfg.mode,
            {
              tenantId: this.cfg.tenantId ?? "default",
              userId: this.cfg.userId || "hud-user-1",
              userRole: "operator",
              apiKey: this.cfg.apiKey || "collector-key:operator",
            },
            { eventType: "suggestion_error", suggestionLength: 0 }
          ).catch(() => {
            // 로깅 실패는 무시 (이중 실패 방지)
          });

          // Stub으로 폴백
          const result = service.stubSuggest(domainContext);
          suggestionText = result.suggestionText;
        }
      } else {
        // Stub(v0): 도메인 서비스의 stubSuggest 사용
        const result = service.stubSuggest(domainContext);
        suggestionText = result.suggestionText;
        // 추론 지연 시뮬레이션 (온디바이스 느낌)
        await new Promise((resolve) => setTimeout(resolve, 600));
      }

      // SuggestResult 형식으로 변환
      const items = [
        {
          id: `llm-suggestion-${Date.now()}`,
          title: suggestionText,
          description: suggestionText,
          score: 0.85,
          source: "local-llm" as const,
        },
      ];

      return {
        items,
        engine: "local-llm-v1",
        confidence: 0.85,
      };
    } catch (error) {
      // LLM 추론 실패 시 fallback 규칙 엔진 사용 (순환 참조 방지를 위해 직접 호출)
      console.warn(
        "[LocalLLMEngineV1] LLM inference failed, falling back to rule engine:",
        error
      );

      // accounting-api의 localRuleEngineV1을 직접 사용
      const oldInput = {
        description: input.text,
        amount:
          typeof input.meta?.amount === "number"
            ? input.meta.amount
            : undefined,
        currency:
          typeof input.meta?.currency === "string"
            ? input.meta.currency
            : undefined,
      };

      const oldItems: OldSuggestItem[] = await (
        oldLocalRuleEngineV1 as OldSuggestEngine
      ).suggest(oldInput);

      // 새로운 SuggestItem 형식으로 변환
      const fallbackItems = oldItems.map((item, idx) => ({
        id: item.id || `fallback-${idx}`,
        title: item.description || item.account || "Unknown",
        description: item.rationale,
        score: item.score,
        source: "local-rule" as const,
      }));

      return {
        items: fallbackItems,
        engine: "local-llm-v1-fallback",
        confidence: oldItems.length > 0 ? oldItems[0].score : 0.5,
      };
    }
  }
}
