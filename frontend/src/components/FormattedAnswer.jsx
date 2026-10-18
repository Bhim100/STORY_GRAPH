import React from 'react';
import { Quote, Sparkles } from 'lucide-react';

/**
 * Parses inline markdown: **bold**, *italic*, and `code`.
 */
function renderInlineText(text) {
  if (!text) return null;
  // Match **bold**, *italic*, or `code`
  const tokens = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g);

  return tokens.map((token, idx) => {
    if (token.startsWith('**') && token.endsWith('**') && token.length >= 4) {
      return (
        <strong key={idx} className="answer-bold">
          {token.slice(2, -2)}
        </strong>
      );
    }
    if (token.startsWith('*') && token.endsWith('*') && token.length >= 2) {
      return (
        <em key={idx} className="answer-italic">
          {token.slice(1, -1)}
        </em>
      );
    }
    if (token.startsWith('`') && token.endsWith('`') && token.length >= 2) {
      return (
        <code key={idx} className="answer-code">
          {token.slice(1, -1)}
        </code>
      );
    }
    return token;
  });
}

/**
 * Normalizes text by fixing encoding glitches and breaking clumped inline bullets into structured lines.
 */
function normalizeNarrativeText(raw) {
  if (!raw) return '';
  let str = raw.replace(/\r\n/g, '\n').replace(/\r/g, '\n');

  // Fix common unicode replacement artifacts
  str = str.replace(/\uFFFD/g, "'");

  // Fix clumped inline bullets (e.g. "...status: * **Trainer:** ... * **Owner:** ...")
  str = str.replace(/(\s+|^)\*\s+(?=\*\*|\*Evidence:|[A-Z][a-zA-Z\s]+:)/g, '\n* ');

  // If a colon is followed by a newline and bullet, make sure there is breathing room
  str = str.replace(/:\s*\n\*\s+/g, ':\n\n* ');

  return str;
}

/**
 * Parses normalized text into block-level elements: headings, lists, evidence callouts, and paragraphs.
 */
function parseBlocks(text) {
  const normalized = normalizeNarrativeText(text);
  const lines = normalized.split('\n');
  const blocks = [];
  let currentList = null;

  for (let i = 0; i < lines.length; i++) {
    const rawLine = lines[i];
    const line = rawLine.trim();

    if (!line) {
      if (currentList) {
        blocks.push({ type: 'list', items: currentList });
        currentList = null;
      }
      continue;
    }

    // Markdown Headings (e.g., ### Investigator Profile)
    const headMatch = line.match(/^(#{1,6})\s*(.*)$/);
    if (headMatch) {
      if (currentList) {
        blocks.push({ type: 'list', items: currentList });
        currentList = null;
      }
      blocks.push({
        type: 'heading',
        level: headMatch[1].length,
        text: headMatch[2].replace(/\*\*/g, '').trim(),
      });
      continue;
    }

    // Markdown Blockquotes (e.g., > "Quote from chapter")
    const quoteMatch = line.match(/^>\s*(.*)$/);
    if (quoteMatch) {
      if (currentList) {
        blocks.push({ type: 'list', items: currentList });
        currentList = null;
      }
      blocks.push({ type: 'evidence', text: quoteMatch[1] });
      continue;
    }

    // Evidence lines starting with *Evidence:* or Evidence:
    const evMatch = line.match(/^(\*\s*)?\*?Evidence:\*?\s*(.*)$/i);
    if (evMatch) {
      if (currentList) {
        blocks.push({ type: 'list', items: currentList });
        currentList = null;
      }
      blocks.push({ type: 'evidence', text: evMatch[2] });
      continue;
    }

    // Bulleted or numbered list items
    const listMatch = line.match(/^([*•-]|\d+\.)\s+(.*)$/);
    if (listMatch) {
      const content = listMatch[2];

      // If bullet item itself is an evidence quote, treat as evidence callout
      const subEvMatch = content.match(/^\*?Evidence:\*?\s*(.*)$/i);
      if (subEvMatch) {
        if (currentList) {
          blocks.push({ type: 'list', items: currentList });
          currentList = null;
        }
        blocks.push({ type: 'evidence', text: subEvMatch[1] });
        continue;
      }

      // Check key-value structured item e.g. **Trainer:** John Straker or **[Trainer]:** John Straker
      const kvMatch = content.match(/^\*\*([^*:]+):\*\*\s*(.*)$/);
      const itemData = kvMatch
        ? { isKv: true, key: kvMatch[1].replace(/^\[|\]$/g, '').trim(), value: kvMatch[2].trim() }
        : { isKv: false, text: content };

      if (!currentList) currentList = [];
      currentList.push(itemData);
      continue;
    }

    // Standard narrative paragraph
    if (currentList) {
      blocks.push({ type: 'list', items: currentList });
      currentList = null;
    }
    blocks.push({ type: 'paragraph', text: line });
  }

  if (currentList) {
    blocks.push({ type: 'list', items: currentList });
  }

  return blocks;
}

export function FormattedAnswer({ text }) {
  if (!text) return null;

  const blocks = parseBlocks(text);

  return (
    <div className="answer-prose">
      {blocks.map((block, idx) => {
        if (block.type === 'heading') {
          const HeadingTag = block.level <= 3 ? 'h3' : 'h4';
          const headingClass = block.level <= 3 ? 'answer-heading-3' : 'answer-heading-4';
          return (
            <HeadingTag key={idx} className={headingClass}>
              {block.level <= 3 && <Sparkles size={13} style={{ color: 'var(--accent-amber)', display: 'inline', marginRight: '0.4rem', verticalAlign: '-1px' }} />}
              {block.text}
            </HeadingTag>
          );
        }

        if (block.type === 'evidence') {
          // Clean quotes/asterisks if nested in evidence block
          let cleanExcerpt = block.text.trim();
          if (cleanExcerpt.startsWith('*') && cleanExcerpt.endsWith('*')) {
            cleanExcerpt = cleanExcerpt.slice(1, -1);
          }

          return (
            <div key={idx} className="dossier-evidence-callout">
              <div className="dossier-evidence-header">
                <Quote size={12} style={{ color: 'var(--accent-amber)' }} />
                <span>Verified Source Evidence</span>
              </div>
              <div className="dossier-evidence-quote">
                {renderInlineText(cleanExcerpt)}
              </div>
            </div>
          );
        }

        if (block.type === 'list') {
          return (
            <div key={idx} className="dossier-report-list">
              {block.items.map((item, itemIdx) => {
                if (item.isKv) {
                  return (
                    <div key={itemIdx} className="dossier-report-row">
                      <div className="dossier-report-key">
                        <span className="dossier-key-dot" />
                        <span>{item.key}:</span>
                      </div>
                      <div className="dossier-report-val">
                        {renderInlineText(item.value)}
                      </div>
                    </div>
                  );
                }
                return (
                  <div key={itemIdx} className="dossier-report-row">
                    <span className="dossier-key-dot" style={{ marginTop: '0.45rem' }} />
                    <div className="dossier-report-val">
                      {renderInlineText(item.text)}
                    </div>
                  </div>
                );
              })}
            </div>
          );
        }

        return (
          <p key={idx} className="answer-paragraph">
            {renderInlineText(block.text)}
          </p>
        );
      })}
    </div>
  );
}
