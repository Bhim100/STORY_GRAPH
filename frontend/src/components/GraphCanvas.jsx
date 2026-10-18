import React, { useState, useEffect, useRef, useMemo } from 'react';
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
  Layers,
  LayoutGrid,
  RefreshCw,
  Filter,
  RotateCcw,
  Target,
  Eye,
  EyeOff,
} from 'lucide-react';

// Generous, spacious deterministic spatial seeds for mystery entities.
const STABLE_NODE_SEEDS = {
  // Characters: Elias (center victim), Mara & Halden (wide flanks), Edith & Ines (inner lower), Jonas & Ruth (outer wings)
  c_elias_thorne: { x: 0, y: 0 },
  c_mara_voss: { x: -280, y: -50 },
  c_pavel_halden: { x: 280, y: -50 },
  c_edith_thorne: { x: -200, y: 240 },
  c_ines_calloway: { x: 200, y: 240 },
  c_jonas_reed: { x: -480, y: 80 },
  c_ruth_ames: { x: 480, y: -120 },
  c_tobias_quill: { x: 490, y: 260 },

  // Silver Blaze canonical seeds
  c_silver_blaze: { x: 0, y: 0 },
  c_colonel_ross: { x: -280, y: -140 },
  c_john_straker: { x: 280, y: -140 },
  c_sherlock_holmes: { x: -320, y: 160 },
  c_inspector_gregory: { x: 320, y: 160 },
  c_dr_watson: { x: -480, y: 260 },
  c_mrs_straker: { x: 480, y: -80 },
  c_silas_brown: { x: 0, y: -340 },
  c_fitzroy_simpson: { x: 180, y: 320 },
  c_ned_hunter: { x: -160, y: 100 },
  c_edith_baxter: { x: -200, y: 260 },

  // Events - placed close to their participating entities
  ev_disappearance_silver_blaze: { x: -120, y: -80 },
  ev_murder_straker: { x: 200, y: 40 },
  ev_arrest_simpson: { x: 260, y: 280 },
  ev_inquest: { x: 420, y: 40 },
  ev_discovery_silver_blaze: { x: -140, y: -260 },
  ev_wessex_cup: { x: -280, y: -260 },

  // Locations
  l_greenhouse: { x: -240, y: -380 },
  l_manor: { x: 240, y: -380 },
  l_harbor_inn: { x: 500, y: 440 },
  l_dartmoor: { x: 300, y: 400 },
  l_kings_pyland: { x: -340, y: 20 },
  l_mapleton: { x: 140, y: -340 },
  l_tavistock: { x: 420, y: 300 },
  l_bond_street: { x: 500, y: -240 },

  // Factions
  f_thorne_household: { x: 0, y: 380 },
  f_harbor_guild: { x: 480, y: 70 },
};

// Golden-angle spiral guarantees that arbitrary candidate or imported nodes never overlap
function getGenerousSpiralPosition(index) {
  const goldenAngle = 2.3999632;
  const radius = 240 + Math.sqrt(index) * 160;
  return {
    x: Math.cos(index * goldenAngle) * radius,
    y: Math.sin(index * goldenAngle) * radius,
  };
}

