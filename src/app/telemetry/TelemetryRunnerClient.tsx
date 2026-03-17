'use client';

import { useState } from 'react';
import type { Session, TelemetryReport } from '@/lib/types';

export default function TelemetryRunnerClient({ sessions }: { sessions: Session[] }) {
  const [sessionKey, setSessionKey] = useState<string>(String(sessions[0]?.session_key ?? ''));
  const [driverNumber, setDriverNumber] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState<TelemetryReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setLoading(true);
    setError(null);
    setReport(null);
    try {
      const res = await fetch(
        `/api/agents/telemetry?session_key=${encodeURIComponent(sessionKey)}&driver_number=${encodeURIComponent(driverNumber)}`
      );
      if (!res.ok) {
        const t = await res.text();
        throw new Error(t);
      }
      const json = (await res.json()) as { telemetry?: TelemetryReport };
      if (!json.telemetry) throw new Error('No telemetry returned');
      setReport(json.telemetry);
    } catch (e: unknown) {
      setError((e as Error).message || 'Failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <label className="text-sm">
          <span className="text-zinc-600 dark:text-zinc-400">Session</span>
          <select
            className="mt-1 w-full rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm dark:border-zinc-800 dark:bg-zinc-900"
            value={sessionKey}
            onChange={(e) => setSessionKey(e.target.value)}
          >
            {sessions.map((s) => (
              <option key={s.session_key} value={String(s.session_key)}>
                {s.year} {s.circuit_short_name} — {s.session_name} ({s.session_type})
              </option>
            ))}
          </select>
        </label>

        <label className="text-sm">
          <span className="text-zinc-600 dark:text-zinc-400">Driver number</span>
          <input
            className="mt-1 w-full rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm dark:border-zinc-800 dark:bg-zinc-900"
            placeholder="e.g. 1"
            value={driverNumber}
            onChange={(e) => setDriverNumber(e.target.value)}
          />
        </label>

        <div className="flex items-end">
          <button
            className="w-full rounded-lg bg-black px-4 py-2 text-sm font-medium text-white disabled:opacity-60 dark:bg-white dark:text-black"
            onClick={run}
            disabled={loading || !sessionKey || !driverNumber}
          >
            {loading ? 'Analyzing…' : 'Run analysis'}
          </button>
        </div>
      </div>

      {error ? (
        <pre className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
          {error}
        </pre>
      ) : null}

      {report ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="rounded-xl border border-zinc-100 p-4 dark:border-zinc-900">
            <h3 className="font-semibold">Summary</h3>
            <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
              {report.driver_name} (#{report.driver_number}) — overall rating {report.overallRating}/100
            </p>
            <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-zinc-700 dark:text-zinc-300">
              {(report.insights || []).slice(0, 10).map((i, idx) => (
                <li key={idx}>{i}</li>
              ))}
            </ul>
          </div>

          <div className="rounded-xl border border-zinc-100 p-4 dark:border-zinc-900">
            <h3 className="font-semibold">Key metrics</h3>
            <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
              <Metric label="Max speed" value={`${report.speedAnalysis?.maxSpeed ?? 0} km/h`} />
              <Metric label="Avg speed" value={`${report.speedAnalysis?.avgSpeed ?? 0} km/h`} />
              <Metric label="Straight mode" value={`${report.activeAeroAnalysis?.straightModePercentage ?? 0}%`} />
              <Metric label="Overtake activations" value={`${report.activeAeroAnalysis?.overtakeModeActivations ?? 0}`} />
              <Metric label="Deploy efficiency" value={`${report.energyAnalysis?.estimatedDeploymentEfficiency ?? 0}%`} />

            </div>
          </div>
        </div>
      ) : null}

      <p className="text-xs text-zinc-500 dark:text-zinc-400">
        Tip: driver number comes from OpenF1 (e.g. Verstappen = 1).
      </p>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-zinc-100 p-3 dark:border-zinc-900">
      <p className="text-xs text-zinc-500 dark:text-zinc-400">{label}</p>
      <p className="mt-1 font-medium">{value}</p>
    </div>
  );
}
