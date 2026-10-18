import React, { useState, useEffect, useRef } from 'react';
import { X, Upload, Link, AlertTriangle, ShieldCheck, FileText, CheckCircle2, Loader2, Info, Sparkles } from 'lucide-react';
import { addBook } from '../services/api';

/**
 * Parses front-matter metadata from the opening page of a story manuscript.
 * Extracts title, author, and description/subtitle from standard literary formats:
 * - Gutenberg headers ("The Project Gutenberg eBook of <Title>, by <Author>")
 * - Tagged headers ("Title: ...", "Author: ...", "Written by: ...")
 * - Positional headers (e.g. Title line followed by "By Author" or "BY \n Author")
 * - Subtitles before chapters
 */
export function parseFirstPageMetadata(rawText, fallbackTitle = '') {
  const result = { title: '', author: '', description: '' };
  if (!rawText || !rawText.trim()) return result;

  const sample = rawText.slice(0, 4000);
  const lines = sample.split(/\r?\n/).map((l) => l.trim());

  // 1. Project Gutenberg header: "The Project Gutenberg eBook of Title, by Author"
  for (let i = 0; i < Math.min(lines.length, 30); i++) {
    const line = lines[i];
    const m = line.match(/The Project Gutenberg e?Book of\s+(.+?),\s+by\s+(.+)/i);
    if (m) {
      result.title = m[1].replace(/\[.*?\]/g, '').trim();
      result.author = m[2].replace(/\[.*?\]/g, '').trim();
      break;
    }
  }

  // 2. Key-value tags: Title: ..., Author: ..., Description: ...
  for (let i = 0; i < Math.min(lines.length, 40); i++) {
    const line = lines[i];
    if (!result.title) {
      const mt = line.match(/^(?:Title|TITLE)\s*:\s*(.+)$/i);
      if (mt) result.title = mt[1].trim();
    }
    if (!result.author) {
      const ma = line.match(/^(?:Author|AUTHOR|Written [Bb]y)\s*:\s*(.+)$/i);
      if (ma) result.author = ma[1].trim();
    }
    if (!result.description) {
      const md = line.match(/^(?:Description|Synopsis|Sub-?title)\s*:\s*(.+)$/i);
      if (md) result.description = md[1].trim();
    }
  }

  // 3. Positional scanning before first chapter marker
  const frontLines = [];
  for (const line of lines) {
    if (!line) continue;
    const lLow = line.toLowerCase();
    if (
      lLow.startsWith('chapter 1') ||
      lLow.startsWith('chapter i') ||
      lLow.startsWith('chapter one') ||
      lLow.startsWith('part 1') ||
      lLow.startsWith('part i') ||
      lLow.startsWith('act 1') ||
      lLow.startsWith('act i') ||
      lLow.startsWith('prologue') ||
      lLow.startsWith('contents') ||
      lLow.startsWith('table of contents') ||
      lLow.startsWith('*** start of')
    ) {
      break;
    }
    frontLines.push(line);
    if (frontLines.length > 30) break;
  }

  // Look for "by [Author]" or "BY [AUTHOR]" or standalone "by" line
  if (!result.author) {
    for (let i = 0; i < frontLines.length; i++) {
      const line = frontLines[i];
      // Standalone "by" or "by:" line followed by author name on next line
      if (/^(?:by|BY|Written By|WRITTEN BY):?$/i.test(line) && i + 1 < frontLines.length) {
        const nextLine = frontLines[i + 1].replace(/^#+\s*/, '').trim();
        if (nextLine.length > 2 && nextLine.length < 65 && !nextLine.toLowerCase().startsWith('chapter')) {
          result.author = nextLine;
          if (!result.title && i > 0) {
            result.title = frontLines[0].replace(/^#+\s*/, '').replace(/^\*+\s*/, '').replace(/\*+$/, '').trim();
            if (i > 1 && !result.description) {
              result.description = frontLines[1].replace(/^#+\s*/, '').trim();
            }
          }
          break;
        }
      }

      // Single line "By Author Name"
      const byM = line.match(/^(?:[#\s*]*)(?:by|BY|Written [Bb]y)\s+([A-Za-z\s.'\-]+?)(?:\s*\*+|\s*#+)?$/i);
      if (byM) {
        const cand = byM[1].trim();
        if (cand.length > 2 && cand.length < 65) {
          result.author = cand;
          if (!result.title && i > 0) {
            result.title = frontLines[0].replace(/^#+\s*/, '').replace(/^\*+\s*/, '').replace(/\*+$/, '').trim();
            if (i > 1 && !result.description) {
              result.description = frontLines[1].replace(/^#+\s*/, '').trim();
            }
          }
          break;
        }
      }
    }
  }

  // 4. If title still not found, take the first prominent heading/line
  if (!result.title) {
    for (const line of frontLines) {
      const clean = line.replace(/^#+\s*/, '').replace(/^\*+\s*/, '').replace(/\*+$/, '').trim();
      const low = clean.toLowerCase();
      if (
        low.startsWith('the project gutenberg') ||
        low.startsWith('gutenberg') ||
        low.startsWith('copyright') ||
        low.startsWith('all rights') ||
        low.startsWith('author:') ||
        low.startsWith('title:') ||
        low.startsWith('by ') ||
        clean.length < 3 ||
        clean.length > 100
      ) {
        continue;
      }
      result.title = clean;
      break;
    }
  }

  // 5. Fallback title
  if (!result.title && fallbackTitle) {
    result.title = fallbackTitle;
  }

  // 6. Look for subtitle / description if still empty
  if (!result.description && frontLines.length >= 2) {
    for (const line of frontLines) {
      if (line === result.title || (result.author && line.toLowerCase().includes(result.author.toLowerCase()))) {
        continue;
      }
      const low = line.toLowerCase();
      if (
        (low.includes('story') ||
          low.includes('novel') ||
          low.includes('mystery') ||
          low.includes('detective') ||
          low.includes('tale') ||
          low.includes('chronicle') ||
          low.includes('adventure') ||
          low.includes('memoir')) &&
        line.length > 5 &&
        line.length < 150
      ) {
        result.description = line.trim();
        break;
      }
    }
  }

  // Helper to convert ALL CAPS strings into Title Case
  const fixAllCaps = (str) => {
    if (str && str.length > 3 && str === str.toUpperCase() && /[A-Z]/.test(str)) {
      return str
        .toLowerCase()
        .replace(/(?:^|\s|\/|-)[a-z]/g, (m) => m.toUpperCase());
    }
    return str;
  };

  result.title = fixAllCaps(result.title);
  result.author = fixAllCaps(result.author);

  return result;
}

export function AddBookModal({ isOpen, onClose, onBookAdded, initialFile = null }) {
  const [title, setTitle] = useState('');
  const [author, setAuthor] = useState('');
  const [description, setDescription] = useState('');
  const [sourceType, setSourceType] = useState('upload'); // 'upload' | 'url'
  const [fileFormat, setFileFormat] = useState('txt'); // 'txt' | 'json' | 'unsupported_pdf' | 'unsupported_epub'
  const [sourceUrl, setSourceUrl] = useState('');
  const [file, setFile] = useState(null);
  const [textContent, setTextContent] = useState('');
  const [inputMode, setInputMode] = useState('file'); // 'file' | 'paste'
  const [extractGraph, setExtractGraph] = useState(true);
  const [parsedPreview, setParsedPreview] = useState(null);
  const [autoFillNotice, setAutoFillNotice] = useState(null);
  const [isDragOver, setIsDragOver] = useState(false);

  const [loading, setLoading] = useState(false);
  const [progressMsg, setProgressMsg] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  const modalRef = useRef(null);

  const processFile = (selected) => {
    if (!selected) return;
    setFile(selected);
    const name = selected.name.toLowerCase();
    let fmt = 'txt';
    if (name.endsWith('.json')) fmt = 'json';
    else if (name.endsWith('.pdf')) fmt = 'unsupported_pdf';
    else if (name.endsWith('.epub')) fmt = 'unsupported_epub';
    setFileFormat(fmt);

    // If text or json, read content in memory to infer title & chapter preview
    if (name.endsWith('.txt') || name.endsWith('.json')) {
      const reader = new FileReader();
      reader.onload = (e) => {
        const text = e.target?.result || '';
        const cleanName = selected.name.replace(/\.[^/.]+$/, '').replace(/[-_]+/g, ' ');
        const capFallback = cleanName.replace(/\b\w/g, (c) => c.toUpperCase());

        if (fmt === 'txt') {
          // Parse opening page front matter for title, author, and description
          const meta = parseFirstPageMetadata(text, capFallback);
          if (meta.title) setTitle(meta.title);
          if (meta.author) setAuthor(meta.author);
          if (meta.description) setDescription(meta.description);

          if (meta.title || meta.author) {
            setAutoFillNotice({
              title: meta.title || capFallback,
              author: meta.author,
              source: 'opening page front matter',
            });
          }

          // Detect chapters
          const chapterMatches = text.match(/(?:^|\r?\n)(?:[#\s]*)(?:CHAPTER|Chapter|Book|Part)\s+[0-9IVXLCDMivxlcdm]+/gm);
          const wordCount = text.trim().split(/\s+/).filter(Boolean).length;
          const estChapters = chapterMatches ? chapterMatches.length : Math.max(1, Math.ceil(wordCount / 2500));
          setParsedPreview({
            chapters: estChapters,
            words: wordCount,
            isDetected: !!chapterMatches,
          });
        } else if (fmt === 'json') {
          try {
            const parsed = JSON.parse(text);
            if (parsed.title) setTitle(parsed.title);
            if (parsed.author) setAuthor(parsed.author);
            if (parsed.description) setDescription(parsed.description);
            if (parsed.title || parsed.author) {
              setAutoFillNotice({
                title: parsed.title,
                author: parsed.author,
                source: 'StoryGraph JSON dataset',
              });
            }
            setParsedPreview({
              chapters: (parsed.characters?.length || 0) + (parsed.claims?.length || 0),
              words: 0,
              isJson: true,
            });
          } catch (_) {}
        }
      };
      reader.readAsText(selected);
    }
  };

  const autoFillFromText = (targetText) => {
    const raw = targetText || textContent;
    if (!raw || raw.trim().length < 10) return;
    const meta = parseFirstPageMetadata(raw);
    let changed = false;
    if (meta.title) {
      setTitle(meta.title);
      changed = true;
    }
    if (meta.author) {
      setAuthor(meta.author);
      changed = true;
    }
    if (meta.description && !description.trim()) {
      setDescription(meta.description);
      changed = true;
    }
    if (meta.title || meta.author) {
      setAutoFillNotice({
        title: meta.title || title,
        author: meta.author || author,
        source: 'pasted text front matter',
      });
    }
    return changed;
  };

  const handleTextContentChange = (val) => {
    setTextContent(val);
    if (val.trim().length > 30) {
      const chapterMatches = val.match(/(?:^|\r?\n)(?:[#\s]*)(?:CHAPTER|Chapter|Book|Part)\s+[0-9IVXLCDMivxlcdm]+/gm);
      const wordCount = val.trim().split(/\s+/).filter(Boolean).length;
      const estChapters = chapterMatches ? chapterMatches.length : Math.max(1, Math.ceil(wordCount / 2500));
      setParsedPreview({
        chapters: estChapters,
        words: wordCount,
        isDetected: !!chapterMatches,
      });
    } else {
      setParsedPreview(null);
    }
  };

  useEffect(() => {
    if (initialFile && isOpen) {
      processFile(initialFile);
    }
  }, [initialFile, isOpen]);

  // Close on Escape key
  useEffect(() => {
    function handleKeyDown(e) {
      if (e.key === 'Escape' && isOpen && !loading) {
        onClose();
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, loading, onClose]);

  // Focus trap / auto-focus
  useEffect(() => {
    if (isOpen) {
      setErrorMsg('');
      setProgressMsg('');
      if (!initialFile) {
        setAutoFillNotice(null);
      }
      const input = modalRef.current?.querySelector('input[name="title"]');
      if (input) input.focus();
    } else {
      setAutoFillNotice(null);
    }
  }, [isOpen, initialFile]);

  if (!isOpen) return null;

  const handleFileChange = (e) => {
    const selected = e.target.files?.[0];
    if (selected) {
      processFile(selected);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMsg('');

    if (!title.trim()) {
      setErrorMsg('Book title is required.');
      return;
    }
    if (!author.trim()) {
      setErrorMsg('Author name is required.');
      return;
    }

    if (fileFormat === 'unsupported_pdf' || fileFormat === 'unsupported_epub') {
      const fmtName = fileFormat === 'unsupported_pdf' ? 'PDF' : 'EPUB';
      setErrorMsg(
        `Parser for format '${fmtName}' is not installed in the backend environment. Please select Plain Text (.txt) or StoryGraph JSON (.json).`
      );
      return;
    }

    if (sourceType === 'url') {
      if (!sourceUrl.trim()) {
        setErrorMsg('Please enter a valid source URL.');
        return;
      }
      if (!sourceUrl.startsWith('http://') && !sourceUrl.startsWith('https://')) {
        setErrorMsg('Source URL must begin with http:// or https://');
        return;
      }
    } else {
      if (inputMode === 'file' && !file) {
        setErrorMsg('Please select a file to upload or switch to direct paste.');
        return;
      }
      if (inputMode === 'paste' && !textContent.trim()) {
        setErrorMsg('Pasted manuscript text cannot be empty.');
        return;
      }
    }

    setLoading(true);
    setProgressMsg('Uploading and validating manuscript...');

    try {
      let payload;
      if (sourceType === 'url') {
        setProgressMsg('Fetching remote text and validating network boundaries...');
        payload = {
          title: title.trim(),
          author: author.trim(),
          description: description.trim(),
          source_type: 'url',
          format: fileFormat,
          source_url: sourceUrl.trim(),
          extract_graph: extractGraph,
        };
      } else if (inputMode === 'paste') {
        setProgressMsg('Processing manuscript and segmenting chapters...');
        payload = {
          title: title.trim(),
          author: author.trim(),
          description: description.trim(),
          source_type: 'upload',
          format: fileFormat,
          content: textContent,
          extract_graph: extractGraph,
        };
      } else {
        setProgressMsg('Uploading file and establishing reading positions...');
        const formData = new FormData();
        formData.append('title', title.trim());
        formData.append('author', author.trim());
        formData.append('description', description.trim());
        formData.append('source_type', 'upload');
        formData.append('format', fileFormat);
        formData.append('file', file);
        formData.append('extract_graph', extractGraph ? 'true' : 'false');
        payload = formData;
      }

      const result = await addBook(payload);
      setProgressMsg('Manuscript imported successfully!');
      setTimeout(() => {
        setLoading(false);
        onBookAdded(result);
        onClose();
      }, 500);
    } catch (err) {
      console.error('Failed to import book:', err);
      setErrorMsg(err.message || 'An error occurred during book ingestion.');
      setLoading(false);
      setProgressMsg('');
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(10, 12, 16, 0.82)',
        backdropFilter: 'blur(4px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
        padding: '1rem',
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget && !loading) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
    >
      <div
        ref={modalRef}
        style={{
          width: '100%',
          maxWidth: '640px',
          maxHeight: '90vh',
          backgroundColor: 'var(--bg-secondary)',
          border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-lg)',
          boxShadow: '0 20px 50px rgba(0, 0, 0, 0.65)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        {/* Modal Header */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '1.25rem 1.5rem',
          borderBottom: '1px solid var(--border-subtle)',
          backgroundColor: 'var(--bg-tertiary)',
        }}>
          <div>
            <h2 id="modal-title" style={{
              fontSize: '1.15rem',
              fontFamily: 'var(--font-serif)',
              color: 'var(--text-ivory-primary)',
              letterSpacing: '0.02em',
            }}>
              Add a Book to StoryGraph
            </h2>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-ivory-muted)' }}>
              Configure manuscript metadata and establish chapter boundaries for graph exploration.
            </p>
          </div>
          <button
            onClick={onClose}
            disabled={loading}
            className="btn"
            style={{ padding: '0.35rem', borderRadius: '50%' }}
            aria-label="Close dialog"
          >
            <X size={16} />
          </button>
        </div>

        {/* Modal Body / Form */}
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', overflowY: 'auto', padding: '1.5rem', gap: '1.25rem' }}>
          {/* Error Message Alert */}
          {errorMsg && (
            <div style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: '0.75rem',
              padding: '0.85rem 1rem',
              backgroundColor: 'rgba(239, 68, 68, 0.12)',
              border: '1px solid rgba(239, 68, 68, 0.35)',
              borderRadius: 'var(--radius-md)',
              color: '#fca5a5',
              fontSize: '0.825rem',
              lineHeight: 1.4,
            }}>
              <AlertTriangle size={16} style={{ flexShrink: 0, marginTop: '2px' }} />
              <div>
                <strong style={{ display: 'block', color: '#f87171', marginBottom: '0.2rem' }}>Import Error</strong>
                {errorMsg}
              </div>
            </div>
          )}

          {/* Auto-fill notification banner */}
          {autoFillNotice && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '0.65rem 0.9rem',
                backgroundColor: 'rgba(217, 119, 6, 0.12)',
                border: '1px solid rgba(217, 119, 6, 0.35)',
                borderRadius: 'var(--radius-md)',
                color: 'var(--accent-amber-light)',
                fontSize: '0.785rem',
                lineHeight: 1.4,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                <Sparkles size={16} style={{ color: 'var(--accent-amber)', flexShrink: 0 }} />
                <div>
                  <strong style={{ color: 'var(--accent-amber-light)' }}>Auto-filled from opening page:</strong>{' '}
                  <span style={{ color: 'var(--text-ivory-primary)' }}>
                    &ldquo;{autoFillNotice.title}&rdquo;{autoFillNotice.author ? ` by ${autoFillNotice.author}` : ''}
                  </span>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setAutoFillNotice(null)}
                style={{
                  background: 'none',
                  border: 'none',
                  color: 'var(--text-ivory-muted)',
                  cursor: 'pointer',
                  padding: '2px 4px',
                  display: 'flex',
                  alignItems: 'center',
                }}
                title="Dismiss"
              >
                <X size={14} />
              </button>
            </div>
          )}

          {/* Title & Author */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-ivory-secondary)', marginBottom: '0.4rem' }}>
                Book Title <span style={{ color: 'var(--accent-amber)' }}>*</span>
              </label>
              <input
                type="text"
                name="title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. The Hound of the Baskervilles"
                disabled={loading}
                className="input-text"
                required
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-ivory-secondary)', marginBottom: '0.4rem' }}>
                Author <span style={{ color: 'var(--accent-amber)' }}>*</span>
              </label>
              <input
                type="text"
                value={author}
                onChange={(e) => setAuthor(e.target.value)}
                placeholder="e.g. Arthur Conan Doyle"
                disabled={loading}
                className="input-text"
                required
              />
            </div>
          </div>

          {/* Description */}
          <div>
            <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-ivory-secondary)', marginBottom: '0.4rem' }}>
              Short Synopsis / Description (Optional)
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Brief mystery premise or context for the investigation..."
              disabled={loading}
              className="input-text"
              rows={2}
              style={{ resize: 'vertical' }}
            />
          </div>

          {/* Source Type Selector */}
          <div>
            <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-ivory-secondary)', marginBottom: '0.5rem' }}>
              Manuscript Source Type
            </label>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button
                type="button"
                onClick={() => setSourceType('upload')}
                disabled={loading}
                className="btn"
                style={{
                  flex: 1,
                  backgroundColor: sourceType === 'upload' ? 'var(--bg-surface)' : 'var(--bg-tertiary)',
                  borderColor: sourceType === 'upload' ? 'var(--accent-amber)' : 'var(--border-subtle)',
                  color: sourceType === 'upload' ? 'var(--accent-amber-light)' : 'var(--text-ivory-muted)',
                }}
              >
                <Upload size={14} /> Upload File or Text
              </button>
              <button
                type="button"
                onClick={() => setSourceType('url')}
                disabled={loading}
                className="btn"
                style={{
                  flex: 1,
                  backgroundColor: sourceType === 'url' ? 'var(--bg-surface)' : 'var(--bg-tertiary)',
                  borderColor: sourceType === 'url' ? 'var(--accent-amber)' : 'var(--border-subtle)',
                  color: sourceType === 'url' ? 'var(--accent-amber-light)' : 'var(--text-ivory-muted)',
                }}
              >
                <Link size={14} /> Source URL (Public Domain)
              </button>
            </div>
          </div>

          {/* File Format Selection */}
          <div>
            <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-ivory-secondary)', marginBottom: '0.4rem' }}>
              File Format
            </label>
            <select
              value={fileFormat}
              onChange={(e) => setFileFormat(e.target.value)}
              disabled={loading}
              className="input-text"
              style={{ cursor: 'pointer' }}
            >
              <option value="txt">Plain Text (.txt) — Fully Supported</option>
              <option value="json">StoryGraph Dataset (.json) — Fully Supported</option>
              <option value="unsupported_pdf">PDF Document (.pdf) — Parser Not Installed</option>
              <option value="unsupported_epub">EPUB Ebook (.epub) — Parser Not Installed</option>
            </select>
            {(fileFormat === 'unsupported_pdf' || fileFormat === 'unsupported_epub') && (
              <p style={{ fontSize: '0.725rem', color: '#f87171', marginTop: '0.4rem' }}>
                Note: PDF and EPUB parsing require external packages (pypdf/ebooklib) not currently installed in this environment. Ingestion will return an unsupported format error.
              </p>
            )}
          </div>

          {/* Content Inputs based on Source Type */}
          {sourceType === 'upload' ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.25rem' }}>
                <button
                  type="button"
                  onClick={() => setInputMode('file')}
                  className="btn"
                  style={{
                    fontSize: '0.75rem',
                    padding: '0.25rem 0.5rem',
                    backgroundColor: inputMode === 'file' ? 'var(--bg-surface)' : 'transparent',
                    borderColor: inputMode === 'file' ? 'var(--accent-amber)' : 'transparent',
                    color: inputMode === 'file' ? 'var(--accent-amber-light)' : 'var(--text-ivory-muted)',
                  }}
                >
                  File Upload
                </button>
                <button
                  type="button"
                  onClick={() => setInputMode('paste')}
                  className="btn"
                  style={{
                    fontSize: '0.75rem',
                    padding: '0.25rem 0.5rem',
                    backgroundColor: inputMode === 'paste' ? 'var(--bg-surface)' : 'transparent',
                    borderColor: inputMode === 'paste' ? 'var(--accent-amber)' : 'transparent',
                    color: inputMode === 'paste' ? 'var(--accent-amber-light)' : 'var(--text-ivory-muted)',
                  }}
                >
                  Paste Text Directly
                </button>
              </div>

              {inputMode === 'file' ? (
                <div
                  onDragOver={(e) => {
                    e.preventDefault();
                    setIsDragOver(true);
                  }}
                  onDragLeave={() => setIsDragOver(false)}
                  onDrop={(e) => {
                    e.preventDefault();
                    setIsDragOver(false);
                    const droppedFile = e.dataTransfer.files?.[0];
                    if (droppedFile) processFile(droppedFile);
                  }}
                  style={{
                    border: `2px dashed ${isDragOver ? 'var(--accent-amber)' : 'var(--border-subtle)'}`,
                    borderRadius: 'var(--radius-md)',
                    padding: '1.75rem 1.5rem',
                    textAlign: 'center',
                    backgroundColor: isDragOver ? 'rgba(217, 119, 6, 0.08)' : 'var(--bg-tertiary)',
                    transition: 'all 0.2s ease',
                    cursor: 'pointer',
                  }}
                >
                  <input
                    type="file"
                    id="book-file-input"
                    accept=".txt,.json,.pdf,.epub"
                    onChange={handleFileChange}
                    disabled={loading}
                    style={{ display: 'none' }}
                  />
                  <label htmlFor="book-file-input" style={{ cursor: 'pointer', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.5rem' }}>
                    <FileText size={28} style={{ color: isDragOver ? 'var(--accent-amber-light)' : 'var(--accent-amber)' }} />
                    <span style={{ fontSize: '0.85rem', color: 'var(--text-ivory-primary)', fontWeight: 500 }}>
                      {file ? file.name : 'Drop your story text file (.txt) here or click to browse'}
                    </span>
                    <span style={{ fontSize: '0.72rem', color: 'var(--text-ivory-muted)' }}>
                      {file ? `${(file.size / 1024).toFixed(1)} KB` : 'Supports UTF-8 Plain Text and StoryGraph JSON (max 5 MB)'}
                    </span>
                  </label>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: '0.72rem', color: 'var(--text-ivory-muted)' }}>
                      Paste story text or front matter:
                    </span>
                    <button
                      type="button"
                      onClick={() => autoFillFromText()}
                      disabled={!textContent.trim() || loading}
                      className="btn"
                      style={{
                        padding: '0.2rem 0.6rem',
                        fontSize: '0.725rem',
                        color: 'var(--accent-amber-light)',
                        borderColor: 'var(--accent-amber)',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.35rem',
                        cursor: textContent.trim() ? 'pointer' : 'not-allowed',
                      }}
                      title="Scan opening page of pasted text for title, author, and description"
                    >
                      <Sparkles size={13} style={{ color: 'var(--accent-amber)' }} /> Auto-fill Details from Text
                    </button>
                  </div>
                  <textarea
                    value={textContent}
                    onChange={(e) => handleTextContentChange(e.target.value)}
                    onPaste={(e) => {
                      const pasted = e.clipboardData?.getData('text');
                      if (pasted) {
                        setTimeout(() => autoFillFromText(pasted), 30);
                      }
                    }}
                    placeholder="Paste manuscript text here (Title, Author, and Chapters will be auto-detected from opening page)..."
                    disabled={loading}
                    className="input-text"
                    rows={6}
                    style={{ resize: 'vertical', fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}
                  />
                </div>
              )}

              {/* Real-time Parsed Chapter & Word Count Preview */}
              {parsedPreview && (
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.65rem',
                  padding: '0.65rem 0.85rem',
                  backgroundColor: 'rgba(217, 119, 6, 0.1)',
                  border: '1px solid rgba(217, 119, 6, 0.3)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '0.775rem',
                  color: 'var(--accent-amber-light)',
                  marginTop: '0.35rem',
                }}>
                  <CheckCircle2 size={16} style={{ color: 'var(--accent-amber)', flexShrink: 0 }} />
                  <span>
                    <strong>Manuscript Analyzed:</strong> {parsedPreview.chapters} {parsedPreview.chapters === 1 ? 'Chapter' : 'Chapters'} detected • {parsedPreview.words.toLocaleString()} words. Progressive reading boundaries will be configured.
                  </span>
                </div>
              )}

              {/* Candidate Story Graph Extraction Checkbox */}
              {fileFormat === 'txt' && (
                <label style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: '0.65rem',
                  padding: '0.75rem',
                  backgroundColor: 'var(--bg-tertiary)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: 'var(--radius-sm)',
                  cursor: 'pointer',
                  marginTop: '0.35rem',
                }}>
                  <input
                    type="checkbox"
                    checked={extractGraph}
                    onChange={(e) => setExtractGraph(e.target.checked)}
                    style={{ accentColor: 'var(--accent-amber)', width: '16px', height: '16px', marginTop: '2px', cursor: 'pointer' }}
                  />
                  <div>
                    <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-ivory-primary)', display: 'block' }}>
                      Extract candidate narrative graph
                    </span>
                    <span style={{ fontSize: '0.72rem', color: 'var(--text-ivory-muted)' }}>
                      Discovers candidate characters and locations revealed across chapters, enabling immediate visual graph exploration, dossier notes, and question answering.
                    </span>
                  </div>
                </label>
              )}
            </div>
          ) : (
            <div>
              <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-ivory-secondary)', marginBottom: '0.4rem' }}>
                Public-Domain Source URL
              </label>
              <input
                type="url"
                value={sourceUrl}
                onChange={(e) => setSourceUrl(e.target.value)}
                placeholder="https://www.gutenberg.org/files/.../....txt"
                disabled={loading}
                className="input-text"
              />
              <div style={{
                marginTop: '0.65rem',
                padding: '0.65rem 0.85rem',
                backgroundColor: 'var(--bg-tertiary)',
                borderRadius: 'var(--radius-sm)',
                fontSize: '0.725rem',
                color: 'var(--text-ivory-muted)',
                lineHeight: 1.4,
                display: 'flex',
                gap: '0.5rem',
              }}>
                <Info size={14} style={{ color: 'var(--accent-amber)', flexShrink: 0, marginTop: '2px' }} />
                <span>
                  <strong>Accepted Sources:</strong> Direct links to public-domain plain text archives (e.g. Project Gutenberg plain text files). Web scraping of paywalled, login-gated, or copyright-restricted websites is blocked.
                </span>
              </div>
            </div>
          )}

          {/* Legal / Redistribution Rights Disclaimer */}
          <div style={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: '0.65rem',
            padding: '0.75rem 0.9rem',
            backgroundColor: 'var(--accent-amber-bg)',
            border: '1px solid rgba(217, 119, 6, 0.25)',
            borderRadius: 'var(--radius-md)',
            fontSize: '0.725rem',
            color: 'var(--text-ivory-secondary)',
            lineHeight: 1.4,
          }}>
            <ShieldCheck size={16} style={{ color: 'var(--accent-amber)', flexShrink: 0, marginTop: '2px' }} />
            <span>
              <strong>Local Library Notice:</strong> Uploading or adding a book incorporates it into your local StoryGraph library for graph analysis and reading. It does not automatically publish the text, host it publicly, or grant redistribution rights.
            </span>
          </div>

          {/* Progress Indicator */}
          {loading && (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.65rem',
              padding: '0.75rem 1rem',
              backgroundColor: 'var(--bg-tertiary)',
              borderRadius: 'var(--radius-md)',
              fontSize: '0.8rem',
              color: 'var(--accent-amber-light)',
            }}>
              <Loader2 size={16} className="animate-spin" />
              <span>{progressMsg || 'Processing...'}</span>
            </div>
          )}

          {/* Action Buttons */}
          <div style={{
            display: 'flex',
            justifyContent: 'flex-end',
            gap: '0.75rem',
            paddingTop: '0.5rem',
            borderTop: '1px solid var(--border-subtle)',
          }}>
            <button
              type="button"
              onClick={onClose}
              disabled={loading}
              className="btn"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="btn btn-primary"
            >
              {loading ? (
                <>
                  <Loader2 size={14} className="animate-spin" /> Ingesting...
                </>
              ) : (
                'Add to Library'
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
