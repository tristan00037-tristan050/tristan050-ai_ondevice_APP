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

export const CARDS = [
  { id: 1, Icon: Inbox, title: '요청 핵심 파악·정리', desc: '받은 메일/메시지 → 무엇을·언제까지·필요자료', active: true },
  { id: 2, Icon: ArrowRightLeft, title: '남의 문서 → 우리 양식', desc: '외부 문서 + 우리 과거 양식', active: false },
  { id: 3, Icon: FilePlus, title: '기존 문서 기반 새 초안', desc: '우리 과거 자료 + 새 상황', active: false },
  { id: 4, Icon: FileEdit, title: '첨부 문서 수정·보완', desc: '작성 중 문서 → 빠진 내용·수정안', active: false },
  { id: 5, Icon: Calculator, title: '통장·거래내역 → 회계 분류', desc: '계정과목 자동 분류', active: true },
  { id: 6, Icon: ClipboardList, title: '상대 양식에 우리 자료 채우기', desc: '빈 양식 + 우리 자료', active: false },
  { id: 7, Icon: Mic, title: '회의 음성 → 회의록', desc: '녹음 파일 → 회의록 자동 작성', active: false },
  { id: 8, Icon: BarChart3, title: '데이터 → 인사이트', desc: '수치 데이터 → 요약·분석', active: false },
];

interface HomeScreenProps {
  onCardSelect?: (cardId: number | null) => void;
  children?: React.ReactNode;
}

export function HomeScreen({ onCardSelect, children }: HomeScreenProps) {
  const [activeCard, setActiveCard] = useState<number | null>(null);

  const handleCardClick = (cardId: number, active: boolean) => {
    if (!active) return;
    const next = activeCard === cardId ? null : cardId;
    setActiveCard(next);
    onCardSelect?.(next);
  };

  const handleCardKeyDown = (e: React.KeyboardEvent, cardId: number, active: boolean) => {
    if (!active) return;
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      handleCardClick(cardId, active);
    }
  };

  return (
    <div data-testid="home-screen">
      <section>
        <h2>자주 쓰는 작업</h2>
        <div
          data-testid="card-grid"
          style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}
        >
          {CARDS.map(card => {
            const { Icon } = card;
            const isActive = activeCard === card.id;
            return (
              <button
                key={card.id}
                data-testid={`card-${card.id}`}
                aria-pressed={card.active ? isActive : undefined}
                disabled={!card.active}
                onClick={() => handleCardClick(card.id, card.active)}
                onKeyDown={(e) => handleCardKeyDown(e, card.id, card.active)}
                tabIndex={card.active ? 0 : -1}
                style={{ padding: 16, cursor: card.active ? 'pointer' : 'default', borderRadius: 8, opacity: card.active ? 1 : 0.5 }}
              >
                <Icon size={20} />
                <span>{card.title}</span>
                <span style={{ fontSize: 12, color: '#666' }}>{card.desc}</span>
                {!card.active && <span style={{ fontSize: 10 }}>준비 중</span>}
              </button>
            );
          })}
        </div>

        {activeCard === 5 && (
          <div
            data-testid="bank-upload-guide"
            style={{ marginTop: 12, padding: 12, background: '#fffbe6', borderRadius: 8 }}
          >
            통장·거래내역 파일을 첨부해주세요 (PDF, CSV, 이미지 지원)
          </div>
        )}
      </section>

      {activeCard === null && (
        <div data-testid="free-input-placeholder" style={{ marginTop: 8, color: '#999' }}>
          무엇을 도와드릴까요? 자유롭게 입력하거나 위 카드를 선택하세요.
        </div>
      )}

      <div style={{ marginTop: 16 }}>{children}</div>
    </div>
  );
}
