// OmniAI WebUI SSE Streaming Parser

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
                throw new Error(`HTTP ${response.status}`);
            }

            this.controller = new AbortController();
            this.reader = response.body.getReader();
            this.processStream();
        } catch (error) {
            this.onError(error);
        }
    }

    async processStream() {
        let currentEventType = 'message'; // Default SSE event type

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
                    if (line.startsWith('event: ')) {
                        // Track the event type for the next data line
                        currentEventType = line.slice(7).trim();
                    } else if (line.startsWith('data: ')) {
                        const data = line.slice(6);
                        if (data === '[DONE]') {
                            this.onEvent({ type: 'done' });
                            return;
                        }
                        try {
                            const event = JSON.parse(data);
                            // Add the event type from the "event:" line
                            event.type = currentEventType;
                            this.onEvent(event);
                        } catch (error) {
                            console.warn('Failed to parse SSE event:', data, error);
                        }
                        // Reset to default after processing
                        currentEventType = 'message';
                    } else if (line === '') {
                        // Empty line marks end of event, reset type
                        currentEventType = 'message';
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
async function streamChat(conversationId, providerId, modelId, settings = {}, onEvent, onError, onDisconnect) {
    const baseUrl = getApiBaseUrl();
    const url = `${baseUrl}/conversations/${conversationId}/stream`;

    // Backend expects flat structure with "model" (not "model_id")
    const body = JSON.stringify({
        provider_id: providerId,
        model: modelId,
        temperature: settings.temperature,
        top_p: settings.top_p,
        max_tokens: settings.max_tokens,
    });

    const parser = new SSEParser(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'ngrok-skip-browser-warning': 'true',
        },
        body,
        onEvent,
        onError,
        onDisconnect,
    });

    await parser.start();
    return parser;
}