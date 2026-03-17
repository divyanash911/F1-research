import { NextResponse } from 'next/server';
import { callPythonAgent } from '@/lib/python-agents-client';
import { createLogger } from '@/lib/logger';
import type { NewsItem } from '@/lib/types';

const log = createLogger('API-Agent-News');

export async function GET() {
  log.info(`GET /api/agents/news`);
  const startTime = Date.now();
  try {
    const today = new Date().toISOString().split('T')[0];
    const extra =
      `Return ONLY valid JSON with this shape: {"news": NewsItem[], "evidence": {"sources": string[]}}.\n` +
      `Each NewsItem: {id,title,summary,category,impactLevel,relatedTeams,relatedDrivers,timestamp}.\n` +
      `Use tools aggressively (OpenF1 + web search + KB). Today is ${today}. Include sources (urls or OpenF1 endpoints).`;

    const resp = await callPythonAgent(
      'Fetch the most important current Formula 1 news and context. Produce 6-10 items prioritized by relevance to upcoming race performance. If claims are uncertain, say so and cite sources.',
      'f1_news',
      extra
    );

    const parsed = safeJson<{ news: NewsItem[]; evidence?: { sources: string[] } }>(resp.answer);

    log.info(`✅ GET /api/agents/news success`, { durationMs: Date.now() - startTime, itemCount: parsed?.news?.length });

    return NextResponse.json({
      news: parsed?.news ?? [],
      evidence: parsed?.evidence ?? { sources: [] },
      toolTrace: resp.tool_calls,
    });
  } catch (e: unknown) {
    log.error(`❌ GET /api/agents/news failed`, {
      error: e instanceof Error ? { message: e.message, stack: e.stack } : String(e),
      durationMs: Date.now() - startTime
    });
    return NextResponse.json(
      { error: (e as Error).message || 'Failed to fetch agent news' },
      { status: 500 }
    );
  }
}

function safeJson<T>(text: string): T | null {
  try {
    return JSON.parse(text) as T;
  } catch {
    const m = text.match(/```(?:json)?\s*([\s\S]*?)\s*```/);
    if (m) {
      try {
        return JSON.parse(m[1]) as T;
      } catch {
        return null;
      }
    }
    const start = text.indexOf('{');
    const end = text.lastIndexOf('}');
    if (start !== -1 && end !== -1) {
      try {
        return JSON.parse(text.slice(start, end + 1)) as T;
      } catch {
        return null;
      }
    }
    return null;
  }
}
