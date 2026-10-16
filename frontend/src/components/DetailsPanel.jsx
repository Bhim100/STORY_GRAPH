import React from 'react';
import { X, FileText, ArrowRight, User, Calendar, MapPin, Users, HelpCircle } from 'lucide-react';

export function DetailsPanel({
  details,
  loading,
  onClose,
  onSelectEntityForQuestion,
}) {
  if (loading) {
    return (
      <div className="dossier-card" style={{ height: '100%', overflowY: 'auto' }}>
        <p style={{ color: 'var(--text-ivory-muted)', fontSize: '0.825rem' }}>
          Retrieving dossier files from FalkorDB...
        </p>
      </div>
    );
  }

  if (!details || !details.node) {
    return (
      <div className="dossier-card" style={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        textAlign: 'center',
        color: 'var(--text-ivory-muted)',
        padding: '2rem 1rem',
      }}>
        <HelpCircle size={32} color="var(--border-subtle)" style={{ marginBottom: '0.75rem' }} />
        <h3 style={{ fontSize: '0.9rem', color: 'var(--text-ivory-secondary)', marginBottom: '0.35rem' }}>
          Investigation Dossier
        </h3>
        <p style={{ fontSize: '0.775rem', lineHeight: 1.4 }}>
          Select any character, event, location, or faction on the canvas to inspect its case notes and verified evidence.
        </p>
      </div>
    );
  }

  const { node, connections = [], evidence = [] } = details;

  const getKindIcon = (kind) => {
    switch (kind) {
      case 'Character':
        return <User size={14} className="badge-character" />;
      case 'Event':
        return <Calendar size={14} className="badge-event" />;
      case 'Location':
        return <MapPin size={14} className="badge-location" />;
      case 'Faction':
        return <Users size={14} className="badge-faction" />;
      default:
        return null;
    }
  };

  return (
    <div className="dossier-card" style={{ height: '100%', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '0.75rem' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.25rem' }}>
            <span className={`badge badge-${node.kind?.toLowerCase()}`}>
              {getKindIcon(node.kind)}
              {node.kind}
            </span>
            <span className="badge" style={{ fontSize: '0.675rem' }}>
              Revealed: Ch. {node.reveal_chapter}
            </span>
          </div>
          <h2 style={{ fontSize: '1.15rem', fontFamily: 'var(--font-serif)', color: 'var(--text-ivory-primary)' }}>
            {node.name}
          </h2>
          {node.role && (
            <p style={{ fontSize: '0.8rem', color: 'var(--accent-amber-light)', fontWeight: 500, marginTop: '0.15rem' }}>
              {node.role}
            </p>
          )}
        </div>
        <button
          onClick={onClose}
          className="btn"
          style={{ padding: '0.3rem', border: 'none', background: 'transparent', color: 'var(--text-ivory-muted)' }}
          title="Close dossier"
        >
          <X size={16} />
        </button>
      </div>

      {/* Aliases / In-World Details */}
      {node.aliases && node.aliases.length > 0 && (
        <div style={{ fontSize: '0.775rem' }}>
          <span style={{ color: 'var(--text-ivory-muted)' }}>Known Aliases: </span>
          <span style={{ color: 'var(--text-ivory-secondary)', fontFamily: 'var(--font-mono)' }}>
            {node.aliases.join(', ')}
          </span>
        </div>
      )}

      {node.event_chapter != null && (
        <div style={{ fontSize: '0.775rem' }}>
          <span style={{ color: 'var(--text-ivory-muted)' }}>In-World Event Chapter: </span>
          <span style={{ color: 'var(--text-ivory-secondary)', fontFamily: 'var(--font-mono)' }}>
            Chapter {node.event_chapter}
          </span>
        </div>
      )}

      {/* Quick Action */}
      <button
        onClick={() => onSelectEntityForQuestion?.(node.name)}
        className="btn"
        style={{ width: '100%', fontSize: '0.775rem', justifyContent: 'center' }}
      >
        Ask about this entity in Question Panel
      </button>

      {/* Active Connections */}
      <div>
        <h3 style={{ fontSize: '0.8rem', letterSpacing: '0.05em', textTransform: 'uppercase', color: 'var(--text-ivory-muted)', marginBottom: '0.5rem' }}>
          Revealed Connections ({connections.length})
        </h3>
        {connections.length === 0 ? (
          <p style={{ fontSize: '0.775rem', color: 'var(--text-ivory-muted)', fontStyle: 'italic' }}>
            No verified connections discovered up to this chapter.
          </p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
            {connections.map((c, idx) => (
              <div
                key={idx}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '0.45rem 0.65rem',
                  backgroundColor: 'var(--bg-secondary)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '0.775rem',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  <ArrowRight size={12} color="var(--accent-amber)" />
                  <span style={{ color: 'var(--text-ivory-primary)', fontWeight: 500 }}>
                    {c.target_name}
                  </span>
                </div>
                <span className="badge badge-amber" style={{ fontSize: '0.675rem' }}>
                  {c.relationship}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Case Notes & Supporting Evidence */}
      <div>
        <h3 style={{ fontSize: '0.8rem', letterSpacing: '0.05em', textTransform: 'uppercase', color: 'var(--text-ivory-muted)', marginBottom: '0.5rem' }}>
          Supporting Evidence Case Notes ({evidence.length})
        </h3>
        {evidence.length === 0 ? (
          <p style={{ fontSize: '0.775rem', color: 'var(--text-ivory-muted)', fontStyle: 'italic' }}>
            No public evidence logged yet for these ties.
          </p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {evidence.map((ev, idx) => (
              <div
                key={idx}
                style={{
                  padding: '0.6rem 0.75rem',
                  backgroundColor: 'var(--bg-secondary)',
                  border: '1px solid var(--border-subtle)',
                  borderLeft: '3px solid var(--accent-amber)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '0.775rem',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
                  <span className="badge" style={{ fontSize: '0.65rem', textTransform: 'uppercase' }}>
                    <FileText size={10} />
                    {ev.kind}
                  </span>
                  <span className="evidence-tag" style={{ color: 'var(--accent-amber-light)' }}>
                    Discovered: Ch. {ev.reveal_chapter}
                  </span>
                </div>
                <p style={{ color: 'var(--text-ivory-secondary)', fontStyle: 'italic', lineHeight: 1.4 }}>
                  "{ev.excerpt}"
                </p>
                <p style={{ fontSize: '0.7rem', color: 'var(--text-ivory-muted)', marginTop: '0.35rem' }}>
                  Supports: <span style={{ color: 'var(--text-ivory-secondary)' }}>{ev.claim}</span>
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
