export const dynamic = 'force-dynamic';

type EvidenceItem = {
  source_type: string;
  source_id: string;
  title?: string | null;
  retrieved_at?: string;
  quote?: string | null;
  metadata?: Record<string, unknown>;
};

type Finding = {
  id: string;
  created_at?: string;
  topic: string;
  summary: string;
  details_md?: string;
  confidence?: number;
  tags?: string[];
  evidence?: EvidenceItem[];
};

type InsightBundle = {
  run_id: string;
  created_at: string;
  kind: string;
  headline: string;
  tldr: string;
  findings: Finding[];
};

async function getInsights(): Promise<InsightBundle[]> {
  const res = await fetch(`${process.env.NEXT_PUBLIC_BASE_URL || ''}/api/autonomous/insights?limit=30`, {
    cache: 'no-store',
  });
  if (!res.ok) return [];
  const json = (await res.json()) as { items?: InsightBundle[] };
  return json.items ?? [];
}

export default async function InsightsPage() {
  const items = await getInsights();

  return (
    <main style={{ padding: 24, maxWidth: 980, margin: '0 auto' }}>
      <h1 style={{ fontSize: 28, fontWeight: 700 }}>Autonomous Insights</h1>
      <p style={{ opacity: 0.8, marginTop: 8 }}>
        This feed is generated continuously by the autonomous research loop.
      </p>

      {items.length === 0 ? (
        <div style={{ marginTop: 24, opacity: 0.75 }}>
          No insights yet. Enable the autonomous loop in the agents service and wait for the first run.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginTop: 24 }}>
          {items.map((b) => (
            <section
              key={b.run_id}
              style={{ border: '1px solid rgba(255,255,255,0.12)', borderRadius: 12, padding: 16 }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                <div>
                  <div style={{ fontSize: 12, opacity: 0.7 }}>
                    {new Date(b.created_at).toLocaleString()} • {b.kind}
                  </div>
                  <h2 style={{ marginTop: 6, fontSize: 18, fontWeight: 650 }}>{b.headline}</h2>
                </div>
              </div>

              {b.tldr ? <p style={{ marginTop: 10, opacity: 0.9 }}>{b.tldr}</p> : null}

              {b.findings?.length ? (
                <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {b.findings.slice(0, 6).map((f) => (
                    <div key={f.id} style={{ padding: 12, borderRadius: 10, background: 'rgba(255,255,255,0.04)' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
                        <strong>{f.topic}</strong>
                        {typeof f.confidence === 'number' ? (
                          <span style={{ fontSize: 12, opacity: 0.7 }}>
                            confidence: {(f.confidence * 100).toFixed(0)}%
                          </span>
                        ) : null}
                      </div>
                      <div style={{ marginTop: 6, opacity: 0.9 }}>{f.summary}</div>
                      {f.evidence?.length ? (
                        <ul style={{ marginTop: 8, paddingLeft: 18, opacity: 0.85 }}>
                          {f.evidence.slice(0, 3).map((e, idx) => (
                            <li key={idx} style={{ fontSize: 12 }}>
                              <a href={e.source_id} target="_blank" rel="noreferrer">
                                {e.title || e.source_id}
                              </a>
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </div>
                  ))}
                </div>
              ) : null}
            </section>
          ))}
        </div>
      )}
    </main>
  );
}
