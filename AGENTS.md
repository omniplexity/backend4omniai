OmniAI Agents

This document defines the agent architecture for OmniAI, our privacy‑first AI chat platform. The goal of this architecture is to decompose the system into specialized “agents” that collaborate to provide a rich conversational experience while respecting the hard constraints (static front‑end, local back‑end with strong security, invite‑only access, and no secrets on the client).

The agents described here are logical units of responsibility. They may be implemented as modules within a single service or as separate services that communicate over internal APIs. The agent model helps us reason about responsibilities, error handling, extensibility and data flow.

Overview

At a high level, OmniAI consists of a static Single Page Application (SPA) front‑end served from GitHub Pages and a local API server (FastAPI) running on the user’s machine. The front‑end never stores secrets or directly contacts provider APIs; instead, it communicates with the back‑end via HTTP(S) and Server‑Sent Events (SSE) to perform chat, search, memory retrieval and other actions. The back‑end exposes a small set of authenticated, rate‑limited endpoints. Providers (LM Studio, Ollama, OpenAI‑compatible models) are abstracted behind a provider registry.

To manage complexity and enforce clean boundaries, we define several agents. Each agent has a well‑defined purpose, inputs, outputs and interactions with other agents. The key agents are:

Agent	Responsibilities	Inputs	Outputs
Chat Agent	Handles user messages, manages conversation state, orchestrates streaming responses and retries. Implements the UI logic for sending messages, attaching files, voice recording and applying settings. Invokes Provider Agent to generate responses, Memory Agent to save/pin messages, and Knowledge Agent to fetch context.	User input (text, voice), conversation settings (model, temperature, top p, etc.), attachments, presets; events from SSE stream.	Updated message list, conversation metadata, streaming status, errors.
Provider Agent	Acts as the adaptor between the chat system and different model providers (LM Studio, Ollama, generic OpenAI endpoints). Exposes list_models(), chat_stream(), chat_once(), healthcheck() and capabilities() interfaces. Uses the provider registry on startup.	Requests from Chat Agent (prompt, model, provider, settings); internal health probes.	Streaming or single responses from providers; model lists; health status.
Authentication Agent	Manages users, sessions and invites. Provides login, logout, session persistence and CSRF protection. Hashes passwords using Argon2id or bcrypt, issues HttpOnly Secure SameSite cookies, enforces rate limits and quotas. Generates and validates invite codes.	Credentials (username/password), invite codes, session cookies, CSRF tokens.	Session tokens, user objects, error codes (invalid credentials, expired invite), audit logs.
Conversation Agent	Persists conversations and messages in the database. Supports creating, listing, updating (rename/delete), and retrieving conversations. Calculates token usage and stores provider metadata for each message. Manages message branching (forking a conversation from a previous message) and pinning to context.	Commands from Chat Agent (create conversation, append message, branch, pin), DB queries.	Conversation objects, message histories, context blocks, artifacts.
Memory Agent	Provides long‑term storage and retrieval of user‑saved content. Users can save messages to memory via the Chat Agent, and the Memory Agent persists these entries and makes them searchable.	Content to save, queries for retrieval.	Memory entries (title, content, timestamp), success/failure messages.
Knowledge Agent	Connects to external or internal knowledge bases (e.g., documentation, manuals, vector stores). Provides search and retrieval operations to enrich chat context. Currently a stub; will be implemented in phase 7 (Admin/Knowledge).	Queries from Chat or Planner Agents.	Snippets/documents, citation metadata.
Voice Agent	Handles transcription of audio and synthesis of text to speech via the voice service. Exposes endpoints for /voice/transcribe and /voice/tts. Enforces file size limits and returns transcripts or audio data to the Chat Agent.	Uploads of audio files or text; optional language selection for transcription.	JSON with transcription (text, language, segments) or binary audio in MP3 format.
Tool Agent	Mediates access to third‑party tools and plugins (code execution, file search, web browsing, etc.). The front‑end exposes toggles for enabling tools (web, files, code, vision). The Tool Agent validates these settings, authorizes tool usage per user policy and proxies requests to the appropriate service.	Tool invocations from Chat Agent, user settings (which tools are enabled).	Tool responses (e.g., code output, search results), error messages.
Planner Agent	Parses high‑level user instructions into sequences of tool calls and provider interactions. Coordinates the Chat, Tool and Knowledge Agents to complete complex tasks. Uses heuristics or large‑language‑model planning to decide when to call memory search, external research or direct chat.	High‑level tasks (e.g., “Research this topic and summarize”), conversation history.	Task plans, intermediate tool outputs, final synthesized responses.
Admin Agent	Provides administrative functionality: managing invites, users, quotas and audit logs. Only accessible to admin users. Persists audit entries on actions (login, invite creation, user deletion). Exposes metrics and status information via an /ops endpoint (e.g., provider health and rate limits).	Admin commands (create invite, disable user), system events.	User lists, invite codes, audit logs, health metrics.
Detailed Agent Descriptions
Chat Agent

