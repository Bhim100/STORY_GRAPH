# StoryGraph 📖🔎

StoryGraph helps readers explore the people, places, events, and evidence inside a book.

It turns a story into an interactive graph. You can follow connections between characters, inspect the evidence behind a relationship, and explore the story one chapter at a time.

## Why StoryGraph?

A normal search can find a name in a book, but it may not explain how that person connects to an event or another character. It can also surface information from later chapters.

StoryGraph uses FalkorDB to store story details as connected data. A chapter filter helps show information revealed up to a reader’s current point, while the evidence panel lets readers inspect the passages that support a connection.

## What you can do

- **Explore a story graph:** View characters, events, locations, and their connections.
- **Follow a connection:** Ask how two story elements are related and inspect the path through the graph.
- **Ask about an entity:** Open a character’s dossier or ask a question about them.
- **Review supporting evidence:** See the story excerpt and chapter associated with a claim.
- **Control spoilers:** Set a chapter boundary so later revelations are hidden from the graph.
- **Add a book:** Import a text manuscript or a prepared graph file. New-book extraction may depend on an LLM API key and can be incomplete.

StoryGraph is a work in progress. Extraction quality can vary by book, and a graph should be checked against its source text.

## How the graph is organized

StoryGraph keeps story facts in a few useful groups:

- **Characters** are people or other agents in the narrative.
- **Locations** are places where story events happen.
- **Events** are important occurrences in the plot.
- **Claims** describe relationships or statements about the story.
- **Evidence** contains passages that support claims.

This separation helps distinguish what the story says from what a character suspects or believes.

## How StoryGraph uses FalkorDB

FalkorDB stores each story as a graph. This lets StoryGraph ask questions such as:

- Who is connected to this character?
- What path links these two people?
- What evidence supports this relationship?
- What was known by the end of a chosen chapter?

Cypher queries retrieve the relevant nodes, relationships, and evidence. The answer panel can then present the results in a way that is easier to follow.

For examples, see [docs/cypher_queries.md](docs/cypher_queries.md).

## Getting started

### Requirements

- Python 3.11 or newer
- Node.js and npm
- Docker Desktop with Docker Compose
- An LLM API key for automated extraction of new books (optional; check the current provider configuration)

### 1. Get the project and configure it

```bash
git clone https://github.com/Bhim100/STORY_GRAPH.git
cd STORY_GRAPH
cp .env.example .env
```

Add your FalkorDB settings and, if you plan to use automated extraction, your configured LLM API key to `.env`.

For example:

```env
FALKORDB_HOST=localhost
FALKORDB_PORT=6379
FALKORDB_PASSWORD=
FALKORDB_USERNAME=

GEMINI_API_KEY=your_api_key_here
```

Use the variable names in the project’s `.env.example` if they differ from this example. Keep `.env` private and never commit your API key.

### 2. Start FalkorDB

```bash
docker compose up -d
```

### 3. Install and run the backend

```bash
python -m venv .venv
```

On Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

On macOS or Linux:

```bash
source .venv/bin/activate
```

Then install the backend requirements and start the API:

```bash
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload --port 8000
```

### 4. Install and run the frontend

Open another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open the local address shown by Vite, usually `http://localhost:5173`.

## Using StoryGraph

1. Choose a story from the library or add a supported file.
2. Select a chapter boundary to control what information appears.
3. Explore the graph or open an entity dossier.
4. Ask a question in the investigation panel.
5. Follow the answer’s graph path and inspect its supporting evidence.

The exact extraction results depend on the story data available. If a relationship or event is missing, StoryGraph may not be able to answer the question reliably.

## Project structure

```text
STORY_GRAPH/
├── backend/
│   ├── app/
│   │   ├── graph/       # FalkorDB connection, graph exploration, and seeding
│   │   ├── llm/         # Question routing, answers, and story extraction
│   │   └── importer.py  # Book import and chapter processing
│   └── tests/
├── frontend/
│   └── src/             # Graph view, dossiers, and question panel
└── docs/
    ├── schema.md
    └── cypher_queries.md
```

## Current limitations

- Automated extraction can miss details or interpret an ambiguous passage incorrectly.
- Some questions need relationships or evidence that may not yet exist in the imported graph.
- Spoiler filtering depends on chapter information being assigned correctly.
- If automated extraction is unavailable, the fallback may produce a simpler graph with fewer relationships.

StoryGraph aims to make story connections easier to explore while keeping the evidence visible, so readers can judge the results for themselves.
