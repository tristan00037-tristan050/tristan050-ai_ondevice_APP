import React, { useState, useRef, useEffect } from 'react';
import type { Conversation } from '../../types';

interface ConversationItemProps {
  conversation: Conversation;
  isActive: boolean;
  onSelect: () => void;
  onRename: (newTitle: string) => void;
  onDelete: () => void;
}

export function ConversationItem({
  conversation,
  isActive,
  onSelect,
  onRename,
  onDelete,
}: ConversationItemProps) {
  const [editMode, setEditMode] = useState(false);
  const [editValue, setEditValue] = useState(conversation.title);
  const [menuOpen, setMenuOpen] = useState(false);
  const [isHovered, setIsHovered] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  // Auto focus + select all when entering edit mode
  useEffect(() => {
    if (editMode && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editMode]);

  // Close menu when clicking outside
  useEffect(() => {
    if (!menuOpen) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [menuOpen]);

  const commitRename = () => {
    const trimmed = editValue.trim();
    if (trimmed) {
      onRename(trimmed);
    } else {
      // Reject empty — revert to original
      setEditValue(conversation.title);
    }
    setEditMode(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      commitRename();
    } else if (e.key === 'Escape') {
      setEditValue(conversation.title);
      setEditMode(false);
    }
  };

  const handleItemClick = (e: React.MouseEvent) => {
    if (editMode) return;
    onSelect();
  };

  const handleDoubleClick = (e: React.MouseEvent) => {
    e.preventDefault();
    setEditValue(conversation.title);
    setEditMode(true);
  };

  return (
    <div
      data-testid={`conv-item-${conversation.id}`}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      style={{
        position: 'relative',
        borderRadius: 8,
        background: isActive ? 'rgba(16,54,125,0.1)' : 'transparent',
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        padding: '8px 10px',
        transition: 'background 150ms ease',
      }}
    >
      {editMode ? (
        <input
          ref={inputRef}
          type="text"
          data-testid="conv-rename-input"
          aria-label="대화 이름 변경"
          value={editValue}
          maxLength={100}
          onChange={e => setEditValue(e.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={commitRename}
          style={{
            flex: 1,
            border: '1px solid var(--color-brand-primary)',
            borderRadius: 4,
            padding: '2px 6px',
            fontSize: 'var(--text-sm)',
            fontFamily: 'var(--font-sans)',
            outline: 'none',
            color: 'var(--color-text-primary)',
          }}
          onClick={e => e.stopPropagation()}
        />
      ) : (
        <span
          onClick={handleItemClick}
          onDoubleClick={handleDoubleClick}
          style={{
            flex: 1,
            fontSize: 'var(--text-sm)',
            color: isActive ? 'var(--color-brand-primary)' : 'var(--color-text-primary)',
            fontWeight: isActive ? 600 : 400,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {conversation.title}
        </span>
      )}

      {!editMode && isHovered && (
        <div style={{ position: 'relative' }} ref={menuRef}>
          <button
            data-testid="conv-menu-btn"
            onClick={e => {
              e.stopPropagation();
              setMenuOpen(o => !o);
            }}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              padding: '2px 4px',
              borderRadius: 4,
              color: 'var(--color-text-secondary)',
              fontSize: 16,
              lineHeight: 1,
            }}
            aria-label="대화 메뉴"
          >
            ⋯
          </button>

          {menuOpen && (
            <div
              style={{
                position: 'absolute',
                right: 0,
                top: '100%',
                background: '#FFFFFF',
                border: '1px solid var(--color-border-subtle)',
                borderRadius: 8,
                boxShadow: '0 4px 12px rgba(0,0,0,0.12)',
                zIndex: 100,
                minWidth: 120,
                overflow: 'hidden',
              }}
            >
              <button
                data-testid="rename-menu-item"
                onClick={e => {
                  e.stopPropagation();
                  setMenuOpen(false);
                  setEditValue(conversation.title);
                  setEditMode(true);
                }}
                style={{
                  display: 'block',
                  width: '100%',
                  textAlign: 'left',
                  padding: '8px 12px',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: 'var(--text-sm)',
                  color: 'var(--color-text-primary)',
                }}
              >
                이름 변경
              </button>
              <button
                data-testid="delete-menu-item"
                onClick={e => {
                  e.stopPropagation();
                  setMenuOpen(false);
                  onDelete();
                }}
                style={{
                  display: 'block',
                  width: '100%',
                  textAlign: 'left',
                  padding: '8px 12px',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: 'var(--text-sm)',
                  color: 'var(--color-error)',
                }}
              >
                삭제
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
