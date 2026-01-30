import { apiBaseUrl } from "./config.js";
import { getCsrfToken } from "./auth.js";
import {
  isStreaming,
  setStreaming,
  setStreamStatus,
  setActiveStreamMeta,
  updateActiveStreamMeta,
  clearActiveStreamMeta,
  markStreamInterrupted,
} from "./state.js";

const PUBLIC_EVENTS = ["meta", "delta", "final", "error", "ping"];

function parseChunk(raw) {
  const lines = raw.split("\n");
  const event = lines.find((row) => row.startsWith("event:"))?.split("event:")[1].trim();
  const dataLines = lines.filter((row) => row.startsWith("data:")).map((row) => row.split("data:")[1]);
  const payload = dataLines.length ? JSON.parse(dataLines.join("\n")) : {};
  return { event, data: payload };
}

async function fetchWithKeepAlive({ path, body, signal }) {
  const token = await getCsrfToken();
  return fetch(`${apiBaseUrl()}${path}`, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": token,
    },
    body: JSON.stringify(body),
    signal,
  });
}

async function createStream({ path, body, onEvent }) {
  if (isStreaming() && path === "/chat/stream") {
    throw new Error("Another stream is already active");
  }
  const controller = new AbortController();
  let buffer = "";
  let reader;
  let reconnecting = false;
  let stalledTimer;
  let partialLength = 0;

  const resetStallTimer = () => {
    clearTimeout(stalledTimer);
    if (reconnecting) {
      reconnecting = false;
      setStreamStatus(body.conversation_id, "streaming");
    }
    stalledTimer = setTimeout(() => {
      reconnecting = true;
      setStreamStatus(body.conversation_id, "reconnecting");
      onEvent?.reconnecting?.();
    }, 15000);
  };

  async function start() {
    const response = await fetchWithKeepAlive({ path, body, signal: controller.signal });
    if (!response.ok) {
      throw new Error("Unable to open SSE stream");
    }
    if (!response.body) {
      throw new Error("Stream body unavailable");
    }
    setStreaming(true);
    reader = response.body.getReader();
    const decoder = new TextDecoder();
    setStreamStatus(body.conversation_id, "streaming");
    resetStallTimer();
    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) {
          break;
        }
        resetStallTimer();
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() || "";
        for (const chunk of chunks) {
          if (!chunk.trim()) continue;
          const { event, data } = parseChunk(chunk);
          if (!event) continue;
          if (event === "ping" || chunk.trim() === ":") {
            continue;
          }
          if (PUBLIC_EVENTS.includes(event) && typeof onEvent[event] === "function") {
            onEvent[event](data);
          }
          if (event === "delta" && data.text) {
            partialLength += data.text.length;
            updateActiveStreamMeta({ partialLength });
          }
          if (event === "final" || event === "error") {
            clearTimeout(stalledTimer);
            if (event === "final") {
              clearActiveStreamMeta();
              setStreamStatus(body.conversation_id, "idle");
            }
            return;
          }
        }
      }
      if (!reconnecting) {
        markStreamInterrupted(body.conversation_id);
        onEvent?.disconnected?.();
        setStreamStatus(body.conversation_id, "disconnected");
      }
    } catch (err) {
      if (err.name === "AbortError") {
        onEvent?.canceled?.();
      } else {
        markStreamInterrupted(body.conversation_id);
        onEvent?.disconnected?.();
      }
    } finally {
      clearTimeout(stalledTimer);
      setStreaming(false);
      if (!reconnecting) {
        setStreamStatus(body.conversation_id, "idle");
      }
      reader?.releaseLock();
      reader = null;
    }
  }
  return {
    start,
    cancel() {
      controller.abort();
      reader?.cancel();
      reader?.releaseLock();
      reader = null;
    },
  };
}

export function createSseStream(options) {
  const { conversationId, providerId, model, input, settings, onEvent } = options;
  return createStream({
    path: "/chat/stream",
    body: {
      conversation_id: conversationId,
      provider_id: providerId,
      model,
      input,
      settings,
    },
    onEvent,
  });
}

export function createRetryStream(conversationId, onEvent) {
  return createStream({
    path: "/chat/retry",
    body: { conversation_id: conversationId },
    onEvent,
  });
}
