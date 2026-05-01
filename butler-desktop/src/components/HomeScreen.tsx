import React, { useState } from 'react';

export const CARDS = [
  { id: 1, icon: '📥', title: '요청 핵심 파악·정리', desc: '받은 메일/메시지 → 무엇을·언제까지·필요자료' },
  { id: 2, icon: '🔄', title: '남의 문서 → 우리 양식', desc: '외부 문서 + 우리 과거 양식' },
  { id: 3, icon: '📄', title: '기존 문서 기반 새 초안', desc: '우리 과거 자료 + 새 상황' },
  { id: 4, icon: '📝', title: '첨부 문서 수정·보완', desc: '작성 중 문서 → 빠진 내용·수정안' },
  { id: 5, icon: '💰', title: '통장·거래내역 → 회계 분류', desc: '계정과목 자동 분류' },
  { id: 6, icon: '📋', title: '상대 양식에 우리 자료 채우기', desc: '빈 양식 + 우리 자료' },
] as const;

interface HomeScreenProps {
  onSubmit?: (text: string, cardId: number | null) => void;
  onCardSelect?: (cardId: number | null) => void;
}

export function HomeScreen({ onSubmit, onCardSelect }: HomeScreenProps) {
  const [activeCard, setActiveCard] = useState<number | null>(null);
  const [inputText, setInputText] = useState('');

  const handleCardClick = (cardId: number) => {
    const next = activeCard === cardId ? null : cardId;
    setActiveCard(next);
    onCardSelect?.(next);
  };

  const handleCardKeyDown = (e: React.KeyboardEvent, cardId: number) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      handleCardClick(cardId);
    }
  };

  const handleSubmit = () => {
    if (inputText.trim()) onSubmit?.(inputText, activeCard);
  };

  return (
    <div data-testid="home-screen">
      <section>
        <h2>자주 쓰는 작업</h2>
        <div data-testid="card-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
          {CARDS.map(card => (
            <button
              key={card.id}
              data-testid={`card-${card.id}`}
              aria-pressed={activeCard === card.id}
              onClick={() => handleCardClick(card.id)}
              onKeyDown={(e) => handleCardKeyDown(e, card.id)}
              tabIndex={0}
              style={{ padding: 16, cursor: 'pointer', borderRadius: 8 }}
            >
              <span role="img" aria-label={card.title}>{card.icon}</span>
              <span>{card.title}</span>
              <span style={{ fontSize: 12, color: '#666' }}>{card.desc}</span>
            </button>
          ))}
        </div>

        {activeCard === 5 && (
          <div data-testid="bank-upload-guide" style={{ marginTop: 12, padding: 12, background: '#fffbe6', borderRadius: 8 }}>
            통장·거래내역 파일을 첨부해주세요 (PDF, CSV, 이미지 지원)
          </div>
        )}
      </section>

      {activeCard === null && (
        <div data-testid="free-input-placeholder" style={{ marginTop: 8, color: '#999' }}>
          무엇을 도와드릴까요? 자유롭게 입력하거나 위 카드를 선택하세요.
        </div>
      )}

      <div style={{ marginTop: 16 }}>
        <textarea
          data-testid="main-input"
          value={inputText}
          onChange={e => setInputText(e.target.value)}
          placeholder="무엇을 도와드릴까요? 자유롭게…"
          maxLength={4000}
          rows={3}
          style={{ width: '100%', resize: 'vertical' }}
        />
        <button data-testid="submit-btn" onClick={handleSubmit}>전송</button>
      </div>
    </div>
  );
}
