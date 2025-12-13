/**
 * Domain LLM Service 타입 re-export
 * R10-S2: 공통 패키지의 OS 표준 인터페이스를 그대로 사용
 * 
 * @module service-core-cs/domain/domainLLMService
 */

// 공통 패키지의 OS 표준 인터페이스를 그대로 사용
// 상대 경로로 import (나중에 tsconfig paths alias 설정 후 @appcore/service-core-common로 변경 가능)
export type {
  DomainLLMService,
} from '../../../service-core-common/src/llm/domainLLMService.js';

