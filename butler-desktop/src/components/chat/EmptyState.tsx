import React, { useState } from 'react';

const CARDS = [
  { id: 1, icon: '📥', title: '요청 핵심 파악·정리', desc: '받은 메일/메시지 → 무엇을·언제까지·필요자료', mode: 'request_organize' },
  { id: 2, icon: '🔄', title: '남의 문서 → 우리 양식', desc: '외부 문서 + 우리 과거 양식', mode: 'format_convert' },
  { id: 3, icon: '📄', title: '기존 문서 기반 새 초안', desc: '우리 과거 자료 + 새 상황', mode: 'new_draft' },
  { id: 4, icon: '📝', title: '첨부 문서 수정·보완', desc: '작성 중 문서 → 빠진 내용·수정안', mode: 'attachment_edit' },
  { id: 5, icon: '💰', title: '통장·거래내역 → 회계 분류', desc: '계정과목 자동 분류', mode: 'accounting_classify' },
  { id: 6, icon: '📋', title: '상대 양식에 우리 자료 채우기', desc: '빈 양식 + 우리 자료', mode: 'form_fill' },
] as const;

interface EmptyStateProps {
  onCardSelect?: (mode: string) => void;
}

export function EmptyState({ onCardSelect }: EmptyStateProps) {
  const [activeMode, setActiveMode] = useState<string | null>(null);
  const [hoveredId, setHoveredId] = useState<number | null>(null);

  const handleCardClick = (mode: string) => {
    setActiveMode(prev => (prev === mode ? null : mode));
    onCardSelect?.(mode);
  };

  const activeCard = CARDS.find(c => c.mode === activeMode) ?? null;

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
          gridTemplateColumns: 'repeat(3, 1fr)',
          gap: 'var(--space-3)',
          maxWidth: 760,
          width: '100%',
        }}
      >
        {CARDS.map(card => {
          const isActive = activeMode === card.mode;
          const isHovered = hoveredId === card.id;
          return (
            <button
              key={card.id}
              data-testid={`card-${card.id}`}
              aria-pressed={isActive}
              onClick={() => handleCardClick(card.mode)}
              onMouseEnter={() => setHoveredId(card.id)}
              onMouseLeave={() => setHoveredId(null)}
              style={{
                padding: 'var(--space-4)',
                cursor: 'pointer',
                borderRadius: 12,
                border: isActive || isHovered
                  ? `2px solid var(--color-brand-primary)`
                  : '2px solid var(--color-border-subtle)',
                background: isActive
                  ? 'rgba(16,54,125,0.06)'
                  : 'var(--color-bg-input)',
                textAlign: 'left',
                display: 'flex',
                flexDirection: 'column',
                gap: 'var(--space-1)',
                transform: isHovered ? 'scale(1.02)' : 'scale(1)',
                transition: 'transform 150ms ease-out, border-color 150ms ease-out, background 150ms ease-out',
              }}
            >
              <span style={{ fontSize: 'var(--text-lg)' }}>{card.icon}</span>
              <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text-primary)' }}>
                {card.title}
              </span>
              <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>
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
            maxWidth: 760,
            width: '100%',
          }}
        >
          통장·거래내역 파일을 첨부해주세요 (PDF, CSV, 이미지 지원)
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
