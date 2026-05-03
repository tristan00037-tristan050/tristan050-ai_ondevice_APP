import React from 'react';
import type { Conversation } from '../../types';
import { ConversationItem } from './ConversationItem';

interface SidebarProps {
  conversations: Conversation[];
  activeConvId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onRename: (id: string, title: string) => void;
  onDeleteRequest: (id: string) => void;
  isOpen: boolean;
}

type GroupKey = 'today' | 'yesterday' | 'week' | 'month' | 'older';

interface GroupedConvs {
  today: Conversation[];
  yesterday: Conversation[];
  week: Conversation[];
  month: Conversation[];
  older: Conversation[];
}

const GROUP_LABELS: Record<GroupKey, string> = {
  today: '오늘',
  yesterday: '어제',
  week: '지난 7일',
  month: '지난 30일',
  older: '더 오래',
};

function groupConversations(convs: Conversation[]): GroupedConvs {
  const now = new Date();
  const today = new Date(now); today.setHours(0, 0, 0, 0);
  const yesterday = new Date(today); yesterday.setDate(yesterday.getDate() - 1);
  const week = new Date(today); week.setDate(today.getDate() - 7);
  const month = new Date(today); month.setDate(today.getDate() - 30);

  const groups: GroupedConvs = { today: [], yesterday: [], week: [], month: [], older: [] };

  for (const conv of convs) {
    const d = new Date(conv.updated_at);
    if (d >= today) {
      groups.today.push(conv);
    } else if (d >= yesterday) {
      groups.yesterday.push(conv);
    } else if (d >= week) {
      groups.week.push(conv);
    } else if (d >= month) {
      groups.month.push(conv);
    } else {
      groups.older.push(conv);
    }
  }

  return groups;
}

export function Sidebar({
  conversations,
  activeConvId,
  onSelect,
  onNew,
  onRename,
  onDeleteRequest,
  isOpen,
}: SidebarProps) {
  const groups = groupConversations(conversations);
  const ORDER: GroupKey[] = ['today', 'yesterday', 'week', 'month', 'older'];

  return (
    <div
      style={{
        width: isOpen ? 260 : 0,
        flexShrink: 0,
        overflow: 'hidden',
        transition: 'width 200ms ease',
        background: 'var(--color-bg-sidebar)',
        borderRight: isOpen ? '1px solid var(--color-border-subtle)' : 'none',
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
      }}
    >
      {isOpen && (
        <>
          {/* Header */}
          <div
            style={{
              padding: 'var(--space-4)',
              borderBottom: '1px solid var(--color-border-subtle)',
            }}
          >
            <button
              data-testid="new-conv-btn"
              onClick={onNew}
              style={{
                width: '100%',
                padding: 'var(--space-2) var(--space-3)',
                background: 'var(--color-brand-primary)',
                color: 'var(--color-text-on-brand)',
                border: 'none',
                borderRadius: 8,
                cursor: 'pointer',
                fontSize: 'var(--text-sm)',
                fontFamily: 'var(--font-sans)',
                fontWeight: 500,
              }}
            >
              + 새 대화
            </button>
          </div>

          {/* Conversation list */}
          <div
            style={{
              flex: 1,
              overflowY: 'auto',
              padding: 'var(--space-2)',
            }}
          >
            {conversations.length === 0 ? (
              <div
                data-testid="sidebar-empty"
                style={{
                  padding: 'var(--space-4)',
                  textAlign: 'center',
                  color: 'var(--color-text-secondary)',
                  fontSize: 'var(--text-sm)',
                }}
              >
                아직 대화가 없습니다
              </div>
            ) : (
              ORDER.map(key => {
                const items = groups[key];
                if (items.length === 0) return null;
                return (
                  <div key={key}>
                    <div
                      style={{
                        padding: '4px 10px',
                        fontSize: 'var(--text-xs)',
                        color: 'var(--color-text-secondary)',
                        fontWeight: 500,
                        marginTop: 'var(--space-2)',
                      }}
                    >
                      {GROUP_LABELS[key]}
                    </div>
                    {items.map(conv => (
                      <ConversationItem
                        key={conv.id}
                        conversation={conv}
                        isActive={conv.id === activeConvId}
                        onSelect={() => onSelect(conv.id)}
                        onRename={title => onRename(conv.id, title)}
                        onDelete={() => onDeleteRequest(conv.id)}
                      />
                    ))}
                  </div>
                );
              })
            )}
          </div>

          {/* Footer */}
          <div
            style={{
              padding: 'var(--space-3) var(--space-4)',
              borderTop: '1px solid var(--color-border-subtle)',
            }}
          >
            <button
              style={{
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                fontSize: 'var(--text-sm)',
                color: 'var(--color-text-secondary)',
              }}
            >
              ⚙️ 설정
            </button>
          </div>
        </>
      )}
    </div>
  );
}
