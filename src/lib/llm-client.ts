// ============================================================
// LLM Client — Provider-agnostic, Rate-Limited, OpenAI-Compatible
// Default provider: OpenRouter
// ============================================================

import OpenAI from 'openai';

// Rate limiter with token bucket algorithm
class RateLimiter {
    private tokens: number;
    private maxTokens: number;
    private refillRate: number; // tokens per second
    private lastRefill: number;
    private queue: Array<{ resolve: () => void; reject: (err: Error) => void }> = [];

    constructor(maxRequestsPerMinute: number) {
        this.maxTokens = maxRequestsPerMinute;
        this.tokens = maxRequestsPerMinute;
        this.refillRate = maxRequestsPerMinute / 60; // tokens per second
        this.lastRefill = Date.now();
    }

    private refill() {
        const now = Date.now();
        const elapsed = (now - this.lastRefill) / 1000;
        this.tokens = Math.min(this.maxTokens, this.tokens + elapsed * this.refillRate);
        this.lastRefill = now;
    }

    async acquire(): Promise<void> {
        this.refill();
        if (this.tokens >= 1) {
            this.tokens -= 1;
            return;
        }
        // Wait until a token is available
        const waitTime = ((1 - this.tokens) / this.refillRate) * 1000;
        return new Promise((resolve, reject) => {
            this.queue.push({ resolve, reject });
            setTimeout(() => {
                this.refill();
                const item = this.queue.shift();
                if (item) {
                    this.tokens -= 1;
                    item.resolve();
                }
            }, waitTime + 100); // +100ms buffer
        });
    }
}

// Singleton rate limiter — conservative default; can be overridden per provider.
const rateLimiter = new RateLimiter(Number(process.env.LLM_MAX_RPM || 30));

type LLMProvider = 'groq' | 'openrouter' | 'ollama';

function getProvider(): LLMProvider {
    const p = (process.env.LLM_PROVIDER || 'openrouter').toLowerCase();
    if (p === 'openrouter') return 'openrouter';
    if (p === 'ollama') return 'ollama';
    return 'groq';
}

function getClient(): OpenAI {
    const provider = getProvider();

    if (provider === 'openrouter') {
        const apiKey = process.env.OPENROUTER_API_KEY;
        if (!apiKey) {
            throw new Error(
                'OPENROUTER_API_KEY environment variable is not set. ' +
                'Get your key at https://openrouter.ai/keys and add it to .env.local'
            );
        }
        return new OpenAI({
            baseURL: process.env.OPENROUTER_BASE_URL || 'https://openrouter.ai/api/v1',
            apiKey,
            defaultHeaders: {
                'HTTP-Referer': process.env.OPENROUTER_HTTP_REFERER || 'http://localhost:3000',
                'X-Title': process.env.OPENROUTER_X_TITLE || 'F1 Intelligence Platform',
            },
        });
    }

    // Ollama (OpenAI-compatible)
    // Expect an OpenAI-compatible endpoint, e.g. http://localhost:11434/v1
    // Ollama typically doesn't require an API key, but the OpenAI SDK expects one.
    if (provider === 'ollama') {
        return new OpenAI({
            baseURL: process.env.OLLAMA_BASE_URL || 'http://localhost:11434/v1',
            apiKey: process.env.OLLAMA_API_KEY || 'ollama',
        });
    }

    // Groq (OpenAI-compatible)
    const apiKey = process.env.GROQ_API_KEY;
    if (!apiKey) {
        throw new Error(
            'GROQ_API_KEY environment variable is not set. ' +
            'Get your key at https://console.groq.com/keys and add it to .env.local'
        );
    }
    return new OpenAI({
        baseURL: process.env.GROQ_BASE_URL || 'https://api.groq.com/openai/v1',
        apiKey,
    });
}

// Default model — set per provider; overridable via env.
const DEFAULT_MODEL = process.env.LLM_MODEL || process.env.GROQ_MODEL || 'llama-3.3-70b-versatile';

export interface LLMMessage {
    role: 'system' | 'user' | 'assistant';
    content: string;
}

export interface LLMOptions {
    model?: string;
    temperature?: number;
    maxTokens?: number;
    jsonMode?: boolean;
}

/**
 * Call the LLM via a configured provider with rate limiting and retry logic.
 */
export async function callLLM(
    messages: LLMMessage[],
    options: LLMOptions = {}
): Promise<string> {
    const {
        model = DEFAULT_MODEL,
        temperature = 0.7,
        maxTokens = 4096,
        jsonMode = false,
    } = options;

    // Wait for rate limit token
    await rateLimiter.acquire();

    const client = getClient();

    // Retry with exponential backoff
    let lastError: Error | null = null;
    for (let attempt = 0; attempt < 3; attempt++) {
        try {
            const completion = await client.chat.completions.create({
                model,
                messages,
                temperature,
                max_tokens: maxTokens,
                ...(jsonMode ? { response_format: { type: 'json_object' } } : {}),
            });

            const content = completion.choices?.[0]?.message?.content;
            if (!content) throw new Error('Empty response from LLM');
            return content;
        } catch (error: unknown) {
            lastError = error as Error;
            const status = (error as { status?: number }).status;

            if (status === 429) {
                // Rate limited — exponential backoff
                const delay = Math.pow(2, attempt) * 2000 + Math.random() * 1000;
                console.warn(`Rate limited (attempt ${attempt + 1}), waiting ${Math.round(delay)}ms...`);
                await new Promise(r => setTimeout(r, delay));
                continue;
            }

            if (status && status >= 500) {
                // Server error — retry
                const delay = Math.pow(2, attempt) * 1000;
                console.warn(`Server error ${status} (attempt ${attempt + 1}), retrying in ${delay}ms...`);
                await new Promise(r => setTimeout(r, delay));
                continue;
            }

            // Non-retryable error
            throw error;
        }
    }

    throw lastError || new Error('Failed after 3 retries');
}

/**
 * Call LLM and parse the response as JSON.
 */
export async function callLLMJSON<T>(
    messages: LLMMessage[],
    options: LLMOptions = {}
): Promise<T> {
    const response = await callLLM(messages, { ...options, jsonMode: true });

    try {
        // Try parsing directly
        return JSON.parse(response) as T;
    } catch {
        // Try extracting JSON from markdown code block
        const jsonMatch = response.match(/```(?:json)?\s*([\s\S]*?)\s*```/);
        if (jsonMatch) {
            return JSON.parse(jsonMatch[1]) as T;
        }
        // Try finding the first { or [ 
        const start = response.indexOf('{') !== -1 ? response.indexOf('{') : response.indexOf('[');
        const end = response.lastIndexOf('}') !== -1 ? response.lastIndexOf('}') : response.lastIndexOf(']');
        if (start !== -1 && end !== -1) {
            return JSON.parse(response.substring(start, end + 1)) as T;
        }
        throw new Error(`Failed to parse LLM JSON response: ${response.substring(0, 200)}`);
    }
}

/**
 * Check if the API key is configured.
 */
export function isLLMConfigured(): boolean {
    const provider = getProvider();
    if (provider === 'openrouter') return !!process.env.OPENROUTER_API_KEY;
    if (provider === 'ollama') return true;
    return !!process.env.GROQ_API_KEY;
}
