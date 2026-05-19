/**
 * @deprecated D-4 Card2 v1.1 — `src/components/v1_1/CardGrid.tsx` 로 대체됨.
 * App.tsx 는 더 이상 본 컴포넌트를 사용하지 않는다. 기존 테스트 호환을 위해
 * 파일만 유지하며, P3~P11 잔여 큐의 테스트 마이그레이션 후 제거 예정.
 */
import React, { useState } from 'react';
import {
  Inbox,
  ArrowRightLeft,
  FilePlus,
  FileEdit,
  Calculator,
  ClipboardList,
  Mic,
  BarChart3,
} from 'lucide-react';

const CARDS = [
  {
    id: 1,
    Icon: Inbox,
    title: '요청 핵심 파악·정리',
    desc: '받은 메일/메시지 → 무엇을·언제까지·필요자료',
    mode: 'request_organize',
    active: true,
  },
  {
    id: 2,
    Icon: ArrowRightLeft,
    title: '남의 문서 → 우리 양식',
    desc: '외부 문서 + 우리 과거 양식',
    mode: 'format_convert',
    active: true,
  },
  {
    id: 3,
    Icon: FilePlus,
    title: '기존 문서 기반 새 초안',
    desc: '우리 과거 자료 + 새 상황',
    mode: 'new_draft',
    active: false,
  },
  {
    id: 4,
    Icon: FileEdit,
    title: '첨부 문서 수정·보완',
    desc: '작성 중 문서 → 빠진 내용·수정안',
    mode: 'attachment_edit',
    active: false,
  },
  {
    id: 5,
    Icon: Calculator,
    title: '통장·거래내역 → 회계 분류',
    desc: '계정과목 자동 분류',
    mode: 'accounting_classify',
    active: true,
  },
  {
    id: 6,
    Icon: ClipboardList,
    title: '상대 양식에 우리 자료 채우기',
    desc: '빈 양식 + 우리 자료',
    mode: 'form_fill',
    active: false,
  },
  {
    id: 7,
    Icon: Mic,
    title: '회의 음성 → 회의록',
    desc: '녹음 파일 → 회의록 자동 작성',
    mode: 'meeting_notes',
    active: false,
  },
  {
    id: 8,
    Icon: BarChart3,
    title: '데이터 → 인사이트',
    desc: '수치 데이터 → 요약·분석',
    mode: 'data_insight',
    active: false,
  },
];

interface EmptyStateProps {
  onCardSelect?: (mode: string | null) => void;
  compact?: boolean;
}

