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

export async function fetchStory() {
  const res = await fetch(`${BASE_URL}/api/story`);
  if (!res.ok) throw new Error(`Failed to fetch story info (${res.status})`);
  return res.json();
}

export async function fetchGraph(chapter = 1) {
  const res = await fetch(`${BASE_URL}/api/graph?chapter=${encodeURIComponent(chapter)}`);
  if (!res.ok) throw new Error(`Failed to fetch graph data (${res.status})`);
  return res.json();
}

export async function fetchNodeDetails(nodeId, chapter = 1) {
  const res = await fetch(`${BASE_URL}/api/nodes/${encodeURIComponent(nodeId)}?chapter=${encodeURIComponent(chapter)}`);
  if (!res.ok) {
    if (res.status === 404) return null;
    throw new Error(`Failed to fetch node details (${res.status})`);
  }
  return res.json();
}

export async function askQuestion(question, chapter = 1) {
  const res = await fetch(`${BASE_URL}/api/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, chapter }),
  });
  if (!res.ok) throw new Error(`Question request failed with status ${res.status}`);
  return res.json();
}