The Chat Agent embodies the conversational UI logic. It maintains local state for the input box, selected provider and model, temperature, top p, maximum tokens, system prompt, reasoning mode (standard/extended) and tool settings. It also manages attachments, voice recording state, and preset management (saving and loading sets of settings). When a user sends a message, the Chat Agent:

Validates that a provider and model are selected and that the input is not empty.

Creates or selects the current conversation via the Conversation Agent; if none exists, it calls createNewConversation() and navigates to the new thread.

Uploads attachments (if any) to the Media/Tool Agent and constructs a settings payload capturing temperature, top p, max tokens, system prompt, reasoning mode and tool toggles.

Invokes the Provider Agent for either streaming or one‑shot chat. For streaming, it uses SSE via streamChatLegacy() or streamChat(), updating the message content on each delta and handling final messages, errors and cancellations. For non‑streaming, it calls createMessageV1() and appends the returned message.

Optionally compares multiple models and synthesizes a consensus answer.

Saves conversation settings or presets when requested and applies presets to update the state.

Provider Agent

Providers are registered on application startup. During the FastAPI application lifespan, the system creates a ProviderRegistry if none exists and stores it in app.state. Each provider must implement:

list_models(): returns available model identifiers and capabilities (e.g., maximum context length, vision or tools support).

chat_stream(request): yields chunks of assistant output using SSE. It accepts settings (temperature, top p, max tokens, system prompt), the current prompt and conversation state. Errors are normalized into stable error codes (e.g., rate_limit_exceeded, model_not_found).

chat_once(request): returns a single response when streaming is disabled or not supported.

healthcheck(): returns a boolean or status dict to indicate provider health. The /providers/health endpoint exposes this information to authenticated users.

capabilities(): describes provider features such as vision or JSON mode.

Providers run locally (LM Studio or Ollama) or remotely (generic OpenAI‑compatible endpoints). The Provider Agent ensures that all API keys and secrets remain on the back‑end and never expose them to the front‑end.

Authentication Agent

Authentication is invite‑only. New users must present a valid invite code to register. The system stores users in the users table and invite codes in the invites table. Passwords are hashed using Argon2id (preferred) or bcrypt. The Authentication Agent issues session cookies (HttpOnly, Secure, SameSite) and ensures that CSRF tokens are validated on state‑changing requests. Sessions are stored in the sessions table with expiration timestamps.

The Authentication Agent also enforces rate limits per IP and per user. These limits are configurable via settings and applied by middleware before requests reach the agents. Additional quotas (messages/day or tokens/day) can be implemented by counting usage in the messages table and denying requests when the quota is exceeded.

Conversation Agent

Conversations and messages are persisted in the database (SQLite by default, upgradable to Postgres). The Conversation Agent exposes endpoints to:

Create a new conversation. Called automatically when a user sends a message without an existing conversation ID.

List conversations for the current user, with pagination and search. The front‑end displays them in a sidebar with rename/delete controls.

Append a message. Called by the Chat Agent after sending or receiving messages. Includes provider metadata and token usage.

Rename/Delete conversations. Protected by CSRF and permissions. Renaming updates the title; deleting marks the conversation as deleted or removes it.

Branch a conversation from a previous message. This duplicates the conversation up to the selected message and opens a new thread.

Pin a message to context. Adds a block to the context_blocks table for retrieval in future calls.

Memory Agent

Users may choose to save notable messages to memory. The Memory Agent creates an entry (title and content) in a memory table via the createMemoryEntry() service. In the future, the Memory Agent will index these entries for semantic search (e.g., via a vector store). The front‑end may offer a “Memory” tab to browse and search saved notes.

Knowledge Agent

The Knowledge Agent will integrate external knowledge sources (documentation, websites, internal databases) into chat. It offers two core operations:

search(query): returns a ranked list of documents or snippets matching the query.

retrieve(id or query): fetches the full content and metadata for a given document.

By separating knowledge access into its own agent, we can control which sources are queried and enforce proper authentication. For example, internal company documents could be exposed through a secure API and only to authorized users.

Voice Agent

Voice capabilities are provided by the Voice Agent. The back‑end exposes two endpoints:

/voice/transcribe: accepts an uploaded audio file (UploadFile) and optional language hint and returns JSON containing the transcribed text, detected language and segments. It enforces a maximum request size and catches runtime errors (e.g., missing model, unsupported file type), returning appropriate HTTP status codes.

/voice/tts: accepts a JSON body with text, optional voice_id, and optional speed, pitch and volume, and returns an MP3 audio stream. Errors are logged and returned with 5xx status codes.

These endpoints rely on a voice service provided via settings (get_voice_service(settings)). The service must run locally and keep any API keys on the back‑end.

Tool Agent

The Tool Agent is responsible for accessing additional capabilities such as web browsing, file search, code execution or vision. Each tool is a pluggable module with its own interface. Users can enable or disable tools through chat settings; for example, the UI exposes toggles for web, files, code and vision. The Tool Agent ensures that:

