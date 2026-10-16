import React from 'react';
import { CheckCircle2, AlertTriangle, HelpCircle, XCircle, FileText, ChevronRight, X } from 'lucide-react';

export function AnswerCard({ result, onDismiss, onSelectNode }) {
  if (!result) return null;

  const { status, answer, resolved_entities = [], nodes = [], relationships = [], evidence = [] } = result;

  const getStatusBadge = () => {
    switch (status) {
      case 'answered':
        return (
          <span className="badge badge-amber" style={{ fontSize: '0.75rem' }}>
            <CheckCircle2 size={13} />
            Verified Connection
          </span>
        );
      case 'no_path':
        return (
          <span className="badge" style={{ fontSize: '0.75rem', borderColor: '#64748b', color: '#94a3b8' }}>
            <HelpCircle size={13} />
            No Connection at Chapter
          </span>
        );
      case 'clarification_needed':
        return (
          <span className="badge badge-amber" style={{ fontSize: '0.75rem' }}>
            <AlertTriangle size={13} />
            Clarification Needed
          </span>
        );
      case 'unresolved_entity':
        return (
          <span className="badge" style={{ fontSize: '0.75rem', borderColor: '#ef4444', color: '#f87171' }}>
            <XCircle size={13} />
            Unresolved Entity
          </span>
        );
      default:
        return (
          <span className="badge" style={{ fontSize: '0.75rem' }}>
            {status}
          </span>
        );
    }
  };

  return (
    <div className="dossier-card" style={{
      borderLeft: status === 'answered' ? '4px solid var(--accent-amber)' : '4px solid var(--border-subtle)',
      display: 'flex',
      flexDirection: 'column',
      gap: '0.75rem',
      boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
    }}>
      {/* Card Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          {getStatusBadge()}
          {resolved_entities.length === 2 && (
            <span style={{ fontSize: '0.75rem', color: 'var(--text-ivory-muted)', fontFamily: 'var(--font-mono)' }}>
              {resolved_entities[0].name} &harr; {resolved_entities[1].name}
            </span>
          )}
        </div>
        <button
          onClick={onDismiss}
          className="btn"
          style={{ padding: '0.2rem', border: 'none', background: 'transparent', color: 'var(--text-ivory-muted)' }}
          title="Dismiss result"
        >
          <X size={15} />
        </button>
      </div>

      {/* Path Breadcrumbs (if connection exists) */}
      {nodes.length > 0 && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.4rem',
          flexWrap: 'wrap',
          padding: '0.5rem 0.75rem',
          backgroundColor: 'var(--bg-secondary)',
          borderRadius: 'var(--radius-sm)',
          border: '1px solid var(--border-subtle)',
          fontSize: '0.775rem',
        }}>
          {nodes.map((node, idx) => {
            const rel = relationships[idx];
            return (
              <React.Fragment key={node.id || idx}>
                <button
                  onClick={() => onSelectNode?.(node.id)}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: 'var(--text-ivory-primary)',
                    fontWeight: 600,
                    cursor: 'pointer',
                    textDecoration: 'underline',
                    textUnderlineOffset: '2px',
                    fontSize: '0.775rem',
                  }}
                  title="View entity dossier"
                >
                  {node.name}
                </button>
                {rel && (
                  <span style={{ display: 'flex', alignItems: 'center', gap: '0.2rem', color: 'var(--accent-amber-light)' }}>
                    <ChevronRight size={12} />
                    <span className="badge badge-amber" style={{ fontSize: '0.65rem' }}>
                      {rel.type}
                    </span>
                    <ChevronRight size={12} />
                  </span>
                )}
              </React.Fragment>
            );
          })}
        </div>
      )}

      {/* Answer Explanation */}
      <div style={{ fontSize: '0.85rem', color: 'var(--text-ivory-primary)', lineHeight: 1.5 }}>
        {answer}
      </div>

      {/* Supporting Evidence Records */}
      {evidence.length > 0 && (
        <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '0.75rem' }}>
          <h4 style={{ fontSize: '0.75rem', letterSpacing: '0.05em', textTransform: 'uppercase', color: 'var(--text-ivory-muted)', marginBottom: '0.5rem' }}>
            Verified Evidence Documents ({evidence.length})
          </h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.45rem' }}>
            {evidence.map((ev, i) => (
              <div
                key={i}
                style={{
                  padding: '0.5rem 0.65rem',
                  backgroundColor: 'var(--bg-secondary)',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--border-subtle)',
                  fontSize: '0.75rem',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.2rem' }}>
                  <span className="badge" style={{ fontSize: '0.625rem', textTransform: 'uppercase' }}>
                    <FileText size={10} />
                    {ev.kind}
                  </span>
                  <span className="evidence-tag" style={{ color: 'var(--accent-amber-light)' }}>
                    Ch. {ev.reveal_chapter}
                  </span>
                </div>
                <p style={{ color: 'var(--text-ivory-secondary)', fontStyle: 'italic', lineHeight: 1.35 }}>
                  "{ev.excerpt}"
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
