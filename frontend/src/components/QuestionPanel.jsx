import React, { useState, useEffect, useRef } from 'react';
import { Search, Sparkles, Loader2, CornerDownLeft } from 'lucide-react';
import { AnswerCard } from './AnswerCard';

export function QuestionPanel({
  currentChapter,
  onAskQuestion,
  loading,
  answerResult,
  onDismissAnswer,
  onSelectNode,
  initialQuestion = '',
}) {
  const [question, setQuestion] = useState(initialQuestion);
  const inputRef = useRef(null);

  useEffect(() => {
    if (initialQuestion) {
      setQuestion(initialQuestion);
      // Focus input without auto-submitting
      setTimeout(() => {
        if (inputRef.current) {
          inputRef.current.focus();
          const len = inputRef.current.value.length;
          inputRef.current.setSelectionRange(len, len);
        }
      }, 50);
    }
  }, [initialQuestion]);

  const handleSubmit = (e) => {
    e?.preventDefault();
    if (!question.trim() || loading) return;
    onAskQuestion(question.trim());
  };

  const sampleQuestions = [
    'How is Mara Voss connected to Elias Thorne?',
    'How are Mara Voss and Dr. Halden related?',
    'How is Jonas Reed connected to Elias?',
    'Is Tobias Quill connected to the household?',
  ];

  const handleSelectDisambiguation = (entityName) => {
    // Replace ambiguous mention with chosen name
    const updated = `How is ${entityName} connected to the story?`;
    setQuestion(updated);
    onAskQuestion(updated);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
      {/* Search Input Bar */}
      <form onSubmit={handleSubmit} className="dossier-card" style={{ padding: '0.75rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.65rem' }}>
          <Search size={16} color="var(--accent-amber)" />
          <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-ivory-primary)' }}>
            Narrative Question Engine
          </span>
          <span className="badge" style={{ fontSize: '0.65rem', marginLeft: 'auto' }}>
            Bound: Ch. {currentChapter}
          </span>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <input
            ref={inputRef}
            id="narrative-question-input"
            type="text"
            className="input-text"
            placeholder="e.g. How are Mara Voss and Dr. Halden connected?"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            disabled={loading}
            aria-label="Investigate narrative question"
          />
          <button
            type="submit"
            className="btn btn-primary"
            disabled={loading || !question.trim()}
            style={{ whiteSpace: 'nowrap' }}
          >
            {loading ? <Loader2 size={15} className="animate-spin" /> : <CornerDownLeft size={15} />}
            Investigate
          </button>
        </div>

        {/* Quick query chips */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginTop: '0.65rem', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '0.7rem', color: 'var(--text-ivory-muted)', display: 'flex', alignItems: 'center', gap: '0.2rem' }}>
            <Sparkles size={11} color="var(--accent-amber)" />
            Suggestions:
          </span>
          {sampleQuestions.map((q, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => {
                setQuestion(q);
                onAskQuestion(q);
              }}
              style={{
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-sm)',
                padding: '0.15rem 0.45rem',
                fontSize: '0.7rem',
                color: 'var(--text-ivory-secondary)',
                cursor: 'pointer',
                textAlign: 'left',
              }}
            >
              {q}
            </button>
          ))}
        </div>
      </form>

      {/* Disambiguation Choices (if clarification needed) */}
      {answerResult?.status === 'clarification_needed' && answerResult?.ambiguous_options && (
        <div className="dossier-card" style={{ padding: '0.75rem', borderColor: 'var(--accent-amber)' }}>
          <p style={{ fontSize: '0.775rem', color: 'var(--text-ivory-secondary)', marginBottom: '0.5rem' }}>
            Select an intended entity revealed up to Chapter {currentChapter}:
          </p>
          <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
            {answerResult.ambiguous_options.map((opt) => (
              <button
                key={opt.id}
                onClick={() => handleSelectDisambiguation(opt.name)}
                className="btn"
                style={{ fontSize: '0.75rem', padding: '0.25rem 0.5rem' }}
              >
                {opt.name} ({opt.labels?.[0]})
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Answer & Verified Path Result Card */}
      {answerResult && (
        <AnswerCard
          result={answerResult}
          onDismiss={onDismissAnswer}
          onSelectNode={onSelectNode}
        />
      )}
    </div>
  );
}
