// OmniAI WebUI SSE Streaming Parser

// Debug logging (check if enabled)
function debugLog(type, data = {}) {
    if (!window.__OMNI_DEBUG__) return;
    console.log(`[${new Date().toISOString()}] ${type}`, data);
}

class SSEParser {
    constructor(url, options = {}) {
        this.url = url;
        this.options = {
            method: 'GET',
            headers: {},
            ...options,
        };
        this.controller = null;
        this.reader = null;
        this.buffer = '';
        this.onEvent = options.onEvent || (() => {});
        this.onError = options.onError || (() => {});
        this.onDisconnect = options.onDisconnect || (() => {});
    }

    async start() {
        try {
            // Add CSRF token if required for streaming endpoint
            const headers = { ...this.options.headers };
            const token = getCsrfToken();
            if (token && this.options.method !== 'GET') {
                headers['X-CSRF-Token'] = token;
            }

            const response = await fetch(this.url, {
                ...this.options,
                headers,
                credentials: 'include',
            });

            if (!response.ok) {
                // Try to get detailed error message from response
                let errorMsg = `HTTP ${response.status}`;
                try {
                    const errorData = await response.json();
                    errorMsg = errorData.detail?.message || errorData.detail || errorData.message || errorMsg;
                } catch (e) {
                    // Response wasn't JSON, try text
                    try {
                        const text = await response.text();
                        if (text) errorMsg += `: ${text.slice(0, 200)}`;
                    } catch (e2) {}
                }
                throw new Error(errorMsg);
            }

            this.controller = new AbortController();
            this.reader = response.body.getReader();
            this.processStream();
        } catch (error) {
            this.onError(error);
        }
    }

    async processStream() {
        try {
            while (true) {
                const { done, value } = await this.reader.read();
                if (done) {
                    this.onDisconnect();
                    break;
                }

                // Decode chunk and add to buffer
                const chunk = new TextDecoder().decode(value);
                this.buffer += chunk;

                // Process complete lines
                const lines = this.buffer.split('\n');
                this.buffer = lines.pop(); // Keep incomplete line in buffer

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const data = line.slice(6);
                        if (data === '[DONE]') {
                            this.onEvent({ type: 'done' });
                            return;
                        }
                        try {
                            const event = JSON.parse(data);
                            debugLog('SSE_EVENT', { type: event.type, data: event });
                            this.onEvent(event);
                        } catch (error) {
                            console.warn('Failed to parse SSE event:', data, error);
                        }
                    } else if (line.startsWith('event: ')) {
                        // Handle event type if needed
                    }
                }
            }
        } catch (error) {
            if (error.name === 'AbortError') {
                return; // Cancelled
            }
            this.onError(error);
        }
    }

    stop() {
        if (this.controller) {
            this.controller.abort();
        }
        if (this.reader) {
            this.reader.cancel();
        }
    }
}

// Helper function to stream chat
// Note: Model tuning params (temperature, top_p, max_tokens) are NOT sent -
// the backend/LM Studio handles model tuning, we just specify provider and model
async function streamChat(conversationId, providerId, modelId, onEvent, onError, onDisconnect) {
    const baseUrl = getApiBaseUrl();

    // Build query parameters - only provider and model, no tuning params
    const params = new URLSearchParams();
    params.append('provider_id', providerId);
    params.append('model', modelId);

    const url = `${baseUrl}/conversations/${conversationId}/stream?${params.toString()}`;

    const parser = new SSEParser(url, {
        method: 'POST',
        headers: {
            'ngrok-skip-browser-warning': 'true',
        },
        onEvent,
        onError,
        onDisconnect,
    });

    await parser.start();
    return parser;
}