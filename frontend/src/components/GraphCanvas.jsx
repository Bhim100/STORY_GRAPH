import React, { useState, useEffect, useRef } from 'react';
import cytoscape from 'cytoscape';
import {
  ZoomIn,
  ZoomOut,
  Maximize2,
  User,
  Calendar,
  MapPin,
  Users,
  HelpCircle,
  ArrowRight,
  Sparkles,
  FileText,
  X,
} from 'lucide-react';

export function GraphCanvas({
  elements,
  selectedNodeId,
  highlightedPath,
  onSelectNode,
  onSelectEntityForQuestion,
  loading,
}) {
  const containerRef = useRef(null);
  const cyRef = useRef(null);
  const [hoverCard, setHoverCard] = useState(null);
  const hideTimerRef = useRef(null);

  const getKindIcon = (kind) => {
    switch (kind) {
      case 'Character':
        return <User size={13} className="badge-character" aria-hidden="true" />;
      case 'Event':
        return <Calendar size={13} className="badge-event" aria-hidden="true" />;
      case 'Location':
        return <MapPin size={13} className="badge-location" aria-hidden="true" />;
      case 'Faction':
        return <Users size={13} className="badge-faction" aria-hidden="true" />;
      default:
        return <HelpCircle size={13} aria-hidden="true" />;
    }
  };

  useEffect(() => {
    if (!containerRef.current) return;

    const cy = cytoscape({
      container: containerRef.current,
      style: [
        // Default Node Style
        {
          selector: 'node',
          style: {
            label: 'data(label)',
            'font-family': 'Inter, sans-serif',
            'font-size': '11px',
            'font-weight': 600,
            'text-valign': 'bottom',
            'text-margin-y': 6,
            color: '#f5f2eb',
            'text-background-color': '#0f1114',
            'text-background-opacity': 0.85,
            'text-background-padding': '3px',
            'text-background-shape': 'roundrectangle',
            width: 38,
            height: 38,
            'border-width': 2,
            'border-color': '#475569',
            'background-color': '#1e293b',
            'transition-property': 'background-color, border-color, border-width, opacity, width, height',
            'transition-duration': '0.2s',
          },
        },
        // Character Nodes
        {
          selector: 'node[kind = "Character"]',
          style: {
            shape: 'ellipse',
            'background-color': '#27272a',
            'border-color': '#e4e4e7',
            'border-width': 2,
          },
        },
        // Event Nodes
        {
          selector: 'node[kind = "Event"]',
          style: {
            shape: 'diamond',
            width: 42,
            height: 42,
            'background-color': '#451a03',
            'border-color': '#f59e0b',
            'border-width': 2,
          },
        },
        // Location Nodes
        {
          selector: 'node[kind = "Location"]',
          style: {
            shape: 'round-hexagon',
            'background-color': '#082f49',
            'border-color': '#38bdf8',
            'border-width': 2,
          },
        },
        // Faction Nodes
        {
          selector: 'node[kind = "Faction"]',
          style: {
            shape: 'round-rectangle',
            'background-color': '#3b0764',
            'border-color': '#c084fc',
            'border-width': 2,
          },
        },
        // Default Edge Style
        {
          selector: 'edge',
          style: {
            width: 1.5,
            'line-color': '#475569',
            'target-arrow-color': '#64748b',
            'target-arrow-shape': 'triangle',
            'curve-style': 'bezier',
            label: 'data(label)',
            'font-family': 'JetBrains Mono, monospace',
            'font-size': '8.5px',
            color: '#cbd5e1',
            'text-background-color': '#0f1114',
            'text-background-opacity': 0.85,
            'text-background-padding': '2px',
            'text-background-shape': 'roundrectangle',
            'text-rotation': 'autorotate',
            'arrow-scale': 0.8,
            'transition-property': 'line-color, width, opacity',
            'transition-duration': '0.2s',
          },
        },
        // Selected Node
        {
          selector: 'node:selected',
          style: {
            'border-color': '#f59e0b',
            'border-width': 4,
            'shadow-blur': 12,
            'shadow-color': '#f59e0b',
            'shadow-opacity': 0.6,
          },
        },
        // Highlighted Path Nodes
        {
          selector: 'node.path-highlight',
          style: {
            'border-color': '#f59e0b',
            'border-width': 4,
            width: 46,
            height: 46,
            'shadow-blur': 14,
            'shadow-color': '#f59e0b',
            'shadow-opacity': 0.75,
            opacity: 1,
            'z-index': 99,
          },
        },
        // Highlighted Path Edges
        {
          selector: 'edge.path-highlight',
          style: {
            'line-color': '#f59e0b',
            'target-arrow-color': '#f59e0b',
            width: 3.5,
            opacity: 1,
            'z-index': 98,
            color: '#f59e0b',
            'font-weight': 'bold',
          },
        },
        // Dimmed Elements (when path is active)
        {
          selector: '.path-dimmed',
          style: {
            opacity: 0.22,
          },
        },
      ],
      elements: [],
      layout: {
        name: 'cose',
        animate: false,
        randomize: false,
        componentSpacing: 100,
        nodeOverlap: 20,
        nodeRepulsion: () => 400000,
      },
      minZoom: 0.3,
      maxZoom: 3.0,
      wheelSensitivity: 0.25,
    });

    // Node Hover Interaction: Shows On-Grid Card
    cy.on('mouseover', 'node', (evt) => {
      if (hideTimerRef.current) {
        clearTimeout(hideTimerRef.current);
        hideTimerRef.current = null;
      }

      const node = evt.target;
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const pos = node.renderedPosition();
      const data = node.data();

      // Gather connected relationships on the visible grid
      const connectedEdges = node.connectedEdges();
      const connections = connectedEdges.map((e) => {
        const isSource = e.source().id() === node.id();
        const otherNode = isSource ? e.target() : e.source();
        return {
          relationship: e.data('label'),
          targetName: otherNode.data('label') || otherNode.id(),
          targetKind: otherNode.data('kind'),
          direction: isSource ? 'outgoing' : 'incoming',
        };
      });

      const cardWidth = 280;
      const cardHeight = 195;
      let x = pos.x + 20;
      let y = pos.y - 25;

      // Ensure card remains completely within grid canvas bounds
      if (x + cardWidth > rect.width - 15) {
        x = pos.x - cardWidth - 20;
      }
      if (x < 15) x = 15;
      if (y + cardHeight > rect.height - 15) {
        y = rect.height - cardHeight - 15;
      }
      if (y < 15) y = 15;

      setHoverCard({
        id: node.id(),
        name: data.label,
        kind: data.kind,
        role: data.role,
        reveal_chapter: data.reveal_chapter,
        aliases: data.aliases || [],
        connectionsCount: connectedEdges.length,
        connections: connections.slice(0, 3),
        x,
        y,
      });
    });

    cy.on('mouseout', 'node', () => {
      hideTimerRef.current = setTimeout(() => {
        setHoverCard(null);
      }, 220);
    });

    cy.on('pan zoom', () => {
      setHoverCard(null);
    });

    cy.on('tap', 'node', (evt) => {
      const node = evt.target;
      onSelectNode?.(node.id());
      setHoverCard(null);
    });

    cy.on('tap', (evt) => {
      if (evt.target === cy) {
        onSelectNode?.(null);
        setHoverCard(null);
      }
    });

    cyRef.current = cy;

    return () => {
      if (hideTimerRef.current) {
        clearTimeout(hideTimerRef.current);
      }
      cy.destroy();
    };
  }, [onSelectNode]);

  // Update elements and apply layout
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;

    cy.batch(() => {
      cy.elements().remove();
      if (elements && (elements.nodes?.length > 0 || elements.edges?.length > 0)) {
        cy.add(elements.nodes || []);
        cy.add(elements.edges || []);
      }
    });

    if (cy.nodes().length > 0) {
      cy.layout({
        name: 'cose',
        animate: true,
        animationDuration: 400,
        nodeDimensionsIncludeLabels: true,
        fit: true,
        padding: 50,
      }).run();
    }
  }, [elements]);

  // Handle Selection & Path Highlighting
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;

    cy.batch(() => {
      cy.elements().removeClass('path-highlight path-dimmed');

      // If there is an active path to highlight
      if (highlightedPath && (highlightedPath.nodes?.length > 0 || highlightedPath.edges?.length > 0)) {
        const pathNodeIds = new Set(highlightedPath.nodes.map((n) => n.id));
        const pathClaimIds = new Set(
          (highlightedPath.relationships || highlightedPath.edges || []).map((r) => r.claim_id)
        );

        // Dim everything first
        cy.elements().addClass('path-dimmed');

        // Highlight path nodes
        cy.nodes().forEach((n) => {
          if (pathNodeIds.has(n.id())) {
            n.removeClass('path-dimmed').addClass('path-highlight');
          }
        });

        // Highlight path edges
        cy.edges().forEach((e) => {
          const claimId = e.data('claim_id');
          if (claimId && pathClaimIds.has(claimId)) {
            e.removeClass('path-dimmed').addClass('path-highlight');
          }
        });
      } else if (selectedNodeId) {
        // Just highlight selected node
        const node = cy.getElementById(selectedNodeId);
        if (node.length > 0) {
          node.select();
        }
      }
    });
  }, [selectedNodeId, highlightedPath]);

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', overflow: 'hidden' }}>
      <div
        ref={containerRef}
        style={{
          width: '100%',
          height: '100%',
          backgroundColor: 'var(--bg-primary)',
          backgroundImage:
            'radial-gradient(var(--border-subtle) 0.8px, transparent 0.8px), radial-gradient(var(--border-subtle) 0.8px, var(--bg-primary) 0.8px)',
          backgroundSize: '32px 32px',
          backgroundPosition: '0 0, 16px 16px',
        }}
      />

      {/* On-Grid Floating Hover Card */}
      {hoverCard && (
        <div
          className="grid-hover-card"
          style={{
            left: `${hoverCard.x}px`,
            top: `${hoverCard.y}px`,
          }}
          onMouseEnter={() => {
            if (hideTimerRef.current) {
              clearTimeout(hideTimerRef.current);
              hideTimerRef.current = null;
            }
          }}
          onMouseLeave={() => {
            setHoverCard(null);
          }}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Card Header: Kind, Reveal Chapter, Close */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              borderBottom: '1px solid var(--border-subtle)',
              paddingBottom: '0.4rem',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
              <span className={`badge badge-${hoverCard.kind?.toLowerCase()}`} style={{ fontSize: '0.65rem' }}>
                {getKindIcon(hoverCard.kind)}
                <span>{hoverCard.kind}</span>
              </span>
              <span className="badge" style={{ fontSize: '0.65rem' }}>
                Revealed: Ch. {hoverCard.reveal_chapter}
              </span>
            </div>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setHoverCard(null);
              }}
              style={{
                background: 'transparent',
                border: 'none',
                color: 'var(--text-ivory-muted)',
                cursor: 'pointer',
                padding: '0.1rem',
              }}
              title="Close card"
              aria-label="Close hover card"
            >
              <X size={13} />
            </button>
          </div>

          {/* Entity Name & Role */}
          <div>
            <h4
              style={{
                fontSize: '0.975rem',
                fontFamily: 'var(--font-serif)',
                color: 'var(--text-ivory-primary)',
                lineHeight: 1.25,
                wordBreak: 'break-word',
              }}
            >
              {hoverCard.name}
            </h4>
            {hoverCard.role && hoverCard.role.trim() !== '' && (
              <p
                style={{
                  fontSize: '0.75rem',
                  color: 'var(--accent-amber-light)',
                  fontWeight: 500,
                  marginTop: '0.15rem',
                  wordBreak: 'break-word',
                }}
              >
                {hoverCard.role}
              </p>
            )}
          </div>

          {/* Known Aliases */}
          {hoverCard.aliases && hoverCard.aliases.length > 0 && (
            <div style={{ fontSize: '0.7rem', color: 'var(--text-ivory-muted)' }}>
              Aliases:{' '}
              <span style={{ color: 'var(--text-ivory-secondary)', fontFamily: 'var(--font-mono)' }}>
                {hoverCard.aliases.join(', ')}
              </span>
            </div>
          )}

          {/* Visible Connections Summary */}
          <div
            style={{
              fontSize: '0.7rem',
              color: 'var(--text-ivory-muted)',
              borderTop: '1px solid var(--border-subtle)',
              paddingTop: '0.35rem',
            }}
          >
            <span style={{ fontWeight: 600, color: 'var(--text-ivory-secondary)' }}>
              {hoverCard.connectionsCount} active connection{hoverCard.connectionsCount === 1 ? '' : 's'} on grid:
            </span>
            {hoverCard.connections.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.2rem', marginTop: '0.25rem' }}>
                {hoverCard.connections.map((c, idx) => (
                  <div
                    key={idx}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.3rem',
                      fontSize: '0.675rem',
                    }}
                  >
                    <ArrowRight size={10} color="var(--accent-amber)" />
                    <span className="badge badge-amber" style={{ fontSize: '0.6rem', padding: '0.05rem 0.25rem' }}>
                      {c.relationship}
                    </span>
                    <span
                      style={{
                        color: 'var(--text-ivory-primary)',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                      title={c.targetName}
                    >
                      {c.targetName}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Quick Action Footer */}
          <div
            style={{
              display: 'flex',
              gap: '0.35rem',
              marginTop: '0.2rem',
              paddingTop: '0.35rem',
              borderTop: '1px solid var(--border-subtle)',
            }}
          >
            <button
              type="button"
              className="action-chip-btn"
              style={{ flex: 1, justifyContent: 'center' }}
              onClick={(e) => {
                e.stopPropagation();
                onSelectNode?.(hoverCard.id);
                setHoverCard(null);
              }}
              title="Inspect full case notes and evidence in right panel"
            >
              <FileText size={11} />
              <span>Full Dossier</span>
            </button>
            <button
              type="button"
              className="action-chip-btn"
              style={{ flex: 1, justifyContent: 'center' }}
              onClick={(e) => {
                e.stopPropagation();
                onSelectEntityForQuestion?.(hoverCard.name);
                setHoverCard(null);
              }}
              title="Ask about this entity in Question Engine"
            >
              <Sparkles size={11} color="var(--accent-amber)" />
              <span>Ask Query</span>
            </button>
          </div>
        </div>
      )}

      {/* Canvas Overlay Controls */}
      <div
        style={{
          position: 'absolute',
          bottom: '1rem',
          left: '1rem',
          display: 'flex',
          gap: '0.35rem',
          backgroundColor: 'var(--bg-secondary)',
          border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-md)',
          padding: '0.25rem',
          zIndex: 10,
          boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
        }}
      >
        <button
          onClick={() => cyRef.current?.zoom(cyRef.current.zoom() * 1.25)}
          className="btn"
          style={{ padding: '0.4rem', border: 'none', background: 'transparent' }}
          title="Zoom In"
        >
          <ZoomIn size={15} />
        </button>
        <button
          onClick={() => cyRef.current?.zoom(cyRef.current.zoom() * 0.8)}
          className="btn"
          style={{ padding: '0.4rem', border: 'none', background: 'transparent' }}
          title="Zoom Out"
        >
          <ZoomOut size={15} />
        </button>
        <button
          onClick={() => cyRef.current?.fit(undefined, 40)}
          className="btn"
          style={{ padding: '0.4rem', border: 'none', background: 'transparent' }}
          title="Fit View"
        >
          <Maximize2 size={15} />
        </button>
      </div>

      {loading && (
        <div
          style={{
            position: 'absolute',
            top: '1rem',
            left: '50%',
            transform: 'translateX(-50%)',
            backgroundColor: 'var(--bg-card)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-md)',
            padding: '0.4rem 0.85rem',
            fontSize: '0.775rem',
            color: 'var(--accent-amber-light)',
            zIndex: 10,
            boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
          }}
        >
          Updating investigation canvas...
        </div>
      )}
    </div>
  );
}
