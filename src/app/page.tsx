import type { NewsItem, PredictionResult } from '@/lib/types';
import { headers } from 'next/headers';

async function getOrigin() {
  const h = await headers();
  const proto = h.get('x-forwarded-proto') ?? 'http';
  const host = h.get('x-forwarded-host') ?? h.get('host') ?? 'localhost:3000';
  return `${proto}://${host}`;
}

async function getNews(): Promise<{ news: NewsItem[]; evidence?: { sources: string[] } }> {
  const origin = await getOrigin();
  const res = await fetch(`${origin}/api/agents/news`, {
    cache: 'no-store',
  });
  if (!res.ok) return { news: [] };
  return (await res.json()) as { news: NewsItem[]; evidence?: { sources: string[] } };
}

async function getPrediction(): Promise<{ prediction?: PredictionResult; evidence?: { sources: string[] } }> {
  const origin = await getOrigin();
  const res = await fetch(`${origin}/api/agents/prediction`, {
    cache: 'no-store',
  });
  if (!res.ok) return {};
  return (await res.json()) as { prediction?: PredictionResult; evidence?: { sources: string[] } };
}

export default async function Home() {
  const [newsRes, predRes] = await Promise.all([getNews(), getPrediction()]);
  const news = newsRes.news || [];
  const prediction = predRes.prediction;

  return (
    <div className="min-h-screen bg-zinc-50 text-zinc-900 dark:bg-black dark:text-zinc-50">
      <div className="mx-auto max-w-6xl px-6 py-10">
        <header className="flex flex-col gap-2">
          <h1 className="text-3xl font-semibold tracking-tight">F1 Intelligence</h1>
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            Agent-driven research: OpenF1 + web search + long-term memory.
          </p>
        </header>

        <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-2">
          <section className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
            <div className="flex items-baseline justify-between">
              <h2 className="text-lg font-semibold">Latest news</h2>
              <span className="text-xs text-zinc-500 dark:text-zinc-400">{news.length} items</span>
            </div>

            <div className="mt-4 space-y-4">
              {news.length === 0 ? (
                <p className="text-sm text-zinc-600 dark:text-zinc-400">No news yet (agent service offline?).</p>
              ) : (
                news.map((n) => (
                  <article key={n.id} className="rounded-xl border border-zinc-100 p-4 dark:border-zinc-900">
                    <div className="flex items-center justify-between gap-3">
                      <h3 className="font-medium leading-6">{n.title}</h3>
                      <span className="text-xs text-zinc-500 dark:text-zinc-400">{n.impactLevel}</span>
                    </div>
                    <p className="mt-2 text-sm text-zinc-700 dark:text-zinc-300">{n.summary}</p>
                    <div className="mt-3 flex flex-wrap gap-2 text-xs text-zinc-600 dark:text-zinc-400">
                      <span className="rounded-full bg-zinc-100 px-2 py-1 dark:bg-zinc-900">{n.category}</span>
                      {n.relatedTeams?.slice(0, 3).map((t) => (
                        <span key={t} className="rounded-full bg-zinc-100 px-2 py-1 dark:bg-zinc-900">
                          {t}
                        </span>
                      ))}
                      {n.relatedDrivers?.slice(0, 2).map((d) => (
                        <span key={d} className="rounded-full bg-zinc-100 px-2 py-1 dark:bg-zinc-900">
                          {d}
                        </span>
                      ))}
                    </div>
                  </article>
                ))
              )}
            </div>

            {newsRes.evidence?.sources?.length ? (
              <details className="mt-4">
                <summary className="cursor-pointer text-xs text-zinc-600 dark:text-zinc-400">Evidence</summary>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-zinc-600 dark:text-zinc-400">
                  {newsRes.evidence.sources.slice(0, 10).map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ul>
              </details>
            ) : null}
          </section>

          <section className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
            <h2 className="text-lg font-semibold">Next race prediction</h2>

            {!prediction ? (
              <p className="mt-4 text-sm text-zinc-600 dark:text-zinc-400">No prediction yet (agent service offline?).</p>
            ) : (
              <div className="mt-4 space-y-4">
                <div>
                  <p className="text-sm text-zinc-600 dark:text-zinc-400">Next race</p>
                  <p className="text-base font-medium">
                    {prediction.nextRace?.name} — {prediction.nextRace?.circuit}
                  </p>
                  <p className="text-xs text-zinc-500 dark:text-zinc-400">{prediction.nextRace?.date}</p>
                </div>

                <div>
                  <p className="text-sm font-medium">Top 10</p>
                  <ol className="mt-2 space-y-1 text-sm">
                    {(prediction.predictedOrder || []).slice(0, 10).map((p) => (
                      <li key={p.driver_number} className="flex items-center justify-between rounded-lg border border-zinc-100 px-3 py-2 dark:border-zinc-900">
                        <span>
                          <span className="mr-2 text-zinc-500 dark:text-zinc-400">P{p.position}</span>
                          {p.driver_name} <span className="text-zinc-500 dark:text-zinc-400">({p.team})</span>
                        </span>
                        <span className="text-xs text-zinc-500 dark:text-zinc-400">{p.confidence}%</span>
                      </li>
                    ))}
                  </ol>
                </div>

                {prediction.narrative ? (
                  <div>
                    <p className="text-sm font-medium">Preview</p>
                    <p className="mt-2 text-sm text-zinc-700 dark:text-zinc-300">{prediction.narrative}</p>
                  </div>
                ) : null}

                {predRes.evidence?.sources?.length ? (
                  <details>
                    <summary className="cursor-pointer text-xs text-zinc-600 dark:text-zinc-400">Evidence</summary>
                    <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-zinc-600 dark:text-zinc-400">
                      {predRes.evidence.sources.slice(0, 10).map((s) => (
                        <li key={s}>{s}</li>
                      ))}
                    </ul>
                  </details>
                ) : null}
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
