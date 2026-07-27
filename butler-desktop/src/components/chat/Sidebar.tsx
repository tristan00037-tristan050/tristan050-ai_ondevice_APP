import React, { useMemo, useState } from 'react';
import type { Conversation, FolderRecord } from '../../types';
import { ConversationItem } from './ConversationItem';

interface Props {
  conversations: Conversation[];
  trashedConversations: Conversation[];
  folders: FolderRecord[];
  activeConvId: string | null;
  isOpen: boolean;
  disabled: boolean;
  onSelect: (id: string) => void;
  onNew: () => void;
  onRename: (id: string, title: string) => void;
  onDeleteRequest: (id: string) => void;
  onCreateFolder: (name: string, parentId: string | null) => void;
  onRenameFolder: (folder: FolderRecord, name: string) => void;
  onDeleteFolder: (folder: FolderRecord) => void;
  onMove: (conversation: Conversation, folderId: string) => void;
  onRestore: (conversation: Conversation) => void;
  onPermanentDelete: (conversation: Conversation) => void;
  onOpenSettings: () => void;
  onRetry: () => void;
  onSearch: (query: string) => void;
}

export function Sidebar(props: Props) {
  const {
    conversations, trashedConversations, folders, activeConvId, isOpen, disabled,
    onSelect, onNew, onRename, onDeleteRequest, onCreateFolder, onRenameFolder,
    onDeleteFolder, onMove, onRestore, onPermanentDelete, onOpenSettings, onRetry, onSearch,
  } = props;
  const [name, setName] = useState('');
  const [parentId, setParentId] = useState('');
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [trashOpen, setTrashOpen] = useState(false);
  const [profileFilter, setProfileFilter] = useState('');
  const visible = useMemo(() => folders.filter(folder => folder.system_kind !== 'TRASH'), [folders]);
  const customFolders = visible.filter(folder => folder.system_kind === null);
  const profiles = useMemo(() => Array.from(new Set(
    conversations.map(conversation => conversation.business_profile_id).filter((value): value is string => Boolean(value)),
  )).sort(), [conversations]);
  const listedConversations = profileFilter
    ? conversations.filter(conversation => conversation.business_profile_id === profileFilter)
    : conversations;

  if (!isOpen) return <aside className="home-sidebar home-sidebar-closed" aria-hidden="true" />;

  const renderFolder = (folder: FolderRecord, depth = 0): React.ReactNode => {
    const items = listedConversations.filter(conversation => (conversation.folder_id ?? 'system-unclassified') === folder.folder_id);
    const children = customFolders.filter(child => child.parent_id === folder.folder_id);
    const open = expanded[folder.folder_id] ?? true;
    return (
      <section key={folder.folder_id} className="folder-group" style={{ '--folder-depth': depth } as React.CSSProperties}>
        <div className="folder-heading">
          <button
            className="folder-disclosure"
            aria-expanded={open}
            onClick={() => setExpanded(value => ({ ...value, [folder.folder_id]: !open }))}
          >
            <span aria-hidden="true">{open ? '−' : '+'}</span>
            <strong>{folder.display_name}</strong>
            <span>{items.length}</span>
          </button>
          {folder.system_kind === null && (
            <span className="folder-actions">
              <button
                disabled={disabled}
                aria-label={`${folder.display_name} 이름 변경`}
                onClick={() => {
                  const next = window.prompt('새 폴더 이름', folder.display_name)?.trim();
                  if (next && next !== folder.display_name) onRenameFolder(folder, next);
                }}
              >이름</button>
              <button disabled={disabled} aria-label={`${folder.display_name} 삭제`} onClick={() => onDeleteFolder(folder)}>삭제</button>
            </span>
          )}
        </div>
        {open && (
          <div>
            {items.map(conversation => (
              <div className="folder-conversation" key={conversation.id}>
                <ConversationItem
                  conversation={conversation}
                  isActive={conversation.id === activeConvId}
                  onSelect={() => onSelect(conversation.id)}
                  onRename={title => onRename(conversation.id, title)}
                  onDelete={() => onDeleteRequest(conversation.id)}
                />
                {conversation.business_profile_id && (
                  <span className="profile-badge" title="생성 당시 업무 프로필">{conversation.business_profile_id}</span>
                )}
                <select
                  aria-label={`${conversation.title} 이동`}
                  value={folder.folder_id}
                  disabled={disabled}
                  onChange={event => onMove(conversation, event.target.value)}
                >
                  {visible.map(target => <option value={target.folder_id} key={target.folder_id}>{target.display_name}</option>)}
                </select>
              </div>
            ))}
            {children.map(child => renderFolder(child, depth + 1))}
          </div>
        )}
      </section>
    );
  };

  const roots = visible.filter(folder => folder.system_kind !== null || folder.parent_id === null);

  return (
    <aside className="home-sidebar">
      <div className="home-sidebar-header">
        <button data-testid="new-conv-btn" className="primary-control" onClick={onNew}>새 대화</button>
        <input
          className="conversation-search"
          type="search"
          maxLength={200}
          placeholder="대화 제목 검색"
          aria-label="대화 제목 검색"
          onChange={event => onSearch(event.target.value)}
        />
        <label className="profile-filter-label">
          업무 프로필
          <select value={profileFilter} onChange={event => setProfileFilter(event.target.value)}>
            <option value="">전체 대화 ({conversations.length})</option>
            {profiles.map(profile => <option key={profile} value={profile}>{profile}</option>)}
          </select>
        </label>
        <form onSubmit={event => {
          event.preventDefault();
          const value = name.trim();
          if (!disabled && value) {
            onCreateFolder(value, parentId || null);
            setName('');
          }
        }}>
          <input value={name} maxLength={80} disabled={disabled} onChange={event => setName(event.target.value)} placeholder="새 폴더 이름" aria-label="새 폴더 이름" />
          <select value={parentId} disabled={disabled} onChange={event => setParentId(event.target.value)} aria-label="상위 폴더">
            <option value="">최상위</option>
            {customFolders.map(folder => <option key={folder.folder_id} value={folder.folder_id}>{folder.display_name}</option>)}
          </select>
          <button type="submit" disabled={disabled}>추가</button>
        </form>
        {disabled && <div className="read-only-notice" role="status">읽기 전용입니다. <button onClick={onRetry}>다시 연결</button></div>}
      </div>
      <nav className="folder-tree" aria-label="대화 폴더">
        {roots.map(folder => renderFolder(folder))}
        {listedConversations.length === 0 && (
          <div className="sidebar-empty">
            <p>{profileFilter ? '이 프로필에 연결된 대화가 없습니다.' : '아직 대화가 없습니다.'}</p>
            {profileFilter && <button onClick={() => setProfileFilter('')}>전체 대화 보기</button>}
          </div>
        )}
        <section className="trash-group">
          <button className="folder-disclosure" aria-expanded={trashOpen} onClick={() => setTrashOpen(open => !open)}>
            <span aria-hidden="true">{trashOpen ? '−' : '+'}</span><strong>휴지통</strong><span>{trashedConversations.length}</span>
          </button>
          {trashOpen && trashedConversations.map(conversation => (
            <div className="trash-row" key={conversation.id}>
              <span title={conversation.title}>{conversation.title}</span>
              <button disabled={disabled} onClick={() => onRestore(conversation)}>복원</button>
              <button disabled={disabled} onClick={() => onPermanentDelete(conversation)}>영구 삭제</button>
            </div>
          ))}
        </section>
      </nav>
      <footer>
        <button
          type="button"
          className="settings-entry"
          data-testid="settings-entry"
          onClick={onOpenSettings}
        >
          설정
        </button>
      </footer>
    </aside>
  );
}
