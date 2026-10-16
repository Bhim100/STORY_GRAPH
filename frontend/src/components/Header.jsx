import React from 'react';
import { Database, ShieldCheck, RefreshCw, Layers } from 'lucide-react';

export function Header({ story, chapter, dbStatus, onReset, onRefresh, loading }) {
  return (
    <header style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '0.75rem 1.25rem',
      backgroundColor: 'var(--bg-secondary)',
      borderBottom: '1px solid var(--border-subtle)',
      zIndex: 20,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <div style={{
            width: '28px',
            height: '28px',
            borderRadius: 'var(--radius-sm)',
            backgroundColor: 'var(--accent-amber-bg)',
            border: '1px solid var(--accent-amber)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--accent-amber)',
          }}>
            <Layers size={16} />
          </div>
          <div>
            <h1 style={{
              fontSize: '1.05rem',
              fontFamily: 'var(--font-serif)',
              letterSpacing: '0.04em',
              color: 'var(--text-ivory-primary)',
              lineHeight: 1.2,
            }}>
              StoryGraph
            </h1>
            <p style={{
              fontSize: '0.75rem',
              color: 'var(--text-ivory-muted)',
            }}>
              {story ? story.title : 'The Glass Orchard'} &bull; Investigation Map
            </p>
          </div>
        </div>

        <div style={{
          height: '24px',
          width: '1px',
          backgroundColor: 'var(--border-subtle)',
          margin: '0 0.5rem',
        }} />

        {/* Legend */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem', fontSize: '0.725rem' }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.3rem', color: 'var(--text-ivory-secondary)' }}>
            <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: 'var(--node-character)', display: 'inline-block' }} />
            Character
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.3rem', color: 'var(--text-ivory-secondary)' }}>
            <span style={{ width: '8px', height: '8px', transform: 'rotate(45deg)', backgroundColor: 'var(--node-event)', display: 'inline-block' }} />
            Event
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.3rem', color: 'var(--text-ivory-secondary)' }}>
            <span style={{ width: '8px', height: '8px', borderRadius: '2px', backgroundColor: 'var(--node-location)', display: 'inline-block' }} />
            Location
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.3rem', color: 'var(--text-ivory-secondary)' }}>
            <span style={{ width: '8px', height: '8px', borderRadius: '2px', backgroundColor: 'var(--node-faction)', display: 'inline-block' }} />
            Faction
          </span>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
        {/* Status Indicator */}
        <div className={`badge ${dbStatus === 'ok' ? 'badge-amber' : ''}`} style={{ fontSize: '0.7rem' }}>
          <Database size={12} />
          {dbStatus === 'ok' ? 'FalkorDB Connected' : 'Connecting to FalkorDB...'}
        </div>

        <div className="badge badge-amber" style={{ fontSize: '0.7rem' }}>
          <ShieldCheck size={12} />
          Spoiler Boundary: Ch. {chapter}
        </div>

        <button
          onClick={onRefresh}
          className="btn"
          disabled={loading}
          title="Refresh graph data"
          style={{ padding: '0.4rem 0.65rem' }}
        >
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>
    </header>
  );
}
