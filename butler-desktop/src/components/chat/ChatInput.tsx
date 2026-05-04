import React, { useState, useRef } from 'react';
import { SIDECAR_BASE } from '../../constants';
import type { FileGrade } from '../../types';

interface PrecheckResult {
  grade: FileGrade;
  message?: string;
}

interface ChatInputProps {
  onSubmit: (text: string, files: File[], cardMode: string) => void;
  onStop: () => void;
  processing: boolean;
  cardMode: string;
  disabled?: boolean;
  maxLength?: number;
  precheckUrl?: string;
  invokeVoice?: () => Promise<string>;
}

async function defaultPrecheckFn(file: File, url: string): Promise<PrecheckResult> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename: file.name, size: file.size }),
  });
  return res.json() as Promise<PrecheckResult>;
}

export function ChatInput({
  onSubmit,
  onStop,
  processing,
  cardMode,
  disabled = false,
  maxLength = 4000,
  precheckUrl = `${SIDECAR_BASE}/api/precheck`,
}: ChatInputProps) {
  const [text, setText] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [teamHubGuide, setTeamHubGuide] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [shakeActive, setShakeActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const triggerShake = () => {
    setShakeActive(true);
    setTimeout(() => setShakeActive(false), 400);
  };

  const handleTextChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setText(e.target.value.slice(0, maxLength));
  };

  const processFile = async (file: File) => {
    try {
      const result = await defaultPrecheckFn(file, precheckUrl);
      if (result.grade === 'XL' || result.grade === 'blocked') {
        setTeamHubGuide(true);
      } else {
        setFiles(prev => [...prev, file]);
        setTeamHubGuide(false);
      }
    } catch {
      setFiles(prev => [...prev, file]);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    Array.from(e.dataTransfer.files).forEach(processFile);
  };

  const handleSubmit = () => {
    if (!processing && (text.trim() || files.length > 0)) {
      onSubmit(text, files, cardMode);
      setText('');
      setFiles([]);
    } else if (!processing && !text.trim() && files.length === 0) {
      triggerShake();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Escape' && processing) {
      onStop();
      return;
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const isInputDisabled = processing || disabled;

  return (
    <div
      style={{
        padding: 'var(--space-4)',
        background: 'var(--color-bg-app)',
      }}
    >
      <div
        data-testid="chat-input-wrapper"
        style={{
          maxWidth: 760,
          margin: '0 auto',
          background: isInputDisabled ? '#F5F5F5' : 'var(--color-bg-input)',
          border: shakeActive
            ? '2px solid var(--color-brand-primary)'
            : '1px solid var(--color-border-subtle)',
          borderRadius: 12,
          padding: 'var(--space-3) var(--space-4)',
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-2)',
          animation: shakeActive ? 'shakeX 0.4s ease' : 'none',
        }}
      >
        <div
          data-testid="drop-zone"
          onDrop={handleDrop}
          onDragOver={e => { e.preventDefault(); setIsDragging(true); }}
          onDragLeave={() => setIsDragging(false)}
          style={{
            border: isDragging ? '2px dashed var(--color-brand-primary)' : '2px dashed transparent',
            borderRadius: 8,
            transition: 'border-color 150ms ease',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
            <button
              data-testid="attach-btn"
              onClick={() => fileInputRef.current?.click()}
              disabled={isInputDisabled}
              style={{
                background: 'none',
                border: '1px solid var(--color-border-subtle)',
                borderRadius: 6,
                padding: '4px 10px',
                cursor: isInputDisabled ? 'not-allowed' : 'pointer',
                fontSize: 'var(--text-xs)',
                color: 'var(--color-text-secondary)',
              }}
            >
              📎 첨부
            </button>
            <input
              ref={fileInputRef}
              type="file"
              hidden
              multiple
              onChange={e => Array.from(e.target.files ?? []).forEach(processFile)}
            />
          </div>

          {files.length > 0 && (
            <ul
              data-testid="file-list"
              style={{
                margin: '4px 0 0',
                padding: '0 0 0 var(--space-4)',
                fontSize: 'var(--text-xs)',
                color: 'var(--color-text-secondary)',
              }}
            >
              {files.map((f, i) => (
                <li key={i}>{f.name}</li>
              ))}
            </ul>
          )}

          {teamHubGuide && (
            <div
              data-testid="team-hub-guide"
              style={{
                marginTop: 'var(--space-2)',
                fontSize: 'var(--text-xs)',
                color: 'var(--color-error)',
              }}
            >
              파일이 너무 큽니다. Team Hub에서 처리해주세요.
            </div>
          )}
        </div>

        {/* Processing indicator: shown when disabled textarea placeholder is unreliable in WKWebView */}
        {processing && (
          <p
            data-testid="processing-status-text"
            style={{
              margin: '0 0 var(--space-1)',
              fontSize: 'var(--text-sm)',
              color: 'var(--color-text-secondary)',
              fontStyle: 'italic',
            }}
          >
            Butler가 답변을 준비하고 있습니다...
          </p>
        )}

        <div style={{ display: 'flex', alignItems: 'flex-end', gap: 'var(--space-2)' }}>
          <textarea
            data-testid="text-input"
            value={text}
            onChange={handleTextChange}
            onKeyDown={handleKeyDown}
            disabled={isInputDisabled}
            placeholder="무엇을 도와드릴까요? 자유롭게…"
            maxLength={maxLength}
            rows={3}
            style={{
              flex: 1,
              resize: 'none',
              border: 'none',
              outline: 'none',
              background: 'transparent',
              fontSize: 'var(--text-base)',
              fontFamily: 'var(--font-sans)',
              color: 'var(--color-text-primary)',
              lineHeight: 1.6,
            }}
          />

          {processing ? (
            <button
              data-testid="cancel-btn"
              onClick={onStop}
              style={{
                width: 32,
                height: 32,
                flexShrink: 0,
                background: 'var(--color-error)',
                color: '#FFFFFF',
                border: 'none',
                borderRadius: 8,
                cursor: 'pointer',
                fontSize: 14,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
              aria-label="정지"
            >
              ⏹
            </button>
          ) : (
            <button
              data-testid="send-btn"
              onClick={handleSubmit}
              disabled={disabled || (!text.trim() && files.length === 0)}
              style={{
                width: 32,
                height: 32,
                flexShrink: 0,
                background: disabled || (!text.trim() && files.length === 0)
                  ? 'var(--color-border-subtle)'
                  : 'var(--color-brand-primary)',
                color: '#FFFFFF',
                border: 'none',
                borderRadius: 8,
                cursor: disabled || (!text.trim() && files.length === 0) ? 'not-allowed' : 'pointer',
                fontSize: 14,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
              aria-label="전송"
            >
              ↑
            </button>
          )}
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-secondary)' }}>
            {text.length}/{maxLength}
          </span>
        </div>
      </div>
    </div>
  );
}
