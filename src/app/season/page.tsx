import { headers } from 'next/headers';
import Link from 'next/link';
import type { SeasonSnapshot } from '@/lib/types';

async function getOrigin() {
  const h = await headers();
  const proto = h.get('x-forwarded-proto') ?? 'http';
  const host = h.get('x-forwarded-host') ?? h.get('host') ?? 'localhost:3000';
  return `${proto}://${host}`;
}

async function getSeason(): Promise<{ season?: SeasonSnapshot; evidence?: { sources: string[] } }> {
  const origin = await getOrigin();
  const res = await fetch(`${origin}/api/agents/season`, { cache: 'no-store' });
  if (!res.ok) return {};
  return (await res.json()) as { season?: SeasonSnapshot; evidence?: { sources: string[] } };
}

export default async function SeasonPage() {
  const data = await getSeason();
  const season = data.season;

  return (
    <div className="min-h-screen bg-zinc-50 text-zinc-900 dark:bg-black dark:text-zinc-50">
      <div className="mx-auto max-w-6xl px-6 py-10">
        <div className="flex items-baseline justify-between">
          <h1 className="text-2xl font-semibold tracking-tight">Season snapshot (2026)</h1>
          <Link className="text-sm text-zinc-600 hover:underline dark:text-zinc-400" href="/">
            ← Back
          </Link>
        </div>

        {!season ? (
          <p className="mt-6 text-sm text-zinc-600 dark:text-zinc-400">
            No season data yet (agent service offline?).
          </p>
        ) : (
          <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
            <section className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
              <h2 className="text-lg font-semibold">WDC</h2>
              <ol className="mt-3 space-y-1 text-sm">
                {season.wdc.slice(0, 15).map((d) => (
                  <li key={d.driver_number} className="flex items-center justify-between rounded-lg border border-zinc-100 px-3 py-2 dark:border-zinc-900">
                    <span>
                      <span className="mr-2 text-zinc-500 dark:text-zinc-400">P{d.position}</span>
                      {d.driver_name} <span className="text-zinc-500 dark:text-zinc-400">({d.team})</span>
                    </span>
                    <span className="text-xs text-zinc-500 dark:text-zinc-400">{d.points} pts</span>
                  </li>
                ))}
              </ol>
            </section>

            <section className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
              <h2 className="text-lg font-semibold">WCC</h2>
              <ol className="mt-3 space-y-1 text-sm">
                {season.wcc.map((t) => (
                  <li key={t.team} className="flex items-center justify-between rounded-lg border border-zinc-100 px-3 py-2 dark:border-zinc-900">
                    <span>
                      <span className="mr-2 text-zinc-500 dark:text-zinc-400">P{t.position}</span>
                      {t.team}
                    </span>
                    <span className="text-xs text-zinc-500 dark:text-zinc-400">{t.points} pts</span>
                  </li>
                ))}
              </ol>
            </section>

            <section className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950 lg:col-span-2">
              <h2 className="text-lg font-semibold">Recent results</h2>
              <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-3">
                {season.recentResults.map((r) => (
                  <div key={r.race} className="rounded-xl border border-zinc-100 p-4 text-sm dark:border-zinc-900">
                    <p className="font-medium">{r.race}</p>
                    <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">{r.date}</p>
                    <p className="mt-2"><span className="text-zinc-500 dark:text-zinc-400">Winner:</span> {r.winner}</p>
                    <p className="mt-1 text-xs text-zinc-600 dark:text-zinc-400">Podium: {r.podium.join(', ')}</p>
                  </div>
                ))}
              </div>

              {data.evidence?.sources?.length ? (
                <details className="mt-4">
                  <summary className="cursor-pointer text-xs text-zinc-600 dark:text-zinc-400">Evidence</summary>
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-zinc-600 dark:text-zinc-400">
                    {data.evidence.sources.slice(0, 10).map((s) => (
                      <li key={s}>{s}</li>
                    ))}
                  </ul>
                </details>
              ) : null}
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
