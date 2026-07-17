import { useEffect, useId, useMemo, useRef, useState } from 'react';
import type { ChartEntry } from '../../lib/accounting_review/contracts';

interface AccountComboboxProps {
  entries: ChartEntry[];
  value: string | null;
  onChange: (accountId: string | null) => void;
  disabled?: boolean;
  labelledBy: string;
}

function searchable(entry: ChartEntry): string {
  return [entry.account_code ?? '', entry.display_name, ...entry.category_path]
    .join(' ')
    .normalize('NFKC')
    .toLocaleLowerCase('ko-KR');
}

export function AccountCombobox({ entries, value, onChange, disabled = false, labelledBy }: AccountComboboxProps) {
  const rawId = useId();
  const listboxId = `account-list-${rawId.replaceAll(':', '')}`;
  const selected = useMemo(() => entries.find(entry => entry.account_id === value) ?? null, [entries, value]);
  const [query, setQuery] = useState(selected?.display_name ?? '');
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const blurTimer = useRef<number | null>(null);
  const typingRef = useRef(false);

  useEffect(() => {
    if (typingRef.current) {
      typingRef.current = false;
      return;
    }
    setQuery(selected?.display_name ?? '');
  }, [selected]);

  useEffect(() => () => {
    if (blurTimer.current !== null) window.clearTimeout(blurTimer.current);
  }, []);

  const filtered = useMemo(() => {
    const needle = query.normalize('NFKC').trim().toLocaleLowerCase('ko-KR');
    const ordered = [...entries].sort((a, b) => a.sort_order - b.sort_order);
    return needle ? ordered.filter(entry => searchable(entry).includes(needle)) : ordered;
  }, [entries, query]);

  useEffect(() => {
    if (activeIndex >= filtered.length) setActiveIndex(Math.max(filtered.length - 1, 0));
  }, [activeIndex, filtered.length]);

  const choose = (entry: ChartEntry) => {
    if (!entry.assignable || disabled) return;
    onChange(entry.account_id);
    setQuery(entry.display_name);
    setOpen(false);
  };

  const move = (delta: number) => {
    if (!filtered.length) return;
    let next = activeIndex;
    for (let tries = 0; tries < filtered.length; tries += 1) {
      next = (next + delta + filtered.length) % filtered.length;
      if (filtered[next]?.assignable) break;
    }
    setActiveIndex(next);
  };

  const active = filtered[activeIndex];
  return (
    <div className="account-combobox">
      <input
        type="text"
        role="combobox"
        aria-labelledby={labelledBy}
        aria-autocomplete="list"
        aria-expanded={open}
        aria-controls={listboxId}
        aria-activedescendant={open && active ? `${listboxId}-${active.account_id}` : undefined}
        autoComplete="off"
        disabled={disabled}
        value={query}
        placeholder="계정과목 검색"
        onChange={event => {
          const next = event.target.value;
          typingRef.current = true;
          setQuery(next);
          setOpen(true);
          setActiveIndex(0);
          if (!selected || next !== selected.display_name) onChange(null);
        }}
        onFocus={() => {
          if (blurTimer.current !== null) window.clearTimeout(blurTimer.current);
          setOpen(true);
        }}
        onBlur={() => {
          blurTimer.current = window.setTimeout(() => setOpen(false), 120);
        }}
        onKeyDown={event => {
          if (event.key === 'ArrowDown') {
            event.preventDefault();
            setOpen(true);
            move(1);
          } else if (event.key === 'ArrowUp') {
            event.preventDefault();
            setOpen(true);
            move(-1);
          } else if (event.key === 'Home') {
            event.preventDefault();
            setOpen(true);
            setActiveIndex(0);
          } else if (event.key === 'End') {
            event.preventDefault();
            setOpen(true);
            setActiveIndex(Math.max(filtered.length - 1, 0));
          } else if (event.key === 'Enter' && open && active) {
            event.preventDefault();
            choose(active);
          } else if (event.key === 'Escape') {
            event.preventDefault();
            setOpen(false);
            setQuery(selected?.display_name ?? '');
          }
        }}
      />
      {open && !disabled && (
        <ul id={listboxId} role="listbox" className="account-combobox__list">
          {filtered.length === 0 && <li className="account-combobox__empty">일치하는 계정과목이 없습니다.</li>}
          {filtered.map((entry, index) => (
            <li
              key={entry.account_id}
              id={`${listboxId}-${entry.account_id}`}
              role="option"
              aria-selected={entry.account_id === value}
              aria-disabled={!entry.assignable}
              className={[
                'account-combobox__option',
                index === activeIndex ? 'is-active' : '',
                !entry.assignable ? 'is-disabled' : '',
              ].filter(Boolean).join(' ')}
              onMouseDown={event => event.preventDefault()}
              onMouseMove={() => setActiveIndex(index)}
              onClick={() => choose(entry)}
            >
              <span>{entry.display_name}</span>
              <small>{entry.category_path.join(' / ')}{entry.account_code ? ` · ${entry.account_code}` : ''}</small>
              {!entry.assignable && <small>{entry.disabled_reason ?? '선택할 수 없는 계정입니다.'}</small>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
