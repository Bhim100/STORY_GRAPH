import React, { useState, useEffect, useCallback } from 'react';
import { Header } from './components/Header';
import { ChapterSelector } from './components/ChapterSelector';
import { GraphCanvas } from './components/GraphCanvas';
import { DetailsPanel } from './components/DetailsPanel';
import { QuestionPanel } from './components/QuestionPanel';
import { ErrorBoundary } from './components/ErrorBoundary';
import { Library } from './components/Library';
import { AddBookModal } from './components/AddBookModal';
import { ManuscriptReader } from './components/ManuscriptReader';
import { Clock, Info, BookOpen } from 'lucide-react';
import {
  fetchHealth,
  fetchStory,
  fetchGraph,
  fetchNodeDetails,
  askQuestion,
} from './services/api';

export default function App() {
  // Navigation / View State: 'library' or 'graph'
  const [currentView, setCurrentView] = useState('library');
  const [selectedBook, setSelectedBook] = useState(null);
  const [isAddBookOpen, setIsAddBookOpen] = useState(false);
  const [droppedFileForModal, setDroppedFileForModal] = useState(null);
  const [libraryRefreshTrigger, setLibraryRefreshTrigger] = useState(0);

  // Graph / Investigation State
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
  const [activeTab, setActiveTab] = useState('all'); // 'all', 'dossier'

  // Initialize DB health status on mount
  useEffect(() => {
    async function checkHealth() {
      try {
        const health = await fetchHealth();
        setDbStatus(health.status);
      } catch (e) {
        setDbStatus('error');
      }
    }
    checkHealth();
  }, []);

  // When a book is selected from the library
  const handleSelectBook = (book) => {
    setSelectedBook(book);
    setCurrentChapter(1);
    setSelectedNodeId(null);
    setNodeDetails(null);
    setAnswerResult(null);
    setCurrentView('graph');
  };

  // Load story metadata when selectedBook changes
  useEffect(() => {
    if (!selectedBook) return;
    async function loadStoryMeta() {
      try {
        const storyData = await fetchStory(selectedBook.id);
        setStory(storyData);
      } catch (e) {
        setStory({
          title: selectedBook.title,
          max_chapters: selectedBook.max_chapters || 8,
          status: selectedBook.status,
          status_message: selectedBook.status_message,
        });
      }
    }
    loadStoryMeta();
  }, [selectedBook]);

  // Fetch graph whenever currentChapter or selectedBook changes
  const loadGraph = useCallback(async (chapter, bookId) => {
    if (!bookId) return;
    setLoadingGraph(true);
    try {
      const data = await fetchGraph(chapter, bookId);
      setGraphData(data);
    } catch (err) {
      console.error('Failed to load graph:', err);
      setGraphData({ nodes: [], edges: [] });
    } finally {
      setLoadingGraph(false);
    }
  }, []);

  useEffect(() => {
    if (currentView === 'graph' && selectedBook) {
      loadGraph(currentChapter, selectedBook.id);
      setAnswerResult(null);

      if (selectedNodeId) {
        loadNodeDetails(selectedNodeId, currentChapter, selectedBook.id);
      }
    }
  }, [currentChapter, selectedBook, currentView, loadGraph]);

  // Load details for a selected node
  const loadNodeDetails = async (nodeId, chapter, bookId) => {
    if (!nodeId || !bookId) {
      setNodeDetails(null);
      return;
    }
    setLoadingDetails(true);
    try {
      const details = await fetchNodeDetails(nodeId, chapter, bookId);
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

  const handleSelectNode = useCallback((nodeId) => {
    setSelectedNodeId(nodeId);
    if (nodeId && selectedBook) {
      loadNodeDetails(nodeId, currentChapter, selectedBook.id);
    } else {
      setNodeDetails(null);
    }
  }, [currentChapter, selectedBook]);

  const handleAskQuestion = async (queryText) => {
    if (!selectedBook) return;
    setLoadingAnswer(true);
    try {
      const result = await askQuestion(queryText, currentChapter, selectedBook.id);
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

  const handleSelectEntityForQuestion = useCallback((entityName) => {
    setActiveTab('all');
    setSuggestedQuestion(`How is ${entityName} connected to the story?`);
  }, []);

  const handleBookAdded = (newBook) => {
    setLibraryRefreshTrigger((prev) => prev + 1);
    if (newBook && newBook.id) {
      handleSelectBook(newBook);
      if (newBook.status === 'import_pending') {
        setActiveTab('manuscript');
      }
    }
  };

  return (
    <>
      {currentView === 'library' ? (
        <Library
          onSelectBook={handleSelectBook}
          onOpenAddBook={() => {
            setDroppedFileForModal(null);
            setIsAddBookOpen(true);
          }}
          onDropStoryFile={(file) => {
            setDroppedFileForModal(file);
            setIsAddBookOpen(true);
          }}
          dbStatus={dbStatus}
          refreshTrigger={libraryRefreshTrigger}
        />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', width: '100vw', overflow: 'hidden' }}>
          {/* Top Header with Back to Library navigation */}
          <Header
            story={story || selectedBook}
            chapter={currentChapter}
            dbStatus={dbStatus}
            loading={loadingGraph}
            onRefresh={() => loadGraph(currentChapter, selectedBook?.id)}
            onBackToLibrary={() => setCurrentView('library')}
          />

          {/* Reading Progress Stepper */}
          <ChapterSelector
            currentChapter={currentChapter}
            maxChapters={story?.max_chapters || selectedBook?.max_chapters || 8}
            onChapterChange={(newChapter) => setCurrentChapter(newChapter)}
          />

          {/* Import Pending Notice Banner if graph relation extraction is pending */}
          {selectedBook?.status === 'import_pending' && (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.75rem',
              padding: '0.65rem 1.25rem',
              backgroundColor: 'var(--accent-amber-bg)',
              borderBottom: '1px solid rgba(217, 119, 6, 0.25)',
              fontSize: '0.775rem',
              color: 'var(--text-ivory-secondary)',
            }}>
              <Clock size={15} style={{ color: 'var(--accent-amber)', flexShrink: 0 }} />
              <span>
                <strong>Manuscript Ingestion Mode:</strong> Text parsed into {selectedBook.max_chapters} chapters with reading boundaries preserved. Automated relation extraction is not yet configured for this manuscript; candidate entities and text are preserved.
              </span>
            </div>
          )}

          {/* Main Investigation Workspace */}
          <div style={{ display: 'flex', flex: 1, position: 'relative', overflow: 'hidden' }}>
            {/* Interactive Graph Canvas */}
            <div style={{ flex: 1, position: 'relative', height: '100%' }}>
              <GraphCanvas
                elements={graphData}
                selectedNodeId={selectedNodeId}
                highlightedPath={answerResult?.path}
                onSelectNode={handleSelectNode}
                onSelectEntityForQuestion={handleSelectEntityForQuestion}
                loading={loadingGraph}
              />

              {/* Empty Graph Canvas Callout for Text Manuscripts */}
              {!loadingGraph && graphData.nodes.length === 0 && (
                <div style={{
                  position: 'absolute',
                  top: '50%',
                  left: '50%',
                  transform: 'translate(-50%, -50%)',
                  padding: '1.75rem 2rem',
                  backgroundColor: 'rgba(22, 25, 30, 0.94)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: 'var(--radius-lg)',
                  textAlign: 'center',
                  maxWidth: '440px',
                  backdropFilter: 'blur(10px)',
                  boxShadow: '0 16px 40px rgba(0, 0, 0, 0.65)',
                  zIndex: 5,
                }}>
                  <BookOpen size={32} style={{ color: 'var(--accent-amber)', margin: '0 auto 0.75rem auto' }} />
                  <h3 style={{ fontSize: '1.1rem', fontFamily: 'var(--font-serif)', color: 'var(--text-ivory-primary)', marginBottom: '0.4rem' }}>
                    Chapter {currentChapter} Manuscript Ready
                  </h3>
                  <p style={{ fontSize: '0.8rem', color: 'var(--text-ivory-muted)', marginBottom: '1.25rem', lineHeight: 1.5 }}>
                    Read this chapter's text in the Manuscript reader or extract candidate narrative entities to populate the visual story graph.
                  </p>
                  <div style={{ display: 'flex', gap: '0.65rem', justifyContent: 'center' }}>
                    <button
                      onClick={() => setActiveTab('manuscript')}
                      className="btn btn-primary"
                      style={{ padding: '0.5rem 1rem', fontSize: '0.8rem' }}
                    >
                      <BookOpen size={14} /> Open Manuscript Reader
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Right Sidebar: Question Engine & Case Notes & Manuscript */}
            <div style={{
              width: '440px',
              minWidth: '380px',
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
                    fontSize: '0.8rem',
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
                    fontSize: '0.8rem',
                  }}
                >
                  Dossier {selectedNodeId && `(1)`}
                </button>
                <button
                  onClick={() => setActiveTab('manuscript')}
                  className="btn"
                  style={{
                    flex: 1,
                    borderRadius: 0,
                    border: 'none',
                    backgroundColor: activeTab === 'manuscript' ? 'var(--bg-secondary)' : 'transparent',
                    color: activeTab === 'manuscript' ? 'var(--accent-amber-light)' : 'var(--text-ivory-muted)',
                    fontWeight: activeTab === 'manuscript' ? 600 : 400,
                    borderBottom: activeTab === 'manuscript' ? '2px solid var(--accent-amber)' : 'none',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '0.35rem',
                    fontSize: '0.8rem',
                  }}
                >
                  <BookOpen size={13} />
                  Manuscript
                </button>
              </div>

              {/* Scrollable Content */}
              <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>
                {activeTab === 'manuscript' ? (
                  <ErrorBoundary onReset={() => setActiveTab('all')}>
                    <ManuscriptReader
                      bookId={selectedBook?.id}
                      currentChapter={currentChapter}
                      maxChapters={story?.max_chapters || selectedBook?.max_chapters || 8}
                      bookStatus={selectedBook?.status}
                      onChapterChange={(newCh) => setCurrentChapter(newCh)}
                      onGraphExtracted={(updated) => {
                        setSelectedBook(updated);
                        loadGraph(currentChapter, updated.id);
                      }}
                      onSelectEntity={handleSelectEntityForQuestion}
                    />
                  </ErrorBoundary>
                ) : activeTab === 'all' ? (
                  <div style={{ padding: '1rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                    <ErrorBoundary onReset={() => setAnswerResult(null)}>
                      <QuestionPanel
                        currentChapter={currentChapter}
                        onAskQuestion={handleAskQuestion}
                        loading={loadingAnswer}
                        answerResult={answerResult}
                        onDismissAnswer={() => setAnswerResult(null)}
                        onSelectNode={handleSelectNode}
                        initialQuestion={suggestedQuestion}
                      />
                    </ErrorBoundary>
                    <ErrorBoundary onReset={() => handleSelectNode(null)}>
                      <DetailsPanel
                        details={nodeDetails}
                        loading={loadingDetails}
                        onClose={() => handleSelectNode(null)}
                        onSelectEntityForQuestion={handleSelectEntityForQuestion}
                      />
                    </ErrorBoundary>
                  </div>
                ) : (
                  <div style={{ padding: '1rem' }}>
                    <ErrorBoundary onReset={() => handleSelectNode(null)}>
                      <DetailsPanel
                        details={nodeDetails}
                        loading={loadingDetails}
                        onClose={() => handleSelectNode(null)}
                        onSelectEntityForQuestion={handleSelectEntityForQuestion}
                      />
                    </ErrorBoundary>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Add Book Modal Dialog */}
      <AddBookModal
        isOpen={isAddBookOpen}
        onClose={() => {
          setIsAddBookOpen(false);
          setDroppedFileForModal(null);
        }}
        onBookAdded={handleBookAdded}
        initialFile={droppedFileForModal}
      />
    </>
  );
}
