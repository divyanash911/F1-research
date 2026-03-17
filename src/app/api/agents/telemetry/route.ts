import { NextResponse } from 'next/server';
import { callPythonAgent } from '@/lib/python-agents-client';
import { createLogger } from '@/lib/logger';
import type { TelemetryReport } from '@/lib/types';

const log = createLogger('API-Agent-Telemetry');

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const session_key = searchParams.get('session_key');
  const driver_number = searchParams.get('driver_number');

  log.info(`GET /api/agents/telemetry`, { session_key, driver_number });

  if (!session_key || !driver_number) {
    log.warn('Missing session_key or driver_number');
    return NextResponse.json(
      { error: 'session_key and driver_number required' },
      { status: 400 }
    );
  }

  const startTime = Date.now();

  try {
    const today = new Date().toISOString().split('T')[0];
    const extra =
      `Return ONLY valid JSON with this shape: {"telemetry": TelemetryReport, "evidence": {"sources": string[]}}.\n` +
      `TelemetryReport must match the TS type shape in the webapp.\n` +
      `You may call OpenF1 tools as much as needed. Default to year 2026 where relevant. Today is ${today}. Include sources.`;

    const msg = `Analyze telemetry/performance for driver #${driver_number} in session_key ${session_key}.\n\n` +
      `Use OpenF1 tools (laps, stints, weather, pit, intervals, race control, positions) to derive metrics. ` +
      `Then produce a structured TelemetryReport with insights and an overallRating. ` +
      `If some fields can't be computed, fill them with reasonable defaults and explain in insights.`;

    const resp = await callPythonAgent(msg, 'f1_telemetry', extra);
    const parsed = safeJson<{ telemetry: TelemetryReport; evidence?: { sources: string[] } }>(resp.answer);

    log.info(`✅ GET /api/agents/telemetry success`, { durationMs: Date.now() - startTime });

    return NextResponse.json({
      telemetry: parsed?.telemetry,
      evidence: parsed?.evidence ?? { sources: [] },
      toolTrace: resp.tool_calls,
    });
  } catch (e: unknown) {
    log.error(`❌ GET /api/agents/telemetry failed`, {
      error: e instanceof Error ? { message: e.message, stack: e.stack } : String(e),
      durationMs: Date.now() - startTime
    });
    return NextResponse.json(
      { error: (e as Error).message || 'Failed to fetch telemetry report' },
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
