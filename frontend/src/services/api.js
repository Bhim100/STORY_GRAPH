/**
 * StoryGraph API Service Layer
 * Connects React frontend to FastAPI backend endpoints.
 */

const BASE_URL = '';

export async function fetchHealth() {
  const res = await fetch(`${BASE_URL}/api/health`);
  if (!res.ok) throw new Error(`Health check failed with status ${res.status}`);
  return res.json();
}

export async function fetchBooks() {
  const res = await fetch(`${BASE_URL}/api/books`);
  if (!res.ok) throw new Error(`Failed to fetch library books (${res.status})`);
  return res.json();
}

export async function fetchBook(bookId) {
  const res = await fetch(`${BASE_URL}/api/books/${encodeURIComponent(bookId)}`);
  if (!res.ok) throw new Error(`Failed to fetch book metadata (${res.status})`);
  return res.json();
}

export async function fetchChapterContent(bookId, chapterNumber) {
  const res = await fetch(
    `${BASE_URL}/api/books/${encodeURIComponent(bookId)}/chapters/${encodeURIComponent(chapterNumber)}`
  );
  if (!res.ok) throw new Error(`Failed to fetch chapter content (${res.status})`);
  return res.json();
}

export async function extractStoryGraph(bookId) {
  const res = await fetch(`${BASE_URL}/api/books/${encodeURIComponent(bookId)}/extract-graph`, {
    method: 'POST',
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || `Graph extraction failed (${res.status})`);
  }
  return data;
}

export async function deleteBook(bookId) {
  const res = await fetch(`${BASE_URL}/api/books/${encodeURIComponent(bookId)}`, {
    method: 'DELETE',
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || `Failed to remove story (${res.status})`);
  }
  return data;
}

export async function addBook(bookData) {
  let options = {};
  if (bookData instanceof FormData) {
    options = {
      method: 'POST',
      body: bookData,
    };
  } else {
    options = {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(bookData),
    };
  }

  const res = await fetch(`${BASE_URL}/api/books`, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || `Book upload failed with status ${res.status}`);
  }
  return data;
}

export async function fetchStory(bookId = null) {
  const url = bookId
    ? `${BASE_URL}/api/story?book_id=${encodeURIComponent(bookId)}`
    : `${BASE_URL}/api/story`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to fetch story info (${res.status})`);
  return res.json();
}

export async function fetchGraph(chapter = 1, bookId = null) {
  let url = `${BASE_URL}/api/graph?chapter=${encodeURIComponent(chapter)}`;
  if (bookId) {
    url += `&book_id=${encodeURIComponent(bookId)}`;
  }
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to fetch graph data (${res.status})`);
  return res.json();
}

export async function fetchNodeDetails(nodeId, chapter = 1, bookId = null) {
  let url = `${BASE_URL}/api/nodes/${encodeURIComponent(nodeId)}?chapter=${encodeURIComponent(chapter)}`;
  if (bookId) {
    url += `&book_id=${encodeURIComponent(bookId)}`;
  }
  const res = await fetch(url);
  if (!res.ok) {
    if (res.status === 404) return null;
    throw new Error(`Failed to fetch node details (${res.status})`);
  }
  return res.json();
}

export async function askQuestion(question, chapter = 1, bookId = null) {
  const payload = { question, chapter };
  if (bookId) {
    payload.book_id = bookId;
  }
  const res = await fetch(`${BASE_URL}/api/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Question request failed with status ${res.status}`);
  return res.json();
}
