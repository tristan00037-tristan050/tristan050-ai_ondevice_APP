import React, { useEffect, useRef, useState } from 'react';
import { Inbox, ArrowRightLeft, FilePlus, FileSearch, Calculator, ClipboardList, Mic, BarChart3, type LucideIcon } from 'lucide-react';

type CardMode = 'request_organize' | 'format_convert' | 'new_draft' | 'document_review' | 'accounting_classify' | 'form_fill' | 'meeting_notes' | 'data_insight';

type Card = {
  id: number;
  mode: CardMode;
  title: string;
  desc: string;
  active: boolean;
  Icon: LucideIcon;
};

// box6/box4 are activated by default (product default ON) so any build ships them on —
// no build-time env needed. An explicit VITE_BUTLER_BOX{6,4}_* === '0' still force-disables
// (kill switch). #839/#840 landed these feature-complete but flag-off; this promotes the
// default to on. box7/box8 remain unimplemented (active:false) and are unaffected.
export const BOX6_FORM_FILL_ENABLED = import.meta.env.VITE_BUTLER_BOX6_FORM_FILL !== '0';
export const BOX4_DOCUMENT_REVIEW_ENABLED = import.meta.env.VITE_BUTLER_BOX4_DOCUMENT_REVIEW !== '0';

const CARDS: Card[] = [
  { id: 1, mode: 'request_organize', title: '요청 핵심 파악·정리', desc: '받은 요청을 액션·마감·자료로 정리', active: true, Icon: Inbox },
  { id: 2, mode: 'format_convert', title: '남의 문서 → 우리 양식 보고서', desc: '외부 문서와 우리 양식으로 보고서 생성', active: true, Icon: ArrowRightLeft },
  { id: 3, mode: 'new_draft', title: '기존 문서 → 새 초안', desc: '우리 과거 자료 기반 새 초안', active: true, Icon: FilePlus },
  { id: 4, mode: 'document_review', title: '첨부 문서 수정·보완', desc: '작성 중 문서 보완', active: BOX4_DOCUMENT_REVIEW_ENABLED, Icon: FileSearch },
  { id: 5, mode: 'accounting_classify', title: '통장·거래내역 → 회계 분류', desc: '계정과목 자동 분류', active: true, Icon: Calculator },
  { id: 6, mode: 'form_fill', title: '상대 양식에 우리 자료', desc: '빈 양식 채우기', active: BOX6_FORM_FILL_ENABLED, Icon: ClipboardList },
  { id: 7, mode: 'meeting_notes', title: '회의 음성 → 회의록', desc: '녹음 기반 회의록', active: false, Icon: Mic },
  { id: 8, mode: 'data_insight', title: '데이터 → 인사이트', desc: '수치 요약·분석', active: false, Icon: BarChart3 },
];

export function CardGrid({ onCardSelect, compact = false }: { onCardSelect: (mode: CardMode) => void; compact?: boolean }) {
  const ref = useRef<HTMLElement>(null);
  const [columns,setColumns]=useState(4);
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const update = () => {
      const width = node.getBoundingClientRect().width;
      setColumns(compact ? (width < 520 ? 2 : width < 900 ? 4 : 8) : (width < 560 ? 1 : width < 900 ? 2 : 4));
    };
    update();
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(update);
    observer.observe(node);
    return () => observer.disconnect();
  }, [compact]);
  return (
    <section ref={ref} className={compact?'home-card-grid compact':'home-card-grid'} aria-label="Butler card grid" data-testid="card-grid" data-card-grid-version="v1.3" style={{ display: 'grid', gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`, gap: compact?6:12 }}>
      {CARDS.map(({ id, mode, title, desc, active, Icon }) => (
        <button
          key={id}
          data-testid={`card-${id}`}
          disabled={!active}
          aria-label={title}
          onClick={() => active && onCardSelect(mode)}
          style={{ position: 'relative', minHeight: compact?40:132, padding: compact?8:16, borderRadius: 14, border: active ? '2px solid var(--color-brand-primary)' : '1px solid var(--color-border-subtle)', background: active ? 'var(--color-bg-input)' : 'var(--color-bg-app)', opacity: active ? 1 : 0.48, cursor: active ? 'pointer' : 'not-allowed', textAlign: 'left' }}
        >
          {!compact&&<Icon size={24} aria-hidden />}
          <strong style={{ display: 'block', marginTop: compact?0:10, fontSize: 14 }}>{compact?id:title}</strong>
          {!compact&&<span style={{ display: 'block', marginTop: 6, fontSize: 12, color: 'var(--color-text-secondary)' }}>{desc}</span>}
          {!active && <span style={{ position: 'absolute', top: 10, right: 10, fontSize: 11, color: 'var(--color-text-secondary)' }}>준비 중</span>}
        </button>
      ))}
    </section>
  );
}