export function EmptyState({ onCardSelect, compact = false }: EmptyStateProps) {
  const [activeMode, setActiveMode] = useState<string | null>(null);
  const [hoveredId, setHoveredId] = useState<number | null>(null);

  const handleCardClick = (card: (typeof CARDS)[number]) => {
    if (!card.active) return;
    const next = activeMode === card.mode ? null : card.mode;
    setActiveMode(next);
    onCardSelect?.(next);
  };

  const activeCard = CARDS.find(c => c.mode === activeMode) ?? null;

  if (compact) {
    return (
      <div
        style={{
          padding: 'var(--space-2) var(--space-4)',
          borderBottom: '1px solid var(--color-border-subtle)',
          background: 'var(--color-bg-input)',
        }}
      >
        <div
          data-testid="card-grid"
          style={{
            display: 'flex',
            gap: 'var(--space-2)',
            flexWrap: 'wrap',
          }}
        >
          {CARDS.map(card => {
            const { Icon } = card;
            const isActive = activeMode === card.mode;
            return (
              <button
                key={card.id}
                data-testid={`card-${card.id}`}
                aria-pressed={card.active ? isActive : undefined}
                disabled={!card.active}
                onClick={() => handleCardClick(card)}
                onMouseEnter={() => setHoveredId(card.id)}
                onMouseLeave={() => setHoveredId(null)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  padding: '4px 10px',
                  borderRadius: 8,
                  border: isActive
                    ? '1.5px solid var(--color-brand-primary)'
                    : '1.5px solid var(--color-border-subtle)',
                  background: isActive ? 'rgba(16,54,125,0.06)' : 'var(--color-bg-app)',
                  cursor: card.active ? 'pointer' : 'default',
                  opacity: card.active ? 1 : 0.45,
                  fontSize: 'var(--text-xs)',
                  color: 'var(--color-text-primary)',
                  transition: 'border-color 150ms ease-out',
                  outline: hoveredId === card.id && card.active ? '2px solid var(--color-brand-primary)' : 'none',
                }}
                title={card.active ? card.title : `${card.title} (준비 중)`}
              >
                <Icon size={14} />
                <span>{card.title}</span>
                {!card.active && (
                  <span style={{ fontSize: 10, color: 'var(--color-text-secondary)', marginLeft: 2 }}>
                    준비 중
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 'var(--space-8)',
        overflowY: 'auto',
      }}
    >
      <h2
        style={{
          fontSize: 'var(--text-xl)',
          fontWeight: 600,
          color: 'var(--color-text-primary)',
          marginBottom: 'var(--space-2)',
          textAlign: 'center',
        }}
      >
        이런 일을 도와드릴 수 있어요
      </h2>
      <p
        style={{
          fontSize: 'var(--text-sm)',
          color: 'var(--color-text-secondary)',
          marginBottom: 'var(--space-6)',
          textAlign: 'center',
        }}
      >
        아래 카드를 선택하거나 직접 입력하세요
      </p>

      <div
        data-testid="card-grid"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: 'var(--space-3)',
          maxWidth: 860,
          width: '100%',
        }}
      >
        {CARDS.map(card => {
          const { Icon } = card;
          const isActive = activeMode === card.mode;
          const isHovered = hoveredId === card.id;
          return (
            <button
              key={card.id}
              data-testid={`card-${card.id}`}
              aria-pressed={card.active ? isActive : undefined}
              disabled={!card.active}
              onClick={() => handleCardClick(card)}
              onMouseEnter={() => setHoveredId(card.id)}
              onMouseLeave={() => setHoveredId(null)}
              style={{
                position: 'relative',
                padding: 'var(--space-4)',
                cursor: card.active ? 'pointer' : 'default',
                borderRadius: 12,
                border:
                  isActive || (isHovered && card.active)
                    ? '2px solid var(--color-brand-primary)'
                    : '2px solid var(--color-border-subtle)',
                background: isActive
                  ? 'rgba(16,54,125,0.06)'
                  : 'var(--color-bg-input)',
                textAlign: 'left',
                display: 'flex',
                flexDirection: 'column',
                gap: 'var(--space-1)',
                opacity: card.active ? 1 : 0.5,
                transform: isHovered && card.active ? 'scale(1.02)' : 'scale(1)',
                transition:
                  'transform 150ms ease-out, border-color 150ms ease-out, background 150ms ease-out',
              }}
            >
              {!card.active && (
                <span
                  style={{
                    position: 'absolute',
                    top: 6,
                    right: 8,
                    fontSize: 9,
                    fontWeight: 600,
                    color: 'var(--color-text-secondary)',
                    background: 'var(--color-border-subtle)',
                    padding: '1px 5px',
                    borderRadius: 4,
                  }}
                >
                  준비 중
                </span>
              )}
              <Icon
                size={24}
                style={{ color: card.active ? 'var(--color-brand-primary)' : 'var(--color-text-secondary)' }}
              />
              <span
                style={{
                  fontSize: 'var(--text-sm)',
                  fontWeight: 600,
                  color: 'var(--color-text-primary)',
                }}
              >
                {card.title}
              </span>
              <span
                style={{
                  fontSize: 'var(--text-xs)',
                  color: 'var(--color-text-secondary)',
                }}
              >
                {card.desc}
              </span>
            </button>
          );
        })}
      </div>

      {activeCard?.mode === 'accounting_classify' && (
        <div
          data-testid="bank-upload-guide"
          style={{
            marginTop: 'var(--space-4)',
            padding: 'var(--space-3)',
            background: '#fffbe6',
            border: '1px solid #ffe58f',
            borderRadius: 8,
            fontSize: 'var(--text-sm)',
            color: 'var(--color-warning)',
            maxWidth: 860,
            width: '100%',
          }}
        >
          통장·거래내역 파일을 첨부해주세요 (.xlsx, .xls, .csv 지원)
        </div>
      )}

      {activeMode === null && (
        <div
          data-testid="free-input-placeholder"
          style={{
            marginTop: 'var(--space-4)',
            color: 'var(--color-text-secondary)',
            fontSize: 'var(--text-sm)',
            textAlign: 'center',
          }}
        >
          무엇을 도와드릴까요?
        </div>
      )}
    </div>
  );
}
