import React, { useEffect, useRef } from 'react';
import cytoscape from 'cytoscape';
import { ZoomIn, ZoomOut, Maximize2 } from 'lucide-react';

export function GraphCanvas({
  elements,
  selectedNodeId,
  highlightedPath,
  onSelectNode,
  loading,
}) {
  const containerRef = useRef(null);
  const cyRef = useRef(null);

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

    cy.on('tap', 'node', (evt) => {
      const node = evt.target;
      onSelectNode?.(node.id());
    });

    cy.on('tap', (evt) => {
      if (evt.target === cy) {
        onSelectNode?.(null);
      }
    });

    cyRef.current = cy;

    return () => {
      cy.destroy();
    };
  }, []);

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

      {/* Canvas Overlay Controls */}
      <div style={{
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
      }}>
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
        <div style={{
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
        }}>
          Updating investigation canvas...
        </div>
      )}
    </div>
  );
}
