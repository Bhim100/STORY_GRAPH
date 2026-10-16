# StoryGraph Graph Schema

## Node Labels
- **`:Character`**: Individuals in the story (suspects, victims, witnesses).
  - Properties: `id` (string), `name` (string), `role` (string), `description` (string), `alibi` (string)
- **`:Clue`**: Physical evidence or forensic leads.
  - Properties: `id` (string), `name` (string), `description` (string), `criticality` (string: high/medium/low)
- **`:Location`**: Rooms, outdoor spots, or scenes of interest.
  - Properties: `id` (string), `name` (string), `accessibility` (string)
- **`:Secret`**: Hidden motives, relationships, or past incidents.
  - Properties: `id` (string), `name` (string), `description` (string)
- **`:Event`**: Timeline events and actions.
  - Properties: `id` (string), `timestamp` (string), `description` (string)

## Edge Types
- `[:KNOWS]`: Character-to-character familiarity.
- `[:LOCATED_AT]`: Character or Clue at Location.
- `[:SUSPECTS]`: Character suspecting another character.
- `[:OWNS]`: Character owning Clue/Object.
- `[:PARTICIPATED_IN]`: Character involved in Event.
- `[:REVEALS]`: Clue or Event that unveils a Secret.
