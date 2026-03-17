// ============================================================
// In-Memory LRU Cache with TTL
// ============================================================

interface CacheEntry<T> {
    data: T;
    timestamp: number;
    ttl: number;
}

export class Cache {
    private store = new Map<string, CacheEntry<unknown>>();
    private maxSize: number;
    private defaultTTL: number; // ms

    constructor(maxSize = 200, defaultTTLSeconds = 300) {
        this.maxSize = maxSize;
        this.defaultTTL = defaultTTLSeconds * 1000;
    }

    get<T>(key: string): T | undefined {
        const entry = this.store.get(key) as CacheEntry<T> | undefined;
        if (!entry) return undefined;

        if (Date.now() - entry.timestamp > entry.ttl) {
            this.store.delete(key);
            return undefined;
        }

        // Move to end for LRU
        this.store.delete(key);
        this.store.set(key, entry);
        return entry.data;
    }

    set<T>(key: string, data: T, ttlSeconds?: number): void {
        if (this.store.size >= this.maxSize) {
            // Remove oldest entry
            const firstKey = this.store.keys().next().value;
            if (firstKey) this.store.delete(firstKey);
        }
        this.store.set(key, {
            data,
            timestamp: Date.now(),
            ttl: ttlSeconds ? ttlSeconds * 1000 : this.defaultTTL,
        });
    }

    clear(): void {
        this.store.clear();
    }

    get size(): number {
        return this.store.size;
    }
}

// Singleton cache instance
export const apiCache = new Cache(500, 300); // 500 entries, 5 min default TTL
