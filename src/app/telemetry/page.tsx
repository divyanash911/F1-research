'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import TelemetryRunnerClient from './TelemetryRunnerClient';
import type { Session } from '@/lib/types';

export default function TelemetryPage() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch('/api/sessions?year=2026', { cache: 'no-store' });
        if (!res.ok) throw new Error(await res.text());
        const json = (await res.json()) as Session[];
        if (!cancelled) setSessions(json);
      } catch (e: unknown) {
        if (!cancelled) setError((e as Error).message || 'Failed to load sessions');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="min-h-screen bg-zinc-50 text-zinc-900 dark:bg-black dark:text-zinc-50">
      <div className="mx-auto max-w-6xl px-6 py-10">
        <div className="flex items-baseline justify-between">
          <h1 className="text-2xl font-semibold tracking-tight">Telemetry analysis</h1>
          <Link className="text-sm text-zinc-600 hover:underline dark:text-zinc-400" href="/">
            ← Back
          </Link>
        </div>

        <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
          Pick a session and driver, then run an agent-backed analysis.
        </p>

        <div className="mt-6 rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
          {loading ? (
            <p className="text-sm text-zinc-600 dark:text-zinc-400">Loading sessions…</p>
          ) : error ? (
            <pre className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
              {error}
            </pre>
          ) : sessions.length ? (
            <TelemetryRunnerClient sessions={sessions} />
          ) : (
            <p className="text-sm text-zinc-600 dark:text-zinc-400">No sessions found for 2026.</p>
          )}
        </div>
      </div>
    </div>
  );
}
