import React from 'react';
import { BookOpen, Lock } from 'lucide-react';

export function ChapterSelector({ currentChapter, maxChapters = 8, onChapterChange }) {
  const chapters = Array.from({ length: maxChapters }, (_, i) => i + 1);

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '0.65rem 1.25rem',
      backgroundColor: 'var(--bg-tertiary)',
      borderBottom: '1px solid var(--border-subtle)',
      fontSize: '0.825rem',
      gap: '1rem',
      flexWrap: 'wrap',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        <BookOpen size={16} color="var(--accent-amber)" />
        <span style={{ fontWeight: 600, color: 'var(--text-ivory-primary)' }}>
          Reading Progress:
        </span>
        <span style={{
          backgroundColor: 'var(--accent-amber-bg)',
          color: 'var(--accent-amber-light)',
          padding: '0.15rem 0.5rem',
          borderRadius: 'var(--radius-sm)',
          fontFamily: 'var(--font-mono)',
          fontWeight: 600,
        }}>
          Chapter {currentChapter} of {maxChapters}
        </span>
        <span style={{ fontSize: '0.75rem', color: 'var(--text-ivory-muted)', marginLeft: '0.5rem' }}>
          (Revelations beyond Chapter {currentChapter} are locked)
        </span>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
        {chapters.map((chap) => {
          const isSelected = chap === currentChapter;
          const isUnlocked = chap <= currentChapter;

          return (
            <button
              key={chap}
              onClick={() => onChapterChange(chap)}
              className="btn"
              style={{
                minWidth: '2.4rem',
                padding: '0.35rem 0.6rem',
                fontSize: '0.775rem',
                fontFamily: 'var(--font-mono)',
                backgroundColor: isSelected
                  ? 'var(--accent-amber)'
                  : isUnlocked
                  ? 'var(--bg-surface)'
                  : 'var(--bg-secondary)',
                color: isSelected ? '#0f1114' : isUnlocked ? 'var(--text-ivory-primary)' : 'var(--text-ivory-muted)',
                borderColor: isSelected ? 'var(--accent-amber)' : 'var(--border-subtle)',
                fontWeight: isSelected ? 700 : 500,
                boxShadow: isSelected ? '0 0 10px var(--border-amber-glow)' : 'none',
              }}
              title={`Reveal narrative up to Chapter ${chap}`}
            >
              Ch. {chap}
            </button>
          );
        })}
      </div>
    </div>
  );
}
