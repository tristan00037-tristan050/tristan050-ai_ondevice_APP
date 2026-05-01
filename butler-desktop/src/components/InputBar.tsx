import React, { useState, useRef } from 'react';
import type { FileGrade } from '../types';

interface PrecheckResult {
  grade: FileGrade;
  message?: string;
}

interface InputBarProps {
  cardMode?: number | null;
  onSubmit: (text: string, files: File[]) => void;
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

async function defaultVoiceFn(): Promise<string> {
  try {
    const { invoke } = await import('@tauri-apps/api/core');
    return (await invoke('dictation_start')) as string;
  } catch {
    return '';
  }
}

export function InputBar({
  cardMode,
  onSubmit,
  maxLength = 4000,
  precheckUrl = '/api/precheck',
  invokeVoice = defaultVoiceFn,
}: InputBarProps) {
  const [text, setText] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [teamHubGuide, setTeamHubGuide] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleTextChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    setText(val.slice(0, maxLength));
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
    const dropped = Array.from(e.dataTransfer.files);
    dropped.forEach(processFile);
  };

  const handleVoice = async () => {
    const transcribed = await invokeVoice();
    if (transcribed) setText(prev => (prev + transcribed).slice(0, maxLength));
  };

  const handleSubmit = () => {
    if (text.trim() || files.length > 0) {
      onSubmit(text, files);
      setText('');
      setFiles([]);
    }
  };

  return (
    <div data-testid="input-bar">
      <div
        data-testid="drop-zone"
        onDrop={handleDrop}
        onDragOver={e => { e.preventDefault(); setIsDragging(true); }}
        onDragLeave={() => setIsDragging(false)}
        style={{ border: isDragging ? '2px dashed #1890ff' : '2px dashed #ddd', padding: 8, borderRadius: 8 }}
      >
        <button data-testid="attach-btn" onClick={() => fileInputRef.current?.click()}>
          📎 자료 첨부
        </button>
        <input ref={fileInputRef} type="file" hidden multiple onChange={e => Array.from(e.target.files ?? []).forEach(processFile)} />
        <button data-testid="voice-btn" onClick={handleVoice}>
          🎙️ 음성 입력
        </button>
        {files.length > 0 && (
          <ul data-testid="file-list">
            {files.map((f, i) => <li key={i}>{f.name}</li>)}
          </ul>
        )}
        {teamHubGuide && (
          <div data-testid="team-hub-guide" style={{ color: '#f5222d', marginTop: 8 }}>
            파일이 너무 큽니다. Team Hub에서 처리해주세요.
          </div>
        )}
      </div>
      <textarea
        data-testid="text-input"
        value={text}
        onChange={handleTextChange}
        placeholder="무엇을 도와드릴까요? 자유롭게…"
        maxLength={maxLength}
        rows={3}
        style={{ width: '100%', marginTop: 8, resize: 'vertical' }}
      />
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ color: '#999', fontSize: 12 }}>{text.length}/{maxLength}</span>
        <button data-testid="send-btn" onClick={handleSubmit}>전송</button>
      </div>
    </div>
  );
}