export function getEntityAssetUrl(node) {
  if (!node || !node.id) return null;
  if (node.kind === 'Character') return `/assets/avatars/${node.id}.jpg`;
  if (node.kind === 'Event') return `/assets/events/${node.id}.jpg`;
  if (node.kind === 'Faction') return `/assets/factions/${node.id}.jpg`;
  if (node.kind === 'Location') return `/assets/locations/${node.id}.jpg`;
  return null;
}

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
  const [activeLayout, setActiveLayout] = useState('cose');
  const hideTimerRef = useRef(null);

  // Filters State
  const [showFilterPanel, setShowFilterPanel] = useState(false);
  const [enabledEntityTypes, setEnabledEntityTypes] = useState({
    Character: true,
    Event: true,
    Location: true,
    Faction: true,
    Evidence: false, // Hidden by default, viewable in dossier
  });
  const [disabledRelTypes, setDisabledRelTypes] = useState(new Set());
  const [neighborhoodMode, setNeighborhoodMode] = useState('all'); // 'all', '1-hop', '2-hop'
  const [expandedNodes, setExpandedNodes] = useState(new Set());
  const [focusConnectedPlot, setFocusConnectedPlot] = useState(false);

  // Keep callback refs stable so cytoscape event listeners never need to be torn down
  const onSelectNodeRef = useRef(onSelectNode);
  const onSelectEntityForQuestionRef = useRef(onSelectEntityForQuestion);

  useEffect(() => {
    onSelectNodeRef.current = onSelectNode;
    onSelectEntityForQuestionRef.current = onSelectEntityForQuestion;
  });

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
      case 'Evidence':
        return <FileText size={13} style={{ color: '#10b981' }} aria-hidden="true" />;
      default:
        return <HelpCircle size={13} aria-hidden="true" />;
    }
  };

  // Collect all available relationship types from raw elements
  const availableRelTypes = useMemo(() => {
    if (!elements?.edges) return [];
    const types = new Set();
    elements.edges.forEach((e) => {
      const label = e.data?.label;
      if (label) types.add(label);
    });
    return Array.from(types).sort();
  }, [elements]);

  // Filter nodes & edges based on active filters and neighborhood focus
  const filteredElements = useMemo(() => {
    if (!elements || (!elements.nodes?.length && !elements.edges?.length)) {
      return { nodes: [], edges: [] };
    }

    const allNodes = elements.nodes || [];
    const allEdges = elements.edges || [];

    // 1. Entity type filtering
    let visibleNodes = allNodes.filter((n) => {
      const kind = n.data?.kind || 'Entity';
      return enabledEntityTypes[kind] !== false;
    });

    // 1b. Hide isolated entities if focusConnectedPlot is active
    if (focusConnectedPlot) {
      const connectedNodeIds = new Set();
      allEdges.forEach((e) => {
        const src = e.data?.source;
        const tgt = e.data?.target;
        const label = e.data?.label;
        if (src && tgt && !disabledRelTypes.has(label)) {
          connectedNodeIds.add(src);
          connectedNodeIds.add(tgt);
        }
      });
      visibleNodes = visibleNodes.filter((n) => connectedNodeIds.has(n.data?.id));
    }

    const visibleNodeIds = new Set(visibleNodes.map((n) => n.data?.id));

    // 2. Neighborhood filtering when selectedNodeId is active
    if (selectedNodeId && visibleNodeIds.has(selectedNodeId) && neighborhoodMode !== 'all') {
      const maxHops = neighborhoodMode === '1-hop' ? 1 : 2;
      const hopMap = new Map();
      hopMap.set(selectedNodeId, 0);

      // BFS for hops
      let currentHop = 0;
      let frontier = [selectedNodeId];

      while (currentHop < maxHops && frontier.length > 0) {
        currentHop++;
        const nextFrontier = [];
        allEdges.forEach((e) => {
          const src = e.data?.source;
          const tgt = e.data?.target;
          if (frontier.includes(src) && !hopMap.has(tgt) && visibleNodeIds.has(tgt)) {
            hopMap.set(tgt, currentHop);
            nextFrontier.push(tgt);
          } else if (frontier.includes(tgt) && !hopMap.has(src) && visibleNodeIds.has(src)) {
            hopMap.set(src, currentHop);
            nextFrontier.push(src);
          }
        });
        frontier = nextFrontier;
      }

      visibleNodes = visibleNodes.filter((n) => hopMap.has(n.data?.id));
    }

    const finalNodeIds = new Set(visibleNodes.map((n) => n.data?.id));

    // 3. Filter edges
    const seenEdgeKeys = new Set();
    const visibleEdges = allEdges.filter((e) => {
      const src = e.data?.source;
      const tgt = e.data?.target;
      const label = e.data?.label;

      if (!finalNodeIds.has(src) || !finalNodeIds.has(tgt)) return false;
      if (disabledRelTypes.has(label)) return false;

      // Deduplicate edges with the same source, target, and relationship
      const edgeKey = `${src}_${label}_${tgt}`;
      if (seenEdgeKeys.has(edgeKey)) return false;
      seenEdgeKeys.add(edgeKey);

      return true;
    });

    return { nodes: visibleNodes, edges: visibleEdges };
  }, [elements, enabledEntityTypes, disabledRelTypes, neighborhoodMode, selectedNodeId]);

  // 1. Initialize Cytoscape ONCE on mount
  useEffect(() => {
    if (!containerRef.current) return;

    const cy = cytoscape({
      container: containerRef.current,
      style: [
        // Default Base Node Style
        {
          selector: 'node',
          style: {
            label: 'data(label)',
            'font-family': 'Inter, sans-serif',
            'font-size': '11.5px',
            'font-weight': 700,
            'text-valign': 'bottom',
            'text-margin-y': 8,
            color: '#f8fafc',
            'text-background-color': '#0f172a',
            'text-background-opacity': 0.95,
            'text-background-padding': '4px 6px',
            'text-background-shape': 'roundrectangle',
            'text-border-width': 1,
            'text-border-color': '#334155',
            'text-max-width': '130px',
            'text-wrap': 'ellipsis',
            width: 52,
            height: 52,
            'border-width': 3,
            'border-color': '#475569',
            'background-color': '#1e293b',
            'transition-property': 'background-color, border-color, border-width, opacity, width, height',
            'transition-duration': '0.18s',
          },
        },
        // Character Nodes (Circle, warm ivory border)
        {
          selector: 'node[kind = "Character"]',
          style: {
            shape: 'ellipse',
            width: 54,
            height: 54,
            'background-image': 'data(avatar)',
            'background-fit': 'cover',
            'background-clip': 'node',
            'background-color': '#1e293b',
            'border-color': '#e2e8f0',
            'border-width': 3,
            'text-border-color': '#64748b',
          },
        },
        // Special Roles
        {
          selector: 'node[id = "c_silver_blaze"], node[id = "c_elias_thorne"], node[role *= "victim"], node[role *= "Victim"]',
          style: {
            'border-color': '#ef4444',
            'border-width': 4,
            'text-border-color': '#dc2626',
            color: '#fecaca',
          },
        },
        {
          selector: 'node[role *= "suspect"], node[role *= "Suspect"]',
          style: {
            'border-color': '#f59e0b',
            'border-width': 3.5,
            'text-border-color': '#d97706',
          },
        },
        // Event Nodes (Vivid Amber/Gold Diamond)
        {
          selector: 'node[kind = "Event"]',
          style: {
            shape: 'diamond',
            width: 56,
            height: 56,
            'background-image': 'data(avatar)',
            'background-fit': 'cover',
            'background-clip': 'node',
            'background-color': '#451a03',
            'border-color': '#f59e0b',
            'border-width': 3,
            'text-border-color': '#d97706',
          },
        },
        // Location Nodes (Architectural Emerald Hexagon)
        {
          selector: 'node[kind = "Location"]',
          style: {
            shape: 'round-hexagon',
            width: 58,
            height: 58,
            'background-image': 'data(avatar)',
            'background-fit': 'cover',
            'background-clip': 'node',
            'background-color': '#064e3b',
            'border-color': '#10b981',
            'border-width': 3,
            'text-border-color': '#059669',
          },
        },
        // Faction Nodes (Majestic Violet Rounded Rectangle)
        {
          selector: 'node[kind = "Faction"]',
          style: {
            shape: 'round-rectangle',
            width: 62,
            height: 48,
            'background-image': 'data(avatar)',
            'background-fit': 'cover',
            'background-clip': 'node',
            'background-color': '#3b0764',
            'border-color': '#c084fc',
            'border-width': 3,
            'text-border-color': '#9333ea',
          },
        },
        // Evidence Nodes (Clean Green Octagon)
        {
          selector: 'node[kind = "Evidence"]',
          style: {
            shape: 'octagon',
            width: 46,
            height: 46,
            'background-color': '#064e3b',
            'border-color': '#34d399',
            'border-width': 2.5,
            'text-border-color': '#059669',
          },
        },
        // Base Edge Style (Bezier curves with 60px step-size so multiple edges separate in distinct wide arcs)
        {
          selector: 'edge',
          style: {
            width: 2.3,
            'line-color': '#64748b',
            'target-arrow-color': '#64748b',
            'target-arrow-shape': 'triangle',
            'arrow-scale': 1.15,
            'curve-style': 'bezier',
            'control-point-step-size': 60,
            label: 'data(label)',
            'font-family': 'JetBrains Mono, monospace',
            'font-size': '9.5px',
            'font-weight': 700,
            color: '#f8fafc',
            'text-background-color': '#090d16',
            'text-background-opacity': 0.95,
            'text-background-padding': '4px',
            'text-background-shape': 'roundrectangle',
            'text-border-width': 1,
            'text-border-color': '#334155',
            'text-rotation': 'autorotate',
            'transition-property': 'line-color, width, opacity, z-index',
            'transition-duration': '0.18s',
          },
        },
        // Semantic Edge Colors:
        // 1. Conflict / Suspects / Allegations / Poisoning
        {
          selector: 'edge[label = "SUSPECTS"], edge[label = "ACCUSES"], edge[label = "TAMPERED_WITH"], edge[label = "KILLED"], edge[label = "CONFLICTS_WITH"], edge[label = "DISPUTES"], edge[label = "POISONED"]',
          style: {
            'line-color': '#f43f5e',
            'target-arrow-color': '#f43f5e',
            width: 2.6,
            'text-border-color': '#e11d48',
            color: '#ffe4e6',
          },
        },
        // 2. Ownership
        {
          selector: 'edge[label = "OWNS"], edge[label = "POSSESSES"], edge[label = "INHERITED"]',
          style: {
            'line-color': '#f59e0b',
            'target-arrow-color': '#f59e0b',
            width: 2.8,
            'text-border-color': '#d97706',
            color: '#fef3c7',
          },
        },
        // 3. Trainer
        {
          selector: 'edge[label = "TRAINER_OF"], edge[label = "CARES_FOR"], edge[label = "TRAINED"]',
          style: {
            'line-color': '#10b981',
            'target-arrow-color': '#10b981',
            width: 2.8,
            'text-border-color': '#059669',
            color: '#d1fae5',
          },
        },
        // 4. Employment
        {
          selector: 'edge[label = "EMPLOYS"], edge[label = "EMPLOYED_BY"], edge[label = "SERVES"], edge[label = "ASSISTANT_OF"]',
          style: {
            'line-color': '#38bdf8',
            'target-arrow-color': '#38bdf8',
            width: 2.6,
            'text-border-color': '#0284c7',
            color: '#e0f2fe',
          },
        },
        // 5. Investigation
        {
          selector: 'edge[label = "INVESTIGATES"], edge[label = "INQUIRES_INTO"], edge[label = "EXAMINES"]',
          style: {
            'line-color': '#a855f7',
            'target-arrow-color': '#a855f7',
            width: 2.8,
            'text-border-color': '#7e22ce',
            color: '#f3e8ff',
          },
        },
        // 6. Evidence / Support
        {
          selector: 'edge[label = "SUPPORTS"], edge[label = "CONFIRMED_BY"], edge[label = "CORROBORATES"], edge[label = "PROVES"], edge[label = "FOUND_WITH"]',
          style: {
            'line-color': '#34d399',
            'target-arrow-color': '#34d399',
            width: 2.6,
            'text-border-color': '#059669',
            color: '#d1fae5',
          },
        },
        // 7. Family / Affiliation
        {
          selector: 'edge[label = "FAMILY_OF"], edge[label = "MARRIED_TO"], edge[label = "PARENT_OF"], edge[label = "CHILD_OF"], edge[label = "AFFILIATED_WITH"], edge[label = "MEMBER_OF"]',
          style: {
            'line-color': '#818cf8',
            'target-arrow-color': '#818cf8',
            width: 2.5,
            'text-border-color': '#6366f1',
            color: '#e0e7ff',
          },
        },
        // 8. Occurrence / Location
        {
          selector: 'edge[label = "OCCURS_AT"], edge[label = "OCCURRED_AT"], edge[label = "LOCATED_AT"], edge[label = "RESIDES_AT"], edge[label = "VISITED"], edge[label = "DISCOVERED_AT"], edge[label = "PRESENT_AT"]',
          style: {
            'line-color': '#2dd4bf',
            'target-arrow-color': '#2dd4bf',
            width: 2.4,
            'text-border-color': '#0d9488',
            color: '#ccfbf1',
          },
        },
        // 9. Involvement
        {
          selector: 'edge[label = "INVOLVED_IN"], edge[label = "PARTICIPATED_IN"], edge[label = "APPEARS_IN"], edge[label = "WITNESSED"]',
          style: {
            'line-color': '#c084fc',
            'target-arrow-color': '#c084fc',
            width: 2.4,
            'text-border-color': '#9333ea',
            color: '#f3e8ff',
          },
        },
        // 10. Interacted With
        {
          selector: 'edge[label = "INTERACTED_WITH"]',
          style: {
            'line-color': '#94a3b8',
            'target-arrow-color': '#94a3b8',
            width: 2.2,
            'text-border-color': '#64748b',
            color: '#f1f5f9',
          },
        },
        // Hover highlight classes
        {
          selector: 'node.hover-highlight',
          style: {
            'border-width': 4.5,
            'border-color': '#f59e0b',
            'z-index': 100,
            opacity: 1,
            width: 60,
            height: 60,
          },
        },
        {
          selector: 'node.hover-neighbor',
          style: {
            'border-width': 3.5,
            opacity: 1,
            'z-index': 90,
          },
        },
        {
          selector: 'edge.hover-highlight',
          style: {
            width: 4,
            opacity: 1,
            'z-index': 95,
            'font-size': '11px',
            'arrow-scale': 1.4,
          },
        },
        {
          selector: '.hover-dimmed',
          style: {
            opacity: 0.18,
          },
        },
        // Selected Node - Amber glow
        {
          selector: 'node:selected',
          style: {
            'border-color': '#f59e0b',
            'border-width': 4.5,
            'z-index': 110,
          },
        },
        // Highlighted Path Nodes
        {
          selector: 'node.path-highlight',
          style: {
            'border-color': '#f59e0b',
            'border-width': 4.5,
            width: 58,
            height: 58,
            opacity: 1,
            'z-index': 120,
          },
        },
        // Highlighted Path Edges
        {
          selector: 'edge.path-highlight',
          style: {
            'line-color': '#f59e0b',
            'target-arrow-color': '#f59e0b',
            width: 4,
            opacity: 1,
            'z-index': 115,
            color: '#f59e0b',
            'font-weight': 800,
            'font-size': '11px',
          },
        },
        {
          selector: '.path-dimmed',
          style: {
            opacity: 0.12,
          },
        },
      ],
      userZoomingEnabled: true,
      userPanningEnabled: true,
      boxSelectionEnabled: false,
    });

    // Node Click -> select node
    cy.on('tap', 'node', (evt) => {
      const node = evt.target;
      onSelectNodeRef.current?.(node.id());
    });

    // Canvas Background Click -> deselect
    cy.on('tap', (evt) => {
      if (evt.target === cy) {
        onSelectNodeRef.current?.(null);
        setHoverCard(null);
      }
    });

    // Node Hover Interaction: Card & Neighborhood Highlighting
    cy.on('mouseover', 'node', (evt) => {
      const node = evt.target;
      if (hideTimerRef.current) {
        clearTimeout(hideTimerRef.current);
        hideTimerRef.current = null;
      }

      cy.elements().removeClass('hover-highlight hover-neighbor hover-dimmed');
      cy.elements().addClass('hover-dimmed');
      node.removeClass('hover-dimmed').addClass('hover-highlight');

      const connectedEdges = node.connectedEdges();
      connectedEdges.removeClass('hover-dimmed').addClass('hover-highlight');
      connectedEdges.connectedNodes().removeClass('hover-dimmed').addClass('hover-neighbor');

      const renderedPos = node.renderedPosition();
      const nodeData = node.data();
      const connections = [];

      connectedEdges.forEach((edge) => {
        const isOutgoing = edge.source().id() === node.id();
        const otherNode = isOutgoing ? edge.target() : edge.source();
        connections.push({
          relationship: edge.data('label') || edge.data('kind'),
          direction: isOutgoing ? 'outgoing' : 'incoming',
          targetName: otherNode.data('label'),
          targetId: otherNode.id(),
        });
      });

      const containerRect = containerRef.current?.getBoundingClientRect();
      const cardWidth = 290;
      const cardHeight = 220;

      let cardX = renderedPos.x + 24;
      let cardY = renderedPos.y - 40;

      if (containerRect) {
        if (cardX + cardWidth > containerRect.width - 20) {
          cardX = renderedPos.x - cardWidth - 24;
        }
        if (cardY + cardHeight > containerRect.height - 20) {
          cardY = Math.max(10, containerRect.height - cardHeight - 20);
        }
        if (cardY < 10) cardY = 10;
        if (cardX < 10) cardX = 10;
      }

      setHoverCard({
        id: node.id(),
        name: nodeData.label,
        kind: nodeData.kind,
        role: nodeData.role,
        aliases: nodeData.aliases || [],
        reveal_chapter: nodeData.reveal_chapter,
        connectionsCount: connectedEdges.length,
        connections: connections.slice(0, 6),
        x: cardX,
        y: cardY,
      });
    });

    // Node Hover Exit
    cy.on('mouseout', 'node', () => {
      cy.elements().removeClass('hover-highlight hover-neighbor hover-dimmed');
      hideTimerRef.current = setTimeout(() => {
        setHoverCard(null);
      }, 350);
    });

    cyRef.current = cy;

    // Automatic container resize observer
    let resizeObserver = null;
    if (typeof ResizeObserver !== 'undefined' && containerRef.current) {
      resizeObserver = new ResizeObserver(() => {
        if (cyRef.current) {
          cyRef.current.resize();
        }
      });
      resizeObserver.observe(containerRef.current);
    }

    return () => {
      if (resizeObserver) {
        resizeObserver.disconnect();
      }
      if (hideTimerRef.current) {
        clearTimeout(hideTimerRef.current);
      }
      cy.destroy();
    };
  }, []);

  // Layout dispatcher
  const applyLayout = (layoutType = activeLayout) => {
    const cy = cyRef.current;
    if (!cy || cy.nodes().length === 0) return;

    let layoutOpts;
    if (layoutType === 'cose') {
      layoutOpts = {
        name: 'cose',
        animate: true,
        animationDuration: 550,
        refresh: 20,
        fit: true,
        padding: 70,
        randomize: false,
        componentSpacing: 180,
        nodeRepulsion: () => 4000000,
        nodeOverlap: 100,
        idealEdgeLength: () => 200,
        edgeElasticity: () => 75,
        nestingFactor: 5,
        gravity: 20,
        numIter: 1000,
        initialTemp: 250,
        coolingFactor: 0.95,
        minTemp: 1.0,
      };
    } else if (layoutType === 'concentric') {
      layoutOpts = {
        name: 'concentric',
        animate: true,
        animationDuration: 550,
        fit: true,
        padding: 70,
        startAngle: (3 / 2) * Math.PI,
        clockwise: true,
        equidistant: false,
        minNodeSpacing: 90,
        concentric: (node) => {
          const kind = node.data('kind');
          const id = node.id();
          if (id === 'c_silver_blaze' || id === 'c_elias_thorne' || node.data('role')?.toLowerCase().includes('victim')) return 5;
          if (kind === 'Character') return 4;
          if (kind === 'Event') return 3;
          if (kind === 'Location') return 2;
          if (kind === 'Faction') return 1;
          return 0;
        },
        levelWidth: () => 1,
      };
    } else if (layoutType === 'grid') {
      layoutOpts = {
        name: 'grid',
        animate: true,
        animationDuration: 550,
        fit: true,
        padding: 70,
        avoidOverlap: true,
        avoidOverlapPadding: 70,
        nodeDimensionsIncludeLabels: true,
      };
    }

    const layout = cy.layout(layoutOpts);
    layout.run();
  };

  // 2. Update elements with spacious deterministic coordinates & run spaced layout
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;

    cy.batch(() => {
      cy.elements().remove();
      if (filteredElements && (filteredElements.nodes?.length > 0 || filteredElements.edges?.length > 0)) {
        const nodesWithPositions = (filteredElements.nodes || []).map((n, idx) => {
          const id = n.data?.id;
          const pos = STABLE_NODE_SEEDS[id] || getGenerousSpiralPosition(idx);
          let avatar = undefined;
          if (n.data?.kind === 'Character') {
            avatar = `/assets/avatars/${id}.jpg`;
          } else if (n.data?.kind === 'Event') {
            avatar = `/assets/events/${id}.jpg`;
          } else if (n.data?.kind === 'Faction') {
            avatar = `/assets/factions/${id}.jpg`;
          } else if (n.data?.kind === 'Location') {
            avatar = `/assets/locations/${id}.jpg`;
          }

          return {
            ...n,
            data: {
              ...n.data,
              avatar,
            },
            position: { ...pos },
          };
        });

        cy.add(nodesWithPositions);
        cy.add(filteredElements.edges || []);
      }
    });

    if (cy.nodes().length > 0) {
      applyLayout(activeLayout);
    }
  }, [filteredElements]);

  // 3. Handle Selection & Path Highlighting
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;

    cy.batch(() => {
      cy.elements().removeClass('path-highlight path-dimmed');

      if (highlightedPath && (highlightedPath.nodes?.length > 0 || highlightedPath.edges?.length > 0)) {
        const pathNodeIds = new Set(highlightedPath.nodes.map((n) => n.id));
        const pathClaimIds = new Set(
          (highlightedPath.relationships || highlightedPath.edges || []).map((r) => r.claim_id)
        );

        cy.elements().addClass('path-dimmed');

        cy.nodes().forEach((n) => {
          if (pathNodeIds.has(n.id())) {
            n.removeClass('path-dimmed').addClass('path-highlight');
          }
        });

        cy.edges().forEach((e) => {
          const claimId = e.data('claim_id');
          if (claimId && pathClaimIds.has(claimId)) {
            e.removeClass('path-dimmed').addClass('path-highlight');
          }
        });
      } else {
        cy.nodes().unselect();
        if (selectedNodeId) {
          const node = cy.getElementById(selectedNodeId);
          if (node.length > 0) {
            node.select();
          }
        }
      }
    });
  }, [selectedNodeId, highlightedPath]);

  // Action: Center on currently selected node
  const handleCenterSelection = () => {
    const cy = cyRef.current;
    if (!cy || !selectedNodeId) return;
    const node = cy.getElementById(selectedNodeId);
    if (node.length > 0) {
      cy.animate({
        center: { eles: node },
        zoom: Math.max(cy.zoom(), 1.1),
        duration: 400,
      });
    }
  };

  // Action: Fit entire graph
  const handleFitGraph = () => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.fit(undefined, 60);
  };

  // Action: Reset all filters
  const handleResetFilters = () => {
    setEnabledEntityTypes({
      Character: true,
      Event: true,
      Location: true,
      Faction: true,
      Evidence: false,
    });
    setDisabledRelTypes(new Set());
    setNeighborhoodMode('all');
    setExpandedNodes(new Set());
    setTimeout(() => {
      handleFitGraph();
    }, 100);
  };

  // Toggle single entity type
  const toggleEntityType = (kind) => {
    setEnabledEntityTypes((prev) => ({
      ...prev,
      [kind]: !prev[kind],
    }));
  };

  // Toggle relationship type
  const toggleRelType = (relType) => {
    setDisabledRelTypes((prev) => {
      const next = new Set(prev);
      if (next.has(relType)) {
        next.delete(relType);
      } else {
        next.add(relType);
      }
      return next;
    });
  };

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

          {/* Entity Name & Role with Avatar/Emblem */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
            {getEntityAssetUrl(hoverCard) && (
              <img
                src={getEntityAssetUrl(hoverCard)}
                alt={hoverCard.name}
                style={{
                  width: '38px',
                  height: '38px',
                  borderRadius: hoverCard.kind === 'Faction' || hoverCard.kind === 'Location' ? '8px' : '50%',
                  objectFit: 'cover',
                  border: `1.5px solid ${
                    hoverCard.kind === 'Faction'
                      ? 'var(--node-faction)'
                      : hoverCard.kind === 'Location'
                      ? 'var(--node-location)'
                      : hoverCard.kind === 'Event'
                      ? 'var(--node-event)'
                      : 'var(--accent-amber)'
                  }`,
                  boxShadow: '0 2px 6px rgba(0, 0, 0, 0.45)',
                  flexShrink: 0,
                }}
                onError={(e) => {
                  e.currentTarget.style.display = 'none';
                }}
              />
            )}
            <div style={{ flex: 1, minWidth: 0 }}>
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
                onSelectNodeRef.current?.(hoverCard.id);
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
                onSelectEntityForQuestionRef.current?.(hoverCard.name);
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

      {/* Top Filter & Legend Strip: Entity Types, Rel Types, & Neighborhood Focus */}
      <div
        style={{
          position: 'absolute',
          top: '0.85rem',
          left: '0.85rem',
          right: '0.85rem',
          display: 'flex',
          flexDirection: 'column',
          gap: '0.45rem',
          zIndex: 10,
          pointerEvents: 'none',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
          {/* Entity Type Filter Chips */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.35rem',
              backgroundColor: 'rgba(15, 17, 20, 0.94)',
              backdropFilter: 'blur(10px)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-md)',
              padding: '0.3rem 0.6rem',
              boxShadow: '0 4px 14px rgba(0,0,0,0.4)',
              fontSize: '0.72rem',
              pointerEvents: 'auto',
            }}
          >
            <span style={{ fontWeight: 600, color: 'var(--text-ivory-muted)', marginRight: '2px' }}>
              Entities:
            </span>
            {['Character', 'Event', 'Location', 'Faction', 'Evidence'].map((kind) => {
              const active = enabledEntityTypes[kind] !== false;
              return (
                <button
                  key={kind}
                  type="button"
                  onClick={() => toggleEntityType(kind)}
                  className="btn"
                  style={{
                    padding: '0.15rem 0.45rem',
                    fontSize: '0.675rem',
                    border: active ? '1px solid var(--accent-amber)' : '1px solid var(--border-subtle)',
                    background: active ? 'rgba(217, 119, 6, 0.14)' : 'transparent',
                    color: active ? 'var(--text-ivory-primary)' : 'var(--text-ivory-muted)',
                    opacity: active ? 1 : 0.6,
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '4px',
                    borderRadius: 'var(--radius-sm)',
                    cursor: 'pointer',
                  }}
                  title={active ? `Hide ${kind}s` : `Show ${kind}s`}
                >
                  {getKindIcon(kind)}
                  <span>{kind}</span>
                  {active ? <Eye size={10} color="#10b981" /> : <EyeOff size={10} color="#ef4444" />}
                </button>
              );
            })}
          </div>

          {/* Neighborhood Focus Controls (when a node is selected) */}
          {selectedNodeId && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.35rem',
                backgroundColor: 'rgba(15, 17, 20, 0.94)',
                backdropFilter: 'blur(10px)',
                border: '1px solid var(--border-active)',
                borderRadius: 'var(--radius-md)',
                padding: '0.3rem 0.6rem',
                boxShadow: '0 4px 14px rgba(0,0,0,0.4)',
                fontSize: '0.72rem',
                pointerEvents: 'auto',
              }}
            >
              <span style={{ fontWeight: 600, color: 'var(--accent-amber-light)', marginRight: '2px' }}>
                Neighborhood Focus:
              </span>
              {[
                { id: 'all', label: 'All' },
                { id: '1-hop', label: '1-Hop' },
                { id: '2-hop', label: '2-Hop' },
              ].map((opt) => (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => setNeighborhoodMode(opt.id)}
                  className="btn"
                  style={{
                    padding: '0.15rem 0.45rem',
                    fontSize: '0.675rem',
                    border: neighborhoodMode === opt.id ? '1px solid var(--accent-amber)' : '1px solid transparent',
                    background: neighborhoodMode === opt.id ? 'var(--bg-surface)' : 'transparent',
                    color: neighborhoodMode === opt.id ? 'var(--accent-amber-light)' : 'var(--text-ivory-muted)',
                    borderRadius: 'var(--radius-sm)',
                    cursor: 'pointer',
                  }}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          )}

          {/* Toggle Relationship Types Filter Strip */}
          <button
            type="button"
            onClick={() => setShowFilterPanel(!showFilterPanel)}
            className="btn"
            style={{
              padding: '0.3rem 0.6rem',
              fontSize: '0.72rem',
              backgroundColor: 'rgba(15, 17, 20, 0.94)',
              backdropFilter: 'blur(10px)',
              border: showFilterPanel ? '1px solid var(--accent-amber)' : '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-md)',
              color: showFilterPanel ? 'var(--accent-amber-light)' : 'var(--text-ivory-secondary)',
              boxShadow: '0 4px 14px rgba(0,0,0,0.4)',
              pointerEvents: 'auto',
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '5px',
            }}
            title="Filter by Relationship Type"
          >
            <Filter size={12} />
            <span>Relationship Types ({availableRelTypes.length})</span>
          </button>
        </div>

        {/* Collapsible Relationship Filter Toolbar */}
        {showFilterPanel && availableRelTypes.length > 0 && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.35rem',
              flexWrap: 'wrap',
              backgroundColor: 'rgba(15, 17, 20, 0.95)',
              backdropFilter: 'blur(12px)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-md)',
              padding: '0.4rem 0.65rem',
              boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
              fontSize: '0.7rem',
              pointerEvents: 'auto',
              maxWidth: '900px',
            }}
          >
            <span style={{ fontWeight: 600, color: 'var(--text-ivory-muted)', marginRight: '4px' }}>
              Filter Relations:
            </span>
            {availableRelTypes.map((relType) => {
              const active = !disabledRelTypes.has(relType);
              return (
                <button
                  key={relType}
                  type="button"
                  onClick={() => toggleRelType(relType)}
                  className="btn"
                  style={{
                    padding: '0.15rem 0.45rem',
                    fontSize: '0.65rem',
                    fontFamily: 'var(--font-mono)',
                    border: active ? '1px solid var(--border-active)' : '1px solid var(--border-subtle)',
                    background: active ? 'rgba(217, 119, 6, 0.12)' : 'transparent',
                    color: active ? 'var(--text-ivory-primary)' : 'var(--text-ivory-muted)',
                    opacity: active ? 1 : 0.5,
                    borderRadius: 'var(--radius-sm)',
                    cursor: 'pointer',
                  }}
                  title={active ? `Hide ${relType} edges` : `Show ${relType} edges`}
                >
                  <span>{relType}</span>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Canvas Bottom Overlay Controls: Zoom, Fit, Center Selection, Reset, Layout Selector, Untangle */}
      <div
        style={{
          position: 'absolute',
          bottom: '1rem',
          left: '1rem',
          display: 'flex',
          alignItems: 'center',
          gap: '0.4rem',
          backgroundColor: 'rgba(22, 25, 30, 0.95)',
          backdropFilter: 'blur(10px)',
          border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-md)',
          padding: '0.35rem 0.5rem',
          zIndex: 10,
          boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
        }}
      >
        {/* Zoom Controls */}
        <button
          onClick={() => cyRef.current?.zoom(cyRef.current.zoom() * 1.25)}
          className="btn"
          style={{ padding: '0.35rem', border: 'none', background: 'transparent' }}
          title="Zoom In"
        >
          <ZoomIn size={15} />
        </button>
        <button
          onClick={() => cyRef.current?.zoom(cyRef.current.zoom() * 0.8)}
          className="btn"
          style={{ padding: '0.35rem', border: 'none', background: 'transparent' }}
          title="Zoom Out"
        >
          <ZoomOut size={15} />
        </button>

        {/* Fit Graph */}
        <button
          onClick={handleFitGraph}
          className="btn"
          style={{ padding: '0.35rem 0.55rem', fontSize: '0.72rem', border: 'none', background: 'transparent', display: 'flex', alignItems: 'center', gap: '4px' }}
          title="Fit graph to view"
        >
          <Maximize2 size={13} />
          <span>Fit Graph</span>
        </button>

        {/* Center Selection */}
        <button
          onClick={handleCenterSelection}
          className="btn"
          disabled={!selectedNodeId}
          style={{
            padding: '0.35rem 0.55rem',
            fontSize: '0.72rem',
            border: 'none',
            background: 'transparent',
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            opacity: selectedNodeId ? 1 : 0.4,
            cursor: selectedNodeId ? 'pointer' : 'not-allowed',
          }}
          title={selectedNodeId ? "Center on selected entity" : "Select an entity first to center"}
        >
          <Target size={13} color={selectedNodeId ? "var(--accent-amber)" : "var(--text-ivory-muted)"} />
          <span>Center Selection</span>
        </button>

        {/* Reset Filters */}
        <button
          onClick={handleResetFilters}
          className="btn"
          style={{ padding: '0.35rem 0.55rem', fontSize: '0.72rem', border: 'none', background: 'transparent', display: 'flex', alignItems: 'center', gap: '4px' }}
          title="Reset all filters and view"
        >
          <RotateCcw size={13} />
          <span>Reset Filters</span>
        </button>

        <div style={{ width: '1px', height: '18px', backgroundColor: 'var(--border-subtle)', margin: '0 2px' }} />

        {/* Layout Mode Selector */}
        <div style={{ display: 'flex', gap: '0.2rem' }}>
          <button
            type="button"
            onClick={() => {
              setActiveLayout('cose');
              applyLayout('cose');
            }}
            className="btn"
            style={{
              padding: '0.3rem 0.55rem',
              fontSize: '0.72rem',
              border: activeLayout === 'cose' ? '1px solid var(--accent-amber)' : '1px solid transparent',
              background: activeLayout === 'cose' ? 'var(--bg-surface)' : 'transparent',
              color: activeLayout === 'cose' ? 'var(--accent-amber-light)' : 'var(--text-ivory-muted)',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
            }}
            title="Spaced Force-Directed Layout (Maximum separation, zero overlap)"
          >
            <Sparkles size={12} />
            <span>Spaced</span>
          </button>
          <button
            type="button"
            onClick={() => {
              setActiveLayout('concentric');
              applyLayout('concentric');
            }}
            className="btn"
            style={{
              padding: '0.3rem 0.55rem',
              fontSize: '0.72rem',
              border: activeLayout === 'concentric' ? '1px solid var(--accent-amber)' : '1px solid transparent',
              background: activeLayout === 'concentric' ? 'var(--bg-surface)' : 'transparent',
              color: activeLayout === 'concentric' ? 'var(--accent-amber-light)' : 'var(--text-ivory-muted)',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
            }}
            title="Concentric Rings Layout"
          >
            <Layers size={12} />
            <span>Rings</span>
          </button>
          <button
            type="button"
            onClick={() => {
              setActiveLayout('grid');
              applyLayout('grid');
            }}
            className="btn"
            style={{
              padding: '0.3rem 0.55rem',
              fontSize: '0.72rem',
              border: activeLayout === 'grid' ? '1px solid var(--accent-amber)' : '1px solid transparent',
              background: activeLayout === 'grid' ? 'var(--bg-surface)' : 'transparent',
              color: activeLayout === 'grid' ? 'var(--accent-amber-light)' : 'var(--text-ivory-muted)',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
            }}
            title="Grid Layout"
          >
            <LayoutGrid size={12} />
            <span>Grid</span>
          </button>
        </div>

        <div style={{ width: '1px', height: '18px', backgroundColor: 'var(--border-subtle)', margin: '0 2px' }} />

        {/* Focus Connected Plot / Hide Isolated Nodes */}
        <button
          type="button"
          onClick={() => setFocusConnectedPlot(!focusConnectedPlot)}
          className="btn"
          style={{
            padding: '0.3rem 0.55rem',
            fontSize: '0.72rem',
            border: focusConnectedPlot ? '1px solid var(--accent-amber)' : '1px solid var(--border-subtle)',
            background: focusConnectedPlot ? 'rgba(217, 119, 6, 0.2)' : 'transparent',
            color: focusConnectedPlot ? 'var(--accent-amber-light)' : 'var(--text-ivory-muted)',
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
          }}
          title={focusConnectedPlot ? "Show all entities including isolated ones" : "Focus connected plot (hide isolated entities with no visible edges)"}
        >
          {focusConnectedPlot ? <Eye size={12} /> : <EyeOff size={12} />}
          <span>{focusConnectedPlot ? 'Plot Focused' : 'Hide Isolated'}</span>
        </button>

        <div style={{ width: '1px', height: '18px', backgroundColor: 'var(--border-subtle)', margin: '0 2px' }} />

        {/* Untangle / Spread Nodes Button */}
        <button
          type="button"
          onClick={() => applyLayout('cose')}
          className="btn"
          style={{
            padding: '0.3rem 0.6rem',
            fontSize: '0.72rem',
            color: 'var(--accent-amber-light)',
            borderColor: 'var(--accent-amber)',
            background: 'rgba(217, 119, 6, 0.12)',
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            cursor: 'pointer',
          }}
          title="Untangle and repel all nodes apart"
        >
          <RefreshCw size={12} />
          <span>Untangle</span>
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
