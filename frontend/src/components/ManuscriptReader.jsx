import React, { useState, useEffect } from 'react';
import { BookOpen, ChevronLeft, ChevronRight, Sparkles, Clock, Users, RefreshCw, AlertCircle } from 'lucide-react';
import { fetchChapterContent, extractStoryGraph } from '../services/api';

export function ManuscriptReader({
  bookId,
  currentChapter,
  maxChapters,
  bookStatus,
  onChapterChange,
  onGraphExtracted,
  onSelectEntity,
}) {
  const [chapterData, setChapterData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [extracting, setExtracting] = useState(false);
  const [extractMsg, setExtractMsg] = useState('');

  useEffect(() => {
    if (!bookId) return;
    let isCancelled = false;

    async function loadChapter() {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchChapterContent(bookId, currentChapter);
        if (!isCancelled) {
          setChapterData(data);
        }
      } catch (err) {
        if (!isCancelled) {
          setError(err.message || 'Failed to load chapter text.');
        }
      } finally {
        if (!isCancelled) {
          setLoading(false);
        }
      }
    }

    loadChapter();
    return () => {
      isCancelled = true;
    };
  }, [bookId, currentChapter]);

  const handleExtractGraph = async () => {
    setExtracting(true);
    setExtractMsg('Extracting candidate characters and building story graph...');
    try {
      const updated = await extractStoryGraph(bookId);
      setExtractMsg('Graph extracted successfully!');
      setTimeout(() => {
        setExtracting(false);
        setExtractMsg('');
        if (onGraphExtracted) onGraphExtracted(updated);
      }, 700);
    } catch (err) {
      setExtractMsg(`Extraction failed: ${err.message}`);
      setExtracting(false);
    }
  };

  const readingTimeMinutes = Math.max(1, Math.round((chapterData?.word_count || 150) / 200));

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      backgroundColor: 'var(--bg-secondary)',
      color: 'var(--text-ivory-primary)',
      overflow: 'hidden',
    }}>
      {/* Chapter Reader Header Bar */}
      <div style={{
        padding: '0.875rem 1rem',
        borderBottom: '1px solid var(--border-subtle)',
        backgroundColor: 'var(--bg-tertiary)',
        display: 'flex',
        flexDirection: 'column',
        gap: '0.5rem',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <BookOpen size={16} style={{ color: 'var(--accent-amber)' }} />
            <h3 style={{
              fontSize: '0.95rem',
              fontWeight: 600,
              fontFamily: 'var(--font-serif)',
              color: 'var(--text-ivory-primary)',
              margin: 0,
            }}>
              {chapterData?.title || `Chapter ${currentChapter}`}
            </h3>
          </div>

          {/* Chapter navigation arrows */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
            <button
              onClick={() => onChapterChange(Math.max(1, currentChapter - 1))}
              disabled={currentChapter <= 1}
              className="btn btn-secondary"
              style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem', opacity: currentChapter <= 1 ? 0.4 : 1 }}
              title="Previous Chapter"
            >
              <ChevronLeft size={14} /> Prev
            </button>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-ivory-muted)', minWidth: '45px', textAlign: 'center' }}>
              {currentChapter} / {maxChapters}
            </span>
            <button
              onClick={() => onChapterChange(Math.min(maxChapters, currentChapter + 1))}
              disabled={currentChapter >= maxChapters}
              className="btn btn-secondary"
              style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem', opacity: currentChapter >= maxChapters ? 0.4 : 1 }}
              title="Next Chapter"
            >
              Next <ChevronRight size={14} />
            </button>
          </div>
        </div>

        {/* Reading stats & spoiler tag */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap', fontSize: '0.72rem', color: 'var(--text-ivory-muted)' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
            <Clock size={12} /> {readingTimeMinutes} min read ({chapterData?.word_count || 0} words)
          </span>
          <span>•</span>
          <span style={{ color: 'var(--accent-amber-light)' }}>
            Spoiler boundary enforced: Chapter {currentChapter}
          </span>
        </div>

        {/* Graph Extraction Banner if pending */}
        {bookStatus === 'import_pending' && (
          <div style={{
            marginTop: '0.25rem',
            padding: '0.5rem 0.75rem',
            backgroundColor: 'rgba(217, 119, 6, 0.1)',
            border: '1px solid rgba(217, 119, 6, 0.3)',
            borderRadius: 'var(--radius-sm)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '0.5rem',
          }}>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-ivory-secondary)' }}>
              Graph extraction is pending for this text.
            </span>
            <button
              onClick={handleExtractGraph}
              disabled={extracting}
              className="btn btn-primary"
              style={{
                padding: '0.25rem 0.6rem',
                fontSize: '0.72rem',
                backgroundColor: 'var(--accent-amber)',
                color: '#0f1114',
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                gap: '0.3rem',
              }}
            >
              <Sparkles size={12} />
              {extracting ? 'Extracting...' : 'Extract Graph'}
            </button>
          </div>
        )}

        {extractMsg && (
          <p style={{ fontSize: '0.72rem', color: 'var(--accent-amber)', margin: '0.2rem 0 0 0' }}>
            {extractMsg}
          </p>
        )}
      </div>

      {/* Candidate Entities in this Chapter */}
      {chapterData?.candidate_entities && chapterData.candidate_entities.length > 0 && (
        <div style={{
          padding: '0.6rem 1rem',
          borderBottom: '1px solid var(--border-subtle)',
          backgroundColor: 'rgba(0, 0, 0, 0.15)',
          display: 'flex',
          flexDirection: 'column',
          gap: '0.35rem',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.7rem', color: 'var(--text-ivory-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            <Users size={12} />
            <span>Entities noted in this chapter:</span>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem' }}>
            {chapterData.candidate_entities.map((entity, idx) => (
              <button
                key={idx}
                onClick={() => onSelectEntity?.(entity)}
                className="badge"
                style={{
                  fontSize: '0.72rem',
                  padding: '0.15rem 0.5rem',
                  backgroundColor: 'var(--bg-tertiary)',
                  color: 'var(--accent-amber-light)',
                  border: '1px solid rgba(217, 119, 6, 0.3)',
                  cursor: 'pointer',
                  borderRadius: '12px',
                  transition: 'all 0.15s ease',
                }}
                title={`Ask about or inspect ${entity}`}
              >
                {entity}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Main Manuscript Text Content */}
      <div style={{
        flex: 1,
        overflowY: 'auto',
        padding: '1.25rem 1.5rem',
        lineHeight: 1.8,
        fontSize: '0.9rem',
        color: 'var(--text-ivory-primary)',
        fontFamily: 'Georgia, Cambria, "Times New Roman", serif',
      }}>
        {loading ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', padding: '1rem 0' }}>
            <div style={{ height: '14px', width: '85%', backgroundColor: 'var(--bg-tertiary)', borderRadius: '4px', animation: 'pulse 1.5s infinite' }} />
            <div style={{ height: '14px', width: '95%', backgroundColor: 'var(--bg-tertiary)', borderRadius: '4px', animation: 'pulse 1.5s infinite' }} />
            <div style={{ height: '14px', width: '70%', backgroundColor: 'var(--bg-tertiary)', borderRadius: '4px', animation: 'pulse 1.5s infinite' }} />
            <div style={{ height: '14px', width: '90%', backgroundColor: 'var(--bg-tertiary)', borderRadius: '4px', animation: 'pulse 1.5s infinite' }} />
          </div>
        ) : error ? (
          <div style={{
            padding: '1rem',
            backgroundColor: 'rgba(239, 68, 68, 0.1)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            borderRadius: 'var(--radius-sm)',
            display: 'flex',
            alignItems: 'flex-start',
            gap: '0.5rem',
            color: '#f87171',
            fontSize: '0.825rem',
          }}>
            <AlertCircle size={16} style={{ flexShrink: 0, marginTop: '2px' }} />
            <div>
              <strong>Error Loading Manuscript:</strong>
              <p style={{ margin: '0.25rem 0 0 0' }}>{error}</p>
            </div>
          </div>
        ) : chapterData?.content ? (
          <div>
            {chapterData.content.split(/\n\s*\n/).map((para, pIdx) => {
              const cleanPara = para.trim();
              if (!cleanPara) return null;
              // Check if heading
              if (cleanPara.startsWith('#') || cleanPara.toLowerCase().startsWith('chapter')) {
                return (
                  <h4 key={pIdx} style={{
                    fontSize: '1.1rem',
                    color: 'var(--accent-amber-light)',
                    marginTop: pIdx > 0 ? '1.5rem' : '0.5rem',
                    marginBottom: '0.75rem',
                    fontFamily: 'var(--font-serif)',
                    letterSpacing: '0.02em',
                  }}>
                    {cleanPara.replace(/^#+\s*/, '')}
                  </h4>
                );
              }
              return (
                <p key={pIdx} style={{
                  marginBottom: '1.15rem',
                  textIndent: '1.25rem',
                  letterSpacing: '0.01em',
                  color: 'var(--text-ivory-primary)',
                }}>
                  {cleanPara}
                </p>
              );
            })}
          </div>
        ) : (
          <p style={{ color: 'var(--text-ivory-muted)', fontStyle: 'italic' }}>
            No text content recorded for this chapter.
          </p>
        )}
      </div>
    </div>
  );
}
