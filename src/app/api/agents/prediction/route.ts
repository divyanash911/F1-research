import { NextResponse } from 'next/server';
import { callPythonAgentTyped } from '@/lib/python-agents-client';
import { createLogger } from '@/lib/logger';
import type { PredictionResult } from '@/lib/types';

const log = createLogger('API-Agent-Prediction');

export async function GET() {
  log.info(`GET /api/agents/prediction`);
  const startTime = Date.now();
  try {
    const today = new Date().toISOString().split('T')[0];
    const extra =
      `Return ONLY valid JSON with this shape: {"prediction": PredictionResult, "evidence": {"sources": string[]}}.\n` +
      `PredictionResult must include nextRace, predictedOrder (22 drivers), keyBattles, strategyPredictions, narrative.\n` +
      `Use tools freely: OpenF1 calendar/results, web search for recent updates, and KB. Today is ${today}. Include sources.`;

    const resp = await callPythonAgentTyped({
      agent_type: 'predict_pipeline',
      message:
        'Generate the best possible prediction for the next F1 race. Use the pipeline: season_form + tyre_weather + news, then synthesize. Produce a 22-driver predicted order with confidence and key factors for each driver.',
      namespace: 'f1_prediction',
      extra_system: extra,
    });

    const parsed = safeJson<{ prediction: PredictionResult; evidence?: { sources: string[] } }>(resp.answer);

    log.info(`✅ GET /api/agents/prediction success`, { durationMs: Date.now() - startTime });

    return NextResponse.json({
      prediction: parsed?.prediction,
      evidence: parsed?.evidence ?? { sources: [] },
      toolTrace: resp.tool_calls,
    });
  } catch (e: unknown) {
    log.error(`❌ GET /api/agents/prediction failed`, {
      error: e instanceof Error ? { message: e.message, stack: e.stack } : String(e),
      durationMs: Date.now() - startTime
    });
    return NextResponse.json(
      { error: (e as Error).message || 'Failed to fetch agent prediction' },
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
