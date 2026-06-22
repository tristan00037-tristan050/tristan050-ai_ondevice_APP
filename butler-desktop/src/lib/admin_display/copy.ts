// 관리자 화면 표시 전용 라벨/문구 헬퍼.
// 이 파일은 화면에 보여줄 한국어 라벨만 제공한다. API field 이름, enum 값,
// request body 값, digest/header/token 등 보안·통신 계약은 절대 바꾸지 않는다.
//
// 라벨 맵은 contracts 의 실제 타입으로 Record 를 강제해, 값이 추가되면
// 컴파일 단계에서 누락이 드러나도록 한다(영어 enum 이 화면에 새어나가는 것 방지).
import type { AdminRole, DocGrade, PolicyDecision } from '../admin_policy/contracts';
import type { DeprecateReasonCode } from '../company_fact/contracts';

export const ROLE_LABELS: Record<AdminRole, string> = {
  admin: '관리자',
  manager: '팀장',
  employee: '직원',
};

// 정책 상태(DRAFT/ACTIVE/DEPRECATED)와 회사 지식 후보 상태(CANDIDATE)를 함께 덮는다.
export type DisplayStatus = 'DRAFT' | 'ACTIVE' | 'DEPRECATED' | 'CANDIDATE';
export const STATUS_LABELS: Record<DisplayStatus, string> = {
  DRAFT: '초안',
  ACTIVE: '사용 중',
  DEPRECATED: '사용 중지',
  CANDIDATE: '승인 대기',
};

export const DOC_GRADE_DISPLAY: Record<DocGrade, string> = {
  restricted: '매우 민감',
  confidential: '대외비',
  internal: '내부용',
  public: '공개 가능',
};

export const POLICY_DECISION_DISPLAY: Record<PolicyDecision, string> = {
  allow: '허용',
  needs_review: '검토 필요',
  block: '차단',
};

export const DEPRECATE_REASON_DISPLAY: Record<DeprecateReasonCode, string> = {
  WRONG: '틀린 정보',
  SUPERSEDED: '대체된 옛 버전',
  MANUAL_DEPRECATED: '일반 폐기',
};

export const DEPRECATE_REASON_HELP: Record<DeprecateReasonCode, string> = {
  WRONG: '앞으로 비슷한 후보가 들어오면 다시 확인합니다.',
  SUPERSEDED: '새 버전으로 바뀐 옛 정보입니다.',
  MANUAL_DEPRECATED: '기록만 남기고 사용을 중지합니다.',
};

// 알 수 없는 상태 코드는 영어 enum 을 그대로 노출하지 않도록 한국어가 없으면
// 빈 표시 대신 '상태 확인 중'으로 보여준다(테스트로 enum 비노출을 검증).
export function statusLabel(value: string): string {
  return (STATUS_LABELS as Record<string, string>)[value] ?? '상태 확인 중';
}
