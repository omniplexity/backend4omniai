🎯 Feature Scope for Version 1
Area	Goals
Provider Support	Focus on LM Studio via the pluggable provider interface; ensure all existing AI capabilities (chat, tools, vision, voice, etc.) work through this provider. Future providers (Ollama, OpenAI‑compatible endpoints) remain pluggable via the same interface.
Full Feature Set	Implement all feature‑flagged modules listed in FRONTEND_FEATURE_FLAGS.md—assistant memory, knowledge RAG/search with citations, model router, command palette, workflow templates, research mode, and the full chat workspace (branches, canvas, artifacts, run inspector, compare).
Persistence	Add long‑term conversation memory and knowledge base. Use a scalable DB layer (SQLite by default, easily swapped for Postgres) with new tables for memory items and uploaded knowledge documents. Integrate a vector‑store (e.g., pgvector or an embedded file‑based store) for semantic search and RAG.
Workflows & Projects	Extend the “projects” concept to support preset workflows for common niches and allow custom user‑defined projects with their own context and memory (similar to ChatGPT “custom instructions”). Tie these into the command palette and plugin system.
UI/UX	Start from the existing Chat UI (threads sidebar, search/rename/delete, streaming transcript with model controls, cancel/retry, SSE reconnect, etc.), and gradually enable new panels (memory, knowledge, workflows, research) behind flags. Keep the overall design ChatGPT‑like for now and schedule a visual redesign closer to release.
Security & Auth	Implement invite‑only onboarding, session cookies with CSRF protection, Argon2id password hashing, strict CORS (only https://omniplexity.github.io and optional custom domain), rate limiting (per‑IP and per‑user), request size limits, and audit logs. Use the existing admin bootstrap mechanism and add role‑based permissions (admin vs. user).
Testing	Develop comprehensive automated tests: Playwright end‑to‑end tests for UI flows (login, chat streaming, memory/knowledge workflows, admin actions) and Pytest/FastAPI tests for backend endpoints. Ensure tests can be run automatically in CI and produce clear pass/fail reports.
🔧 Architectural Enhancements

Backend upgrades

Extend the db module with tables for persistent memory and knowledge documents.

Build a vector‑store wrapper (e.g., using pgvector or faiss) for semantic search and RAG.

Implement workflow execution endpoints (plan→execute→synthesize) leveraging the provider’s tools and the new memory/knowledge systems.

Flesh out the “projects” API to create, list and manage project contexts (with their own memory and knowledge).

Harden security: enforce invite codes, Argon2id password hashing, CSRF tokens, CORS allowlist, and per‑user rate limits.

Provider registry & LM Studio integration

Finalize provider interface: list_models(), chat_stream(), chat_once(), healthcheck(), capabilities().

Implement LM Studio provider with support for streaming SSE, tool invocation, vision/voice where available, and proper error normalization.

Add a model router (client‑side and server‑side) that selects provider/model based on requested capabilities (e.g., vision vs. text only).

Frontend expansion

Enable feature flags and ensure runtime‑config.json is read at startup and merged with backend metadata.

Add pages/panels for memory and knowledge (upload/search) and tie them into chat context.

Build workflow templates UI with preset tasks (e.g., research summarization, blog generation) and a “research mode” to guide plan→execute→synthesize flows.

Implement the full chat workspace with tabs (branches, canvas, artifacts, run inspector, compare) as described in the feature flags list.

Use the existing plugin registry to register new routes and commands.

Keep the visual style simple for now; schedule a modernized UI pass after functionality is complete.

Deployment & Ops

Maintain the static SPA on GitHub Pages; ensure public/runtime-config.json has placeholders for backend URL and feature flags.

Continue using Docker Compose for local dev; optionally provide Kubernetes manifests for scaling (e.g., Postgres/Redis on K8s). Expose the backend via Cloudflare Tunnel or ngrok with origin lock.

Add runbooks and scripts in deploy/ for starting the tunnel, seeding the database (admin bootstrap), and running migrations.

Documentation & QA

Update docs/ with architecture diagrams, threat model, feature list, and runbook instructions.

Expand the QA checklist to include new features and ensure that npm run test:e2e covers memory, knowledge, workflows, and admin flows.

Provide .env.example files for backend and runtime-config.json examples for frontend.