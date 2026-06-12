# API Documentation

## Orchestrator Service

Base URL: `http://localhost:38081`

### Game Management

#### Start Game
```http
POST /game/start
```

**Response**: `201 Created`
```json
{
  "status": "started",
  "round": 1,
  "phase": "DAY"
}
```

#### Get Game State
```http
GET /game/state
```

**Response**: `200 OK`
```json
{
  "round": 2,
  "phase": "NIGHT",
  "alive_agents": ["agent-1", "agent-2", "agent-3"],
  "eliminated": ["agent-4"]
}
```

### Agent Management

#### List All Agents
```http
GET /game/agents
```

**Response**: `200 OK`
```json
{
  "agent-1": {
    "agent_id": "agent-1",
    "role": "CITIZEN",
    "persona_id": "persona-1",
    "persona_name": "Добродушная",
    "status": "ALIVE"
  },
  "agent-2": {
    "agent_id": "agent-2",
    "role": "MAFIA",
    "persona_id": "persona-2",
    "persona_name": "Истеричка",
    "status": "ALIVE"
  }
}
```

#### Get Agent Info
```http
GET /game/agents/{agent_id}
```

**Response**: `200 OK`
```json
{
  "agent_id": "agent-1",
  "role": "CITIZEN",
  "persona_id": "persona-1",
  "persona_name": "Добродушная",
  "status": "ALIVE"
}
```

#### Ask Agent Question
```http
POST /game/agents/{agent_id}/question
Content-Type: application/json

{
  "question": "Кто по-твоему мафия?"
}
```

**Response**: `200 OK`
```json
{
  "answer": "Я думаю, что агент-3 ведёт себя подозрительно..."
}
```

**Timeout**: 60 seconds  
**Errors**:
- `404` — Agent not found
- `408` — Timeout (agent didn't respond)
- `500` — Internal error

### Host Decisions

#### Submit Host Decision
```http
POST /game/host/decision
Content-Type: application/json

{
  "action": "APPROVE"
}
```

**Actions**:
- `"APPROVE"` — Accept vote result
- `"REJECT"` — Reject vote, retry voting
- `"OVERRIDE"` — Override vote with specific agent elimination

**Response**: `204 No Content`

**Override Example**:
```json
{
  "action": "OVERRIDE",
  "override_agent_id": "agent-5"
}
```

### Server-Sent Events

#### Subscribe to Messages
```http
GET /game/messages/subscribe
Accept: text/event-stream
```

**Stream Format**:
```
data: {"phase": "DAY", "round": 1, "sender_id": "agent-1", "content": "Добрый день!", "timestamp": "2026-06-07T10:30:00Z"}

data: {"phase": "NIGHT", "round": 1, "sender_id": "agent-2", "content": "Я за агента-3", "timestamp": "2026-06-07T10:31:00Z"}
```

---

## Unified Agent Service

Base URL: `http://localhost:38100`

### Agent Lifecycle

#### Initialize Agent
```http
POST /agents/{agent_id}/init
Content-Type: application/json

{
  "role": "CITIZEN",
  "persona_id": "persona-1"
}
```

**Response**: `201 Created`
```json
{
  "agent_id": "agent-1",
  "role": "CITIZEN",
  "persona_id": "persona-1",
  "status": "ALIVE"
}
```

#### Get Agent State
```http
GET /agents/{agent_id}/state
```

**Response**: `200 OK`
```json
{
  "agent_id": "agent-1",
  "role": "CITIZEN",
  "persona_id": "persona-1",
  "status": "ALIVE",
  "message_history": [
    {"role": "assistant", "content": "Добрый день!"}
  ]
}
```

#### Execute Agent Action
```http
POST /agents/{agent_id}/act
Content-Type: application/json

{
  "action": "generate_message",
  "params": {
    "phase": "DAY",
    "game_round": 1
  }
}
```

**Actions**:
- `"generate_message"` — Generate day/night speech
- `"vote"` — Vote for elimination
- `"answer_question"` — Answer host question
- `"add_message"` — Add message to history

**Response**: `200 OK`
```json
{
  "message": "Я думаю, мы должны обсудить..."
}
```

**Vote Example**:
```http
POST /agents/agent-1/act
Content-Type: application/json

{
  "action": "vote",
  "params": {
    "candidates": ["agent-2", "agent-3", "agent-4"],
    "is_night": false,
    "game_round": 2
  }
}
```

**Response**:
```json
{
  "vote": "agent-3"
}
```

#### Eliminate Agent
```http
DELETE /agents/{agent_id}
```

**Response**: `204 No Content`

#### Health Check
```http
GET /health
```

**Response**: `200 OK`
```json
{
  "status": "ok"
}
```

---

## LLM Service

Base URL: `http://localhost:38080`

### LLM Generation

#### Generate Response
```http
POST /generate
Content-Type: application/json

{
  "model": "llama3.1:8b",
  "prompt": "Вы добродушный житель деревни. Опишите своё мнение о текущей ситуации.",
  "max_tokens": 150
}
```

**Response**: `200 OK`
```json
{
  "response": "Я считаю, что мы должны действовать осторожно...",
  "tokens_used": 87,
  "model": "llama3.1:8b"
}
```

#### Health Check
```http
GET /health
```

**Response**: `200 OK`
```json
{
  "status": "ok",
  "pool_size": 4,
  "model": "llama3.1:8b"
}
```

---

## Error Responses

All services follow consistent error format:

### 400 Bad Request
```json
{
  "detail": "Invalid action: unknown_action"
}
```

### 404 Not Found
```json
{
  "detail": "Agent agent-99 not found"
}
```

### 408 Request Timeout
```json
{
  "detail": "Agent did not respond within 60 seconds"
}
```

### 500 Internal Server Error
```json
{
  "detail": "LLM service unavailable"
}
```

---

## Authentication

Currently, **no authentication** is implemented. All endpoints are open.

**Future**: Plan to add JWT-based authentication for production deployment.

---

## Rate Limits

Currently, **no rate limits** are enforced.

**Future**: Consider adding rate limits for:
- Agent questions: 10 requests/minute per agent
- LLM generation: 100 requests/minute per service
- Game start: 1 request/minute (prevent spam)

---

## WebSocket Support (Planned)

Future enhancement: Replace SSE with WebSocket for bi-directional communication.

```javascript
const ws = new WebSocket('ws://localhost:38081/game/ws');

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  console.log('New message:', message);
};
```

---

## Testing APIs

### Using curl

```bash
# Start game
curl -X POST http://localhost:38081/game/start

# Get game state
curl http://localhost:38081/game/state

# Ask agent question
curl -X POST http://localhost:38081/game/agents/agent-1/question \
  -H "Content-Type: application/json" \
  -d '{"question": "Кто мафия?"}'
```

### Using Python httpx

```python
import httpx

async with httpx.AsyncClient() as client:
    # Start game
    response = await client.post('http://localhost:38081/game/start')
    print(response.json())
    
    # Get agents
    response = await client.get('http://localhost:38081/game/agents')
    agents = response.json()
    print(f"Total agents: {len(agents)}")
```

---

## API Versioning

Current version: **v1** (implicit)

All endpoints are unversioned. Future breaking changes will use explicit versioning:
- `/v2/game/start`
- `/v2/agents/{id}/init`
