import React, { useState, useEffect, useCallback } from 'react';
import { Header } from './components/Header';
import { ChapterSelector } from './components/ChapterSelector';
import { GraphCanvas } from './components/GraphCanvas';
import { DetailsPanel } from './components/DetailsPanel';
import { QuestionPanel } from './components/QuestionPanel';
import {
  fetchHealth,
  fetchStory,
  fetchGraph,
  fetchNodeDetails,
  askQuestion,
} from './services/api';

export default function App() {
  const [currentChapter, setCurrentChapter] = useState(1);
  const [story, setStory] = useState(null);
  const [dbStatus, setDbStatus] = useState('connecting');

  const [graphData, setGraphData] = useState({ nodes: [], edges: [] });
  const [loadingGraph, setLoadingGraph] = useState(false);

  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [nodeDetails, setNodeDetails] = useState(null);
  const [loadingDetails, setLoadingDetails] = useState(false);

  const [answerResult, setAnswerResult] = useState(null);
  const [loadingAnswer, setLoadingAnswer] = useState(false);

  const [suggestedQuestion, setSuggestedQuestion] = useState('');
  const [activeTab, setActiveTab] = useState('all'); // 'all', 'questions', 'dossier'

  // Initialize story and health status
  useEffect(() => {
    async function init() {
      try {
        const health = await fetchHealth();
        setDbStatus(health.status);
      } catch (e) {
        setDbStatus('error');
      }

      try {
        const storyData = await fetchStory();
        setStory(storyData);
      } catch (e) {
        // Fallback default
        setStory({ title: 'The Glass Orchard', max_chapters: 8 });
      }
    }
    init();
  }, []);

  // Fetch graph whenever chapter changes
  const loadGraph = useCallback(async (chapter) => {
    setLoadingGraph(true);
    try {
      const data = await fetchGraph(chapter);
      setGraphData(data);
    } catch (err) {
      console.error('Failed to load graph:', err);
    } finally {
      setLoadingGraph(false);
    }
  }, []);

  useEffect(() => {
    loadGraph(currentChapter);
    // Clear path answer on chapter change to prevent cross-chapter leakage
    setAnswerResult(null);

    // Refresh node details at new chapter boundary if a node is selected
    if (selectedNodeId) {
      loadNodeDetails(selectedNodeId, currentChapter);
    }
  }, [currentChapter, loadGraph]);

  // Load details for a selected node
  const loadNodeDetails = async (nodeId, chapter) => {
    if (!nodeId) {
      setNodeDetails(null);
      return;
    }
    setLoadingDetails(true);
    try {
      const details = await fetchNodeDetails(nodeId, chapter);
      if (!details) {
        setSelectedNodeId(null);
        setNodeDetails(null);
      } else {
        setNodeDetails(details);
      }
    } catch (err) {
      console.error('Error fetching node details:', err);
      setNodeDetails(null);
    } finally {
      setLoadingDetails(false);
    }
  };

  const handleSelectNode = (nodeId) => {
    setSelectedNodeId(nodeId);
    if (nodeId) {
      loadNodeDetails(nodeId, currentChapter);
    } else {
      setNodeDetails(null);
    }
  };

  const handleAskQuestion = async (queryText) => {
    setLoadingAnswer(true);
    try {
      const result = await askQuestion(queryText, currentChapter);
      setAnswerResult(result);
    } catch (err) {
      setAnswerResult({
        status: 'error',
        answer: `Question service error: ${err.message || 'Service temporarily unavailable.'}`,
        nodes: [],
        relationships: [],
        evidence: [],
      });
    } finally {
      setLoadingAnswer(false);
    }
  };

  const handleSelectEntityForQuestion = (entityName) => {
    setSuggestedQuestion(`How is ${entityName} connected to the story?`);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', width: '100vw', overflow: 'hidden' }}>
      {/* Top Header */}
      <Header
        story={story}
        chapter={currentChapter}
        dbStatus={dbStatus}
        loading={loadingGraph}
        onRefresh={() => loadGraph(currentChapter)}
      />

      {/* Reading Progress Stepper */}
      <ChapterSelector
        currentChapter={currentChapter}
        maxChapters={story?.max_chapters || 8}
        onChapterChange={(newChapter) => setCurrentChapter(newChapter)}
      />

      {/* Main Investigation Workspace */}
      <div style={{ display: 'flex', flex: 1, position: 'relative', overflow: 'hidden' }}>
        {/* Interactive Graph Canvas */}
        <div style={{ flex: 1, position: 'relative', height: '100%' }}>
          <GraphCanvas
            elements={graphData}
            selectedNodeId={selectedNodeId}
            highlightedPath={answerResult?.path}
            onSelectNode={handleSelectNode}
            loading={loadingGraph}
          />
        </div>

        {/* Right Sidebar: Question Engine & Case Notes */}
        <div style={{
          width: '420px',
          minWidth: '360px',
          height: '100%',
          backgroundColor: 'var(--bg-secondary)',
          borderLeft: '1px solid var(--border-subtle)',
          display: 'flex',
          flexDirection: 'column',
          zIndex: 10,
        }}>
          {/* Sidebar Tab Toggle */}
          <div style={{
            display: 'flex',
            borderBottom: '1px solid var(--border-subtle)',
            backgroundColor: 'var(--bg-tertiary)',
          }}>
            <button
              onClick={() => setActiveTab('all')}
              className="btn"
              style={{
                flex: 1,
                borderRadius: 0,
                border: 'none',
                backgroundColor: activeTab === 'all' ? 'var(--bg-secondary)' : 'transparent',
                color: activeTab === 'all' ? 'var(--accent-amber-light)' : 'var(--text-ivory-muted)',
                fontWeight: activeTab === 'all' ? 600 : 400,
                borderBottom: activeTab === 'all' ? '2px solid var(--accent-amber)' : 'none',
              }}
            >
              Investigation Deck
            </button>
            <button
              onClick={() => setActiveTab('dossier')}
              className="btn"
              style={{
                flex: 1,
                borderRadius: 0,
                border: 'none',
                backgroundColor: activeTab === 'dossier' ? 'var(--bg-secondary)' : 'transparent',
                color: activeTab === 'dossier' ? 'var(--accent-amber-light)' : 'var(--text-ivory-muted)',
                fontWeight: activeTab === 'dossier' ? 600 : 400,
                borderBottom: activeTab === 'dossier' ? '2px solid var(--accent-amber)' : 'none',
              }}
            >
              Entity Dossier {selectedNodeId && `(1)`}
            </button>
          </div>

          {/* Scrollable Content */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '1rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {activeTab === 'all' ? (
              <>
                <QuestionPanel
                  currentChapter={currentChapter}
                  onAskQuestion={handleAskQuestion}
                  loading={loadingAnswer}
                  answerResult={answerResult}
                  onDismissAnswer={() => setAnswerResult(null)}
                  onSelectNode={handleSelectNode}
                  initialQuestion={suggestedQuestion}
                />
                <DetailsPanel
                  details={nodeDetails}
                  loading={loadingDetails}
                  onClose={() => handleSelectNode(null)}
                  onSelectEntityForQuestion={handleSelectEntityForQuestion}
                />
              </>
            ) : (
              <DetailsPanel
                details={nodeDetails}
                loading={loadingDetails}
                onClose={() => handleSelectNode(null)}
                onSelectEntityForQuestion={handleSelectEntityForQuestion}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
