import React, { useState, useEffect, useRef } from 'react';
import {
  X,
  FileText,
  ArrowRight,
  ArrowLeft,
  User,
  Calendar,
  MapPin,
  Users,
  HelpCircle,
  MessageSquare,
  Package,
  Copy,
  Check,
  Sparkles,
  Clock,
} from 'lucide-react';

function getEntityAssetUrl(node) {
  if (!node || !node.id) return null;
  if (node.kind === 'Character') return `/assets/avatars/${node.id}.jpg`;
  if (node.kind === 'Event') return `/assets/events/${node.id}.jpg`;
  if (node.kind === 'Faction') return `/assets/factions/${node.id}.jpg`;
  if (node.kind === 'Location') return `/assets/locations/${node.id}.jpg`;
  return null;
}

export function DetailsPanel({
  details,
  loading,
  onClose,
  onSelectEntityForQuestion,
}) {
  const [copied, setCopied] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const cardRef = useRef(null);

  // Close actions menu on Escape or outside click
  useEffect(() => {
    function handleKeyDown(e) {
      if (e.key === 'Escape') {
        setMenuOpen(false);
      }
    }
    function handleClickOutside(e) {
      if (cardRef.current && !cardRef.current.contains(e.target)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener('keydown', handleKeyDown);
    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

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
      <div
        className="dossier-card"
        style={{
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          textAlign: 'center',
          color: 'var(--text-ivory-muted)',
          padding: '2rem 1rem',
        }}
      >
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
        return <User size={14} className="badge-character" aria-hidden="true" />;
      case 'Event':
        return <Calendar size={14} className="badge-event" aria-hidden="true" />;
      case 'Location':
        return <MapPin size={14} className="badge-location" aria-hidden="true" />;
      case 'Faction':
        return <Users size={14} className="badge-faction" aria-hidden="true" />;
      default:
        return <HelpCircle size={14} aria-hidden="true" />;
    }
  };

  const getEvidenceIcon = (kind) => {
    switch (kind) {
      case 'document':
        return <FileText size={12} color="var(--accent-amber)" aria-hidden="true" />;
      case 'testimony':
        return <MessageSquare size={12} color="var(--accent-amber-light)" aria-hidden="true" />;
      case 'object':
        return <Package size={12} color="var(--node-location)" aria-hidden="true" />;
      default:
        return <FileText size={12} aria-hidden="true" />;
    }
  };

  const handleAsk = () => {
    onSelectEntityForQuestion?.(node.name);
    setMenuOpen(false);
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(node.name);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback if clipboard API is restricted
    }
  };

  return (
    <div
      ref={cardRef}
      className="dossier-card dossier-interactive-card"
      tabIndex={0}
      aria-label={`Dossier for ${node.name}`}
      style={{
        height: '100%',
        overflowY: 'auto',
        display: 'flex',
        flexDirection: 'column',
        gap: '1rem',
        outline: 'none',
      }}
    >
      {/* Floating / Docked Hover Actions Bar */}
      <div
        className={`dossier-actions-container ${menuOpen ? 'is-open' : ''}`}
        style={{
          position: 'sticky',
          top: 0,
          zIndex: 20,
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '-0.5rem',
        }}
      >
        <div className="dossier-actions-bar" role="toolbar" aria-label="Entity Actions">
          <button
            type="button"
            className="action-chip-btn"
            onClick={handleAsk}
            title={`Focus narrative question engine for ${node.name}`}
            aria-label={`Ask about ${node.name}`}
          >
            <Sparkles size={12} color="var(--accent-amber)" />
            <span>Ask about this entity</span>
          </button>

          <button
            type="button"
            className="action-chip-btn"
            onClick={handleCopy}
            title="Copy entity name to clipboard"
            aria-label={`Copy name ${node.name}`}
          >
            {copied ? <Check size={12} color="#10b981" /> : <Copy size={12} />}
            <span>{copied ? 'Copied' : 'Copy'}</span>
          </button>
        </div>

        {menuOpen && (
          <button
            type="button"
            className="btn"
            onClick={() => setMenuOpen(false)}
            style={{
              padding: '0.25rem 0.4rem',
              border: 'none',
              background: 'var(--bg-surface)',
              color: 'var(--text-ivory-muted)',
              borderRadius: 'var(--radius-sm)',
            }}
            title="Dismiss actions"
            aria-label="Dismiss actions menu"
          >
            <X size={13} />
          </button>
        )}
      </div>

      {/* Header & Classification */}
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          borderBottom: '1px solid var(--border-subtle)',
          paddingBottom: '0.75rem',
          position: 'relative',
        }}
      >
        <div style={{ flex: 1, paddingRight: '0.5rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap', marginBottom: '0.35rem' }}>
            <span className={`badge badge-${node.kind?.toLowerCase()}`}>
              {getKindIcon(node.kind)}
              <span>{node.kind}</span>
            </span>

            <span className="badge" title="Narrative reveal boundary">
              <Clock size={10} style={{ marginRight: '0.2rem' }} />
              Revealed: Ch. {node.reveal_chapter}
            </span>

            {node.event_chapter != null && (
              <span className="badge" title="In-world timeline chapter">
                In-World: Ch. {node.event_chapter}
              </span>
            )}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginTop: '0.25rem' }}>
            {getEntityAssetUrl(node) && (
              <img
                src={getEntityAssetUrl(node)}
                alt={node.name}
                style={{
                  width: '54px',
                  height: '54px',
                  borderRadius: node.kind === 'Faction' || node.kind === 'Location' ? '10px' : '50%',
                  objectFit: 'cover',
                  border: `2px solid ${
                    node.kind === 'Faction'
                      ? 'var(--node-faction)'
                      : node.kind === 'Location'
                      ? 'var(--node-location)'
                      : node.kind === 'Event'
                      ? 'var(--node-event)'
                      : 'var(--accent-amber)'
                  }`,
                  boxShadow: '0 2px 8px rgba(0, 0, 0, 0.5)',
                  flexShrink: 0,
                }}
                onError={(e) => {
                  e.currentTarget.style.display = 'none';
                }}
              />
            )}
            <div>
              <h2
                style={{
                  fontSize: '1.2rem',
                  fontFamily: 'var(--font-serif)',
                  color: 'var(--text-ivory-primary)',
                  lineHeight: 1.25,
                  wordBreak: 'break-word',
                }}
              >
                {node.name}
              </h2>

              {node.role && node.role.trim() !== '' && (
                <p
                  style={{
                    fontSize: '0.8rem',
                    color: 'var(--accent-amber-light)',
                    fontWeight: 500,
                    marginTop: '0.2rem',
                    wordBreak: 'break-word',
                  }}
                >
                  {node.role}
                </p>
              )}
            </div>
          </div>

          {node.description && node.description.trim() !== '' && (
            <p
              style={{
                fontSize: '0.775rem',
                color: 'var(--text-ivory-secondary)',
                lineHeight: 1.45,
                marginTop: '0.4rem',
                wordBreak: 'break-word',
              }}
            >
              {node.description}
            </p>
          )}
        </div>

        {/* Right Header Buttons: Touch Menu Toggle & Close Dossier */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
          <button
            type="button"
            onClick={() => setMenuOpen(!menuOpen)}
            className="btn"
            style={{
              padding: '0.35rem',
              border: 'none',
              background: menuOpen ? 'var(--bg-surface)' : 'transparent',
              color: menuOpen ? 'var(--accent-amber-light)' : 'var(--text-ivory-muted)',
            }}
            title="Toggle action options"
            aria-label="Toggle action options"
            aria-expanded={menuOpen}
          >
            <MoreHorizontal size={16} />
          </button>

          <button
            type="button"
            onClick={onClose}
            className="btn"
            style={{ padding: '0.35rem', border: 'none', background: 'transparent', color: 'var(--text-ivory-muted)' }}
            title="Close dossier"
            aria-label="Close dossier"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      {/* Aliases / In-World Details */}
      {node.aliases && Array.isArray(node.aliases) && node.aliases.length > 0 && (
        <div style={{ fontSize: '0.775rem', display: 'flex', alignItems: 'baseline', gap: '0.35rem', flexWrap: 'wrap' }}>
          <span style={{ color: 'var(--text-ivory-muted)' }}>Known Aliases:</span>
          <div style={{ display: 'inline-flex', gap: '0.25rem', flexWrap: 'wrap' }}>
            {node.aliases.map((alias, idx) => (
              <span
                key={idx}
                style={{
                  color: 'var(--text-ivory-secondary)',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.725rem',
                  backgroundColor: 'var(--bg-surface)',
                  padding: '0.1rem 0.35rem',
                  borderRadius: 'var(--radius-sm)',
                  border: '1px solid var(--border-subtle)',
                }}
              >
                {alias}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Primary Action Button (Keyboard & Screen Reader Accessible) */}
      <button
        type="button"
        onClick={handleAsk}
        className="btn"
        style={{
          width: '100%',
          fontSize: '0.775rem',
          justifyContent: 'center',
          borderColor: 'var(--border-subtle)',
          backgroundColor: 'var(--bg-tertiary)',
        }}
        aria-label={`Ask question about ${node.name}`}
      >
        <Sparkles size={13} color="var(--accent-amber)" />
        <span>Ask about this entity in Question Panel</span>
      </button>

      {/* Revealed Connections */}
      <div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
          <h3
            style={{
              fontSize: '0.775rem',
              letterSpacing: '0.05em',
              textTransform: 'uppercase',
              color: 'var(--text-ivory-muted)',
              fontFamily: 'var(--font-mono)',
            }}
          >
            Revealed Connections ({connections.length})
          </h3>
        </div>

        {connections.length === 0 ? (
          <p style={{ fontSize: '0.775rem', color: 'var(--text-ivory-muted)', fontStyle: 'italic' }}>
            No verified connections discovered up to this chapter.
          </p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
            {connections.map((c, idx) => {
              const isOutgoing = c.direction === 'outgoing';
              return (
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
                    gap: '0.5rem',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', minWidth: 0, flex: 1 }}>
                    {isOutgoing ? (
                      <ArrowRight size={13} color="var(--accent-amber)" style={{ flexShrink: 0 }} aria-label="Outgoing connection" />
                    ) : (
                      <ArrowLeft size={13} color="var(--accent-amber-light)" style={{ flexShrink: 0 }} aria-label="Incoming connection" />
                    )}
                    <span
                      style={{
                        color: 'var(--text-ivory-primary)',
                        fontWeight: 500,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                      title={c.target_name}
                    >
                      {c.target_name}
                    </span>
                    {c.target_kind && (
                      <span
                        className="badge"
                        style={{
                          fontSize: '0.625rem',
                          padding: '0.05rem 0.3rem',
                          flexShrink: 0,
                          backgroundColor: 'var(--bg-surface)',
                        }}
                      >
                        {c.target_kind}
                      </span>
                    )}
                  </div>
                  <span
                    className="badge badge-amber"
                    style={{ fontSize: '0.675rem', flexShrink: 0 }}
                    title={`Revealed in Chapter ${c.reveal_chapter}`}
                  >
                    {c.relationship}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Case Notes & Supporting Evidence */}
      <div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
          <h3
            style={{
              fontSize: '0.775rem',
              letterSpacing: '0.05em',
              textTransform: 'uppercase',
              color: 'var(--text-ivory-muted)',
              fontFamily: 'var(--font-mono)',
            }}
          >
            Supporting Evidence Case Notes ({evidence.length})
          </h3>
        </div>

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
                  padding: '0.65rem 0.75rem',
                  backgroundColor: 'var(--bg-secondary)',
                  border: '1px solid var(--border-subtle)',
                  borderLeft: '3px solid var(--accent-amber)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '0.775rem',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '0.35rem',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.5rem', flexWrap: 'wrap' }}>
                  <span
                    className="badge"
                    style={{
                      fontSize: '0.65rem',
                      textTransform: 'uppercase',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '0.3rem',
                    }}
                  >
                    {getEvidenceIcon(ev.kind)}
                    <span>{ev.kind}</span>
                  </span>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                    {ev.source_chapter != null && (
                      <span className="evidence-tag" style={{ color: 'var(--text-ivory-muted)', fontSize: '0.65rem' }}>
                        Source: Ch. {ev.source_chapter}
                      </span>
                    )}
                    <span className="evidence-tag" style={{ color: 'var(--accent-amber-light)' }}>
                      Discovered: Ch. {ev.reveal_chapter}
                    </span>
                  </div>
                </div>

                {ev.excerpt && (
                  <p
                    style={{
                      color: 'var(--text-ivory-secondary)',
                      fontStyle: 'italic',
                      lineHeight: 1.45,
                      wordBreak: 'break-word',
                      overflowWrap: 'anywhere',
                    }}
                  >
                    "{ev.excerpt}"
                  </p>
                )}

                {ev.claim && (
                  <p style={{ fontSize: '0.7rem', color: 'var(--text-ivory-muted)', wordBreak: 'break-word' }}>
                    Supports: <span style={{ color: 'var(--text-ivory-secondary)', fontWeight: 500 }}>{ev.claim}</span>
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
