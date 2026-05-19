import React from 'react';
import { Inbox, ArrowRightLeft, FilePlus, FileEdit, Calculator, ClipboardList, Mic, BarChart3, type LucideIcon } from 'lucide-react';

type CardMode = 'request_organize' | 'format_convert' | 'new_draft' | 'attachment_edit' | 'accounting_classify' | 'form_fill' | 'meeting_notes' | 'data_insight';

type Card = {
  id: number;
  mode: CardMode;
  title: string;
  desc: string;
  active: boolean;
  Icon: LucideIcon;
};

const CARDS: Card[] = [
  { id: 1, mode: 'request_organize', title: '요청 핵심 파악·정리', desc: '받은 요청을 액션·마감·자료로 정리', active: true, Icon: Inbox },
  { id: 2, mode: 'format_convert', title: '남의 문서 → 우리 양식 보고서', desc: '외부 문서와 우리 양식으로 보고서 생성', active: true, Icon: ArrowRightLeft },
  { id: 3, mode: 'new_draft', title: '기존 문서 → 새 초안', desc: '우리 과거 자료 기반 새 초안', active: false, Icon: FilePlus },
  { id: 4, mode: 'attachment_edit', title: '첨부 문서 수정·보완', desc: '작성 중 문서 보완', active: false, Icon: FileEdit },
  { id: 5, mode: 'accounting_classify', title: '통장·거래내역 → 회계 분류', desc: '계정과목 자동 분류', active: true, Icon: Calculator },
  { id: 6, mode: 'form_fill', title: '상대 양식에 우리 자료', desc: '빈 양식 채우기', active: false, Icon: ClipboardList },
  { id: 7, mode: 'meeting_notes', title: '회의 음성 → 회의록', desc: '녹음 기반 회의록', active: false, Icon: Mic },
  { id: 8, mode: 'data_insight', title: '데이터 → 인사이트', desc: '수치 요약·분석', active: false, Icon: BarChart3 },
];

export function CardGrid({ onCardSelect }: { onCardSelect: (mode: CardMode) => void }) {
  return (
    <section aria-label="Butler card grid" data-testid="d4-card-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 12 }}>
      {CARDS.map(({ id, mode, title, desc, active, Icon }) => (
        <button
          key={id}
          data-testid={`card-${id}`}
          disabled={!active}
          onClick={() => active && onCardSelect(mode)}
          style={{ position: 'relative', minHeight: 132, padding: 16, borderRadius: 14, border: active ? '2px solid var(--color-brand-primary)' : '1px solid var(--color-border-subtle)', background: active ? 'var(--color-bg-input)' : 'var(--color-bg-app)', opacity: active ? 1 : 0.48, cursor: active ? 'pointer' : 'not-allowed', textAlign: 'left' }}
        >
          <Icon size={24} aria-hidden />
          <strong style={{ display: 'block', marginTop: 10, fontSize: 14 }}>{title}</strong>
          <span style={{ display: 'block', marginTop: 6, fontSize: 12, color: 'var(--color-text-secondary)' }}>{desc}</span>
          {!active && <span style={{ position: 'absolute', top: 10, right: 10, fontSize: 11, color: 'var(--color-text-secondary)' }}>준비 중</span>}
        </button>
      ))}
    </section>
  );
}