The requested tool is enabled for the current user and conversation.

The tool invocation complies with rate limits and policies (e.g., max recursion depth for web browsing). The settings include a webDepth value that limits how many pages the browsing tool may fetch.

Tool results are normalized and returned to the Planner or Chat Agent. Errors are caught and surfaced with stable error codes (e.g., tool_not_available, tool_rate_limited).

Planner Agent

The Planner Agent interprets high‑level user intents into sequences of agent calls. For instance, a user might ask “Summarize the latest research on quantum computing.” The Planner will:

Invoke the Knowledge Agent’s search to get relevant documents.

Use the Tool Agent’s web browsing tool to fetch and possibly summarize those documents.

Call the Provider Agent with a prompt that synthesizes the retrieved information into a concise summary.

The Planner may rely on a large‑language model running via the Provider Agent to generate the plan itself. It maintains context of the current conversation and any intermediate results. Future enhancements could include a planning language, caching of known plans and dynamic constraint handling.

Admin Agent

Administrative tasks are centralized in the Admin Agent. Only users with an admin role may access these endpoints. Responsibilities include:

Managing invites: generating invite codes with expiration, listing active invites, invalidating codes.

Managing users: listing users, updating roles, disabling accounts, exporting user data, deleting users (subject to data controls).

Managing quotas: setting per‑user message/token quotas and resetting usage counters.

Viewing audit logs: retrieving entries from the audit_log table filtered by actor, action, target, or date range. Logs are structured JSON and never exposed to non‑admin users.

Exposing operational metrics: via an /ops/limits endpoint the agent returns rate‑limit parameters (rate_limit_rpm, max_request_bytes, voice_max_request_bytes). Additional endpoints provide provider health and audit status.

Agent Interactions and Data Flow

The following sequence describes a typical user journey and the agents involved:

Invite & Registration: A prospective user receives an invite code from the Admin Agent. They register via the Authentication Agent, which hashes their password and stores the user record.

Login: The user logs in, obtaining a session cookie. The Authentication Agent sets HttpOnly Secure SameSite cookies and CSRF tokens.

Chat: The user opens the chat UI. The Chat Agent lists conversations via the Conversation Agent and displays them. When the user types a message and clicks send:

The Chat Agent validates input, ensures a conversation exists and uploads attachments via the Media component of the Tool Agent (if any).

It constructs settings (model, temperature, top p, tools) and calls the Provider Agent via chat_stream() or chat_once().

The Provider Agent forwards the request to the selected provider; responses stream back via SSE. The Chat Agent updates the UI incrementally and handles stops/retries.

The Conversation Agent appends the messages and provider metadata to the database.

Memory & Context: The user can save messages to memory via the Memory Agent or pin messages to context via the Conversation Agent. These entries are stored for future retrieval.

Voice & Tools: At any point, the user may start voice recording; the Chat Agent streams audio to the Voice Agent, which returns the transcript. They may also invoke tools (e.g., code execution); the Tool Agent verifies permissions and returns results. The Planner Agent may orchestrate multiple tools to satisfy complex requests.

Administration: Admin users can create invites, view audit logs, check provider health and adjust quotas via the Admin Agent.

Extensibility and Future Work

OmniAI is designed for extensibility. To add a new agent or tool:

Define the agent’s responsibilities, inputs and outputs in AGENTS.md.

Implement the agent as a module under backend/services/ or as a separate service. Ensure it has clear interfaces and integrates with the Provider or Tool Agents as needed.

Expose endpoints via FastAPI routers under the appropriate version (/api/v1/ or /api/). Protect them with authentication and rate limiting.

Update the front‑end to call the new endpoints and provide UI controls if necessary.

Add entries to the OpenAPI spec under contracts/ and regenerate typed clients for the front‑end.

Future agents that may be valuable include:

Scheduler Agent: manages background tasks (e.g., periodic health checks, summary digests, notifications).

Analytics Agent: collects and aggregates anonymized usage statistics, token consumption and model performance metrics. Reports to admins without revealing sensitive content.

Review Agent: automatically flags or filters content that violates usage policies or terms of service. Could integrate with moderation APIs.

Observability and Error Handling

Each agent logs structured events with contextual metadata (request ID, user ID, conversation ID). Errors are never exposed to the client with stack traces; instead, they are normalized into error codes and user‑friendly messages. The Admin Agent can retrieve aggregated metrics and logs for debugging purposes.

Rate limiting and quotas are enforced uniformly via middleware (per‑IP and per‑user). The Provider Agent handles provider‑specific errors (timeouts, 429 responses) and translates them into standard error responses.

Conclusion

The agent architecture provides a modular framework for OmniAI that meets our strict security and deployment constraints while enabling powerful features. By clearly defining responsibilities and interfaces for each agent, we can develop, test and deploy features incrementally, plug in new capabilities (providers, tools, knowledge sources) and maintain a robust, invite‑only AI chat system.