import { NextResponse } from 'next/server';
import { callPythonAgent } from '@/lib/python-agents-client';
import { createLogger } from '@/lib/logger';
import type { SeasonSnapshot } from '@/lib/types';

const log = createLogger('API-Agent-Season');

export async function GET() {
  log.info(`GET /api/agents/season`);
  const startTime = Date.now();
  try {
    const today = new Date().toISOString().split('T')[0];
    const extra =
      `Return ONLY valid JSON with this shape: {"season": SeasonSnapshot, "evidence": {"sources": string[]}}.\n` +
      `SeasonSnapshot must contain: wdc, wcc, recentResults (use OpenF1 endpoints).\n` +
      `Default to year 2026. Use tools freely (OpenF1 + web search + KB). Today is ${today}. Include sources.`;

    const resp = await callPythonAgent(
      'Build a 2026 season snapshot: WDC standings, WCC standings, and the last 3 race winners/podiums. Prefer OpenF1 data. If data is missing, explain uncertainty and still return best-effort structured output.',
      'f1_season',
      extra
    );

    const parsed = safeJson<{ season: SeasonSnapshot; evidence?: { sources: string[] } }>(resp.answer);

    log.info(`✅ GET /api/agents/season success`, { durationMs: Date.now() - startTime });

    return NextResponse.json({
      season: parsed?.season,
      evidence: parsed?.evidence ?? { sources: [] },
      toolTrace: resp.tool_calls,
    });
  } catch (e: unknown) {
    log.error(`❌ GET /api/agents/season failed`, {
      error: e instanceof Error ? { message: e.message, stack: e.stack } : String(e),
      durationMs: Date.now() - startTime
    });
    return NextResponse.json(
      { error: (e as Error).message || 'Failed to fetch season snapshot' },
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
