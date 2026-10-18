import React, { useState, useEffect } from 'react';
import {
  Layers,
  BookOpen,
  Plus,
  Search,
  CheckCircle2,
  Clock,
  AlertTriangle,
  RefreshCw,
  FileText,
  ArrowRight,
  Database,
  Sparkles,
} from 'lucide-react';
import { fetchBooks } from '../services/api';

export function Library({ onSelectBook, onOpenAddBook, onDropStoryFile, dbStatus, refreshTrigger }) {
  const [books, setBooks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [isDragOverPage, setIsDragOverPage] = useState(false);

  const loadLibrary = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchBooks();
      setBooks(data.books || []);
    } catch (err) {
      console.error('Failed to load library books:', err);
      setError(err.message || 'Unable to connect to the StoryGraph library service.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadLibrary();
  }, [refreshTrigger]);

  const filteredBooks = books.filter((b) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      (b.title && b.title.toLowerCase().includes(q)) ||
      (b.author && b.author.toLowerCase().includes(q)) ||
      (b.description && b.description.toLowerCase().includes(q))
    );
  });

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setIsDragOverPage(true);
      }}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) {
          setIsDragOverPage(false);
        }
      }}
      onDrop={(e) => {
        e.preventDefault();
        setIsDragOverPage(false);
        const droppedFile = e.dataTransfer.files?.[0];
        if (droppedFile && onDropStoryFile) {
          onDropStoryFile(droppedFile);
        } else if (onOpenAddBook) {
          onOpenAddBook();
        }
      }}
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100vh',
        width: '100vw',
        backgroundColor: 'var(--bg-primary)',
        color: 'var(--text-ivory-primary)',
        overflowY: 'auto',
        position: 'relative',
      }}
    >
      {/* Drag & Drop Overlay */}
      {isDragOverPage && (
        <div style={{
          position: 'fixed',
          inset: 0,
          backgroundColor: 'rgba(15, 17, 20, 0.92)',
          zIndex: 9999,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '1rem',
          border: '3px dashed var(--accent-amber)',
          backdropFilter: 'blur(6px)',
          pointerEvents: 'none',
        }}>
          <div style={{
            width: '70px',
            height: '70px',
            borderRadius: '50%',
            backgroundColor: 'var(--accent-amber-bg)',
            border: '2px solid var(--accent-amber)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--accent-amber)',
          }}>
            <FileText size={36} />
          </div>
          <h2 style={{
            fontSize: '1.75rem',
            fontFamily: 'var(--font-serif)',
            color: 'var(--text-ivory-primary)',
            margin: 0,
          }}>
            Drop Story Text File (.txt) Here
          </h2>
          <p style={{ fontSize: '0.9rem', color: 'var(--text-ivory-secondary)', maxWidth: '450px', textAlign: 'center' }}>
            StoryGraph will segment your story into chapters, enforce progressive reading boundaries, and extract candidate narrative entities.
          </p>
        </div>
      )}

      {/* Top Navbar */}
      <header style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '1rem 2rem',
        backgroundColor: 'var(--bg-secondary)',
        borderBottom: '1px solid var(--border-subtle)',
        position: 'sticky',
        top: 0,
        zIndex: 50,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <div style={{
            width: '34px',
            height: '34px',
            borderRadius: 'var(--radius-sm)',
            backgroundColor: 'var(--accent-amber-bg)',
            border: '1px solid var(--accent-amber)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--accent-amber)',
          }}>
            <Layers size={20} />
          </div>
          <div>
            <h1 style={{
              fontSize: '1.25rem',
              fontFamily: 'var(--font-serif)',
              letterSpacing: '0.04em',
              color: 'var(--text-ivory-primary)',
              lineHeight: 1.1,
            }}>
              StoryGraph
            </h1>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-ivory-muted)' }}>
              Investigative Literary Knowledge Graphs
            </p>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          {/* FalkorDB status indicator */}
          <div
            className={`badge ${dbStatus === 'ok' ? 'badge-amber' : ''}`}
            style={{ fontSize: '0.75rem' }}
            title={dbStatus === 'ok' ? 'Connected to FalkorDB graph backend' : 'FalkorDB is offline'}
          >
            <Database size={13} />
            {dbStatus === 'ok' ? 'FalkorDB Connected' : 'Database Offline'}
          </div>

          {/* Primary Quick-Add Action for Text Stories */}
          <button
            onClick={onOpenAddBook}
            className="btn btn-primary"
            style={{
              padding: '0.55rem 1.1rem',
              backgroundColor: 'var(--accent-amber)',
              color: '#0f1114',
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              gap: '0.45rem',
              boxShadow: '0 2px 8px rgba(217, 119, 6, 0.35)',
            }}
          >
            <FileText size={16} />
            Add Story (.txt)
          </button>

          <button
            onClick={onOpenAddBook}
            className="btn btn-secondary"
            style={{ padding: '0.55rem 0.9rem' }}
            title="Import from other formats or URLs"
          >
            <Plus size={15} />
            More Sources
          </button>
        </div>
      </header>

      {/* Main Library Viewport */}
      <main style={{
        maxWidth: '1200px',
        width: '100%',
        margin: '0 auto',
        padding: '2.5rem 1.5rem',
        display: 'flex',
        flexDirection: 'column',
        gap: '2rem',
        flex: 1,
      }}>
        {/* Hero Section */}
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-end',
          flexWrap: 'wrap',
          gap: '1rem',
          borderBottom: '1px solid var(--border-subtle)',
          paddingBottom: '1.5rem',
        }}>
          <div>
            <span style={{
              fontSize: '0.75rem',
              textTransform: 'uppercase',
              letterSpacing: '0.12em',
              color: 'var(--accent-amber-light)',
              fontWeight: 600,
              display: 'block',
              marginBottom: '0.25rem',
            }}>
              Investigation Archive
            </span>
            <h2 style={{
              fontSize: '2rem',
              fontFamily: 'var(--font-serif)',
              letterSpacing: '0.02em',
              color: 'var(--text-ivory-primary)',
              lineHeight: 1.2,
            }}>
              Choose a Story
            </h2>
            <p style={{
              fontSize: '0.9rem',
              color: 'var(--text-ivory-secondary)',
              marginTop: '0.35rem',
              maxWidth: '650px',
            }}>
              Select an archived mystery to open its emergent story graph, trace evidence across chapters, or ingest a new manuscript to establish progressive reading boundaries.
            </p>
          </div>

          {/* Search bar */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', minWidth: '280px' }}>
            <div style={{ position: 'relative', width: '100%' }}>
              <Search
                size={16}
                style={{
                  position: 'absolute',
                  left: '0.75rem',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  color: 'var(--text-ivory-muted)',
                }}
              />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search stories or authors..."
                className="input-text"
                style={{ paddingLeft: '2.25rem' }}
                aria-label="Search stories"
              />
            </div>
            <button
              onClick={loadLibrary}
              disabled={loading}
              className="btn"
              title="Refresh library catalog"
              style={{ padding: '0.65rem' }}
              aria-label="Refresh library"
            >
              <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
            </button>
          </div>
        </div>

        {/* Database Unavailable Banner if down */}
        {dbStatus !== 'ok' && (
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.75rem',
            padding: '1rem 1.25rem',
            backgroundColor: 'rgba(239, 68, 68, 0.12)',
            border: '1px solid rgba(239, 68, 68, 0.35)',
            borderRadius: 'var(--radius-md)',
            color: '#fca5a5',
            fontSize: '0.85rem',
          }}>
            <AlertTriangle size={18} style={{ flexShrink: 0, color: '#f87171' }} />
            <div style={{ flex: 1 }}>
              <strong style={{ color: '#f87171' }}>Graph Database Offline:</strong> FalkorDB connection is currently unavailable on localhost:6379. Library browsing is accessible, but graph exploration requires the database service to be running.
            </div>
          </div>
        )}

        {/* Error Banner */}
        {error && (
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '1rem 1.25rem',
            backgroundColor: 'rgba(239, 68, 68, 0.12)',
            border: '1px solid rgba(239, 68, 68, 0.35)',
            borderRadius: 'var(--radius-md)',
            color: '#fca5a5',
            fontSize: '0.85rem',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <AlertTriangle size={18} style={{ color: '#f87171', flexShrink: 0 }} />
              <span>{error}</span>
            </div>
            <button onClick={loadLibrary} className="btn" style={{ fontSize: '0.75rem' }}>
              Retry
            </button>
          </div>
        )}

        {/* Loading Skeleton */}
        {loading && (
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))',
            gap: '1.5rem',
          }}>
            {[1, 2, 3].map((n) => (
              <div
                key={n}
                style={{
                  height: '240px',
                  backgroundColor: 'var(--bg-secondary)',
                  borderRadius: 'var(--radius-lg)',
                  border: '1px solid var(--border-subtle)',
                  padding: '1.5rem',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '1rem',
                  opacity: 0.6,
                }}
              >
                <div style={{ height: '24px', width: '60%', backgroundColor: 'var(--bg-surface)', borderRadius: '4px' }} />
                <div style={{ height: '16px', width: '40%', backgroundColor: 'var(--bg-surface)', borderRadius: '4px' }} />
                <div style={{ height: '60px', width: '100%', backgroundColor: 'var(--bg-surface)', borderRadius: '4px' }} />
                <div style={{ height: '36px', width: '100%', backgroundColor: 'var(--bg-surface)', borderRadius: '4px', marginTop: 'auto' }} />
              </div>
            ))}
          </div>
        )}

        {/* Empty State */}
        {!loading && !error && filteredBooks.length === 0 && (
          <div style={{
            textAlign: 'center',
            padding: '4rem 1rem',
            backgroundColor: 'var(--bg-secondary)',
            borderRadius: 'var(--radius-lg)',
            border: '1px dashed var(--border-subtle)',
          }}>
            <BookOpen size={48} style={{ color: 'var(--text-ivory-muted)', margin: '0 auto 1rem', opacity: 0.5 }} />
            <h3 style={{ fontSize: '1.15rem', fontFamily: 'var(--font-serif)', color: 'var(--text-ivory-primary)', marginBottom: '0.5rem' }}>
              {searchQuery ? 'No Matching Manuscripts' : 'Your Library is Empty'}
            </h3>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-ivory-muted)', maxWidth: '420px', margin: '0 auto 1.5rem' }}>
              {searchQuery
                ? `No books match the search term "${searchQuery}". Try a different keyword or reset search.`
                : 'Add a new book or manuscript to begin building and navigating its knowledge graph.'}
            </p>
            {searchQuery ? (
              <button onClick={() => setSearchQuery('')} className="btn">
                Clear Search Filter
              </button>
            ) : (
              <button onClick={onOpenAddBook} className="btn btn-primary">
                <Plus size={16} /> Add Your First Book
              </button>
            )}
          </div>
        )}

        {/* Books Grid */}
        {!loading && filteredBooks.length > 0 && (
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(350px, 1fr))',
            gap: '1.5rem',
          }}>
            {filteredBooks.map((book) => {
              const isReady = book.status === 'ready';
              const isPending = book.status === 'import_pending';
              const isError = book.status === 'error';

              return (
                <article
                  key={book.id}
                  style={{
                    backgroundColor: 'var(--bg-secondary)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-lg)',
                    padding: '1.5rem',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                    gap: '1.25rem',
                    transition: 'all 0.2s ease',
                    boxShadow: '0 4px 12px rgba(0, 0, 0, 0.25)',
                    position: 'relative',
                    overflow: 'hidden',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.borderColor = 'var(--accent-amber)';
                    e.currentTarget.style.transform = 'translateY(-2px)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = 'var(--border-subtle)';
                    e.currentTarget.style.transform = 'translateY(0)';
                  }}
                >
                  {/* Subtle Top Accent Bar */}
                  <div style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    right: 0,
                    height: '3px',
                    backgroundColor: isReady ? 'var(--accent-amber)' : isPending ? '#fbbf24' : '#ef4444',
                  }} />

                  {/* Card Header & Badges */}
                  <div>
                    <div style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: '0.5rem',
                      marginBottom: '0.65rem',
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                        <span style={{
                          fontSize: '0.675rem',
                          textTransform: 'uppercase',
                          fontWeight: 700,
                          letterSpacing: '0.06em',
                          padding: '0.2rem 0.5rem',
                          borderRadius: 'var(--radius-sm)',
                          backgroundColor: 'var(--bg-tertiary)',
                          color: 'var(--text-ivory-secondary)',
                          border: '1px solid var(--border-subtle)',
                        }}>
                          {book.format?.toUpperCase() || 'TXT'}
                        </span>
                        <span style={{
                          fontSize: '0.675rem',
                          color: 'var(--text-ivory-muted)',
                        }}>
                          &bull; {book.max_chapters} {book.max_chapters === 1 ? 'Chapter' : 'Chapters'}
                        </span>
                      </div>

                      {/* Status Badge */}
                      {isReady && (
                        <span style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '0.3rem',
                          fontSize: '0.7rem',
                          color: '#4ade80',
                          backgroundColor: 'rgba(34, 197, 94, 0.1)',
                          padding: '0.2rem 0.5rem',
                          borderRadius: 'var(--radius-sm)',
                          border: '1px solid rgba(34, 197, 94, 0.25)',
                        }}>
                          <CheckCircle2 size={12} /> Graph Ready
                        </span>
                      )}
                      {isPending && (
                        <span style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '0.3rem',
                          fontSize: '0.7rem',
                          color: 'var(--accent-amber-light)',
                          backgroundColor: 'var(--accent-amber-bg)',
                          padding: '0.2rem 0.5rem',
                          borderRadius: 'var(--radius-sm)',
                          border: '1px solid rgba(217, 119, 6, 0.3)',
                        }}>
                          <Clock size={12} /> Text Parsed • Graph Pending
                        </span>
                      )}
                      {isError && (
                        <span style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '0.3rem',
                          fontSize: '0.7rem',
                          color: '#f87171',
                          backgroundColor: 'rgba(239, 68, 68, 0.1)',
                          padding: '0.2rem 0.5rem',
                          borderRadius: 'var(--radius-sm)',
                          border: '1px solid rgba(239, 68, 68, 0.25)',
                        }}>
                          <AlertTriangle size={12} /> Ingestion Error
                        </span>
                      )}
                    </div>

                    {/* Book Title & Author */}
                    <h3 style={{
                      fontSize: '1.25rem',
                      fontFamily: 'var(--font-serif)',
                      color: 'var(--text-ivory-primary)',
                      lineHeight: 1.25,
                      marginBottom: '0.25rem',
                    }}>
                      {book.title}
                    </h3>
                    <p style={{
                      fontSize: '0.8rem',
                      color: 'var(--text-ivory-muted)',
                      fontWeight: 500,
                      marginBottom: '0.85rem',
                    }}>
                      By {book.author || 'Anonymous'}
                    </p>

                    {/* Description */}
                    <p style={{
                      fontSize: '0.825rem',
                      color: 'var(--text-ivory-secondary)',
                      lineHeight: 1.5,
                      display: '-webkit-box',
                      WebkitLineClamp: 3,
                      WebkitBoxOrient: 'vertical',
                      overflow: 'hidden',
                    }}>
                      {book.description || 'No description provided.'}
                    </p>
                  </div>

                  {/* Card Footer / Action */}
                  <div style={{
                    paddingTop: '1rem',
                    borderTop: '1px solid var(--border-subtle)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                  }}>
                    <span style={{
                      fontSize: '0.725rem',
                      color: isPending ? 'var(--accent-amber)' : 'var(--text-ivory-muted)',
                      fontStyle: isPending ? 'italic' : 'normal',
                    }}>
                      {isReady
                        ? 'Full graph & dossier active'
                        : isPending
                        ? 'Chapter boundaries active'
                        : 'Review logs'}
                    </span>

                    <button
                      onClick={() => onSelectBook(book)}
                      className="btn btn-primary"
                      style={{ padding: '0.45rem 0.85rem', fontSize: '0.8rem' }}
                      aria-label={`Open StoryGraph for ${book.title}`}
                    >
                      <Sparkles size={14} /> Open StoryGraph <ArrowRight size={14} />
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}
