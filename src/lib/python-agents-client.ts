import { createLogger } from './logger';
import type { NewsItem, PredictionResult, SeasonSnapshot, TelemetryReport } from '@/lib/types';

const log = createLogger('PythonAgents');

export interface PythonAgentRunResponse {
  answer: string;
  tool_calls: Array<Record<string, unknown>>;
  trace?: Record<string, unknown>;
}

export interface PythonNewsResponse {
  news: NewsItem[];
  evidence: { sources: string[] };
  toolTrace?: Array<Record<string, unknown>>;
}

export interface PythonPredictionResponse {
  prediction: PredictionResult;
  evidence: { sources: string[] };
  toolTrace?: Array<Record<string, unknown>>;
}

export interface PythonSeasonResponse {
  season: SeasonSnapshot;
  evidence: { sources: string[] };
  toolTrace?: Array<Record<string, unknown>>;
}

export interface PythonTelemetryResponse {
  telemetry: TelemetryReport;
  evidence: { sources: string[] };
  toolTrace?: Array<Record<string, unknown>>;
}

const DEFAULT_BASE = 'http://localhost:8001';

function getBaseUrl() {
  return process.env.PY_AGENTS_URL || DEFAULT_BASE;
}

export async function callPythonAgent(message: string, namespace = 'f1', extra_system?: string) {
  return callPythonAgentTyped({ message, namespace, extra_system });
}

export async function callPythonAgentTyped(opts: {
  message: string;
  namespace?: string;
  extra_system?: string;
  agent_type?: 'general' | 'news' | 'season_form' | 'telemetry' | 'tyre_weather' | 'predict_pipeline';
}) {
  const baseUrl = getBaseUrl();
  const url = `${baseUrl}/agent/run`;

  log.info(`📡 Calling Python agent service`, {
    url,
    agent_type: opts.agent_type ?? 'general',
    namespace: opts.namespace ?? 'f1',
    messagePreview: opts.message.slice(0, 150) + (opts.message.length > 150 ? '...' : ''),
  });

  const startTime = Date.now();

  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: opts.message,
        namespace: opts.namespace ?? 'f1',
        extra_system: opts.extra_system,
        agent_type: opts.agent_type ?? 'general',
      }),
    });

    const durationMs = Date.now() - startTime;

    if (!res.ok) {
      const txt = await res.text().catch(() => '');
      log.error(`Python agent returned ${res.status}`, {
        url,
        status: res.status,
        statusText: res.statusText,
        responseBody: txt.slice(0, 500),
        durationMs,
        hint: 'Is the Python agents service running? Start it with: cd agents_py && python -m f1_agents_service',
      });
      throw new Error(`Python agent error ${res.status}: ${txt}`);
    }

    const data = (await res.json()) as PythonAgentRunResponse;
    log.info(`✅ Python agent responded`, {
      durationMs,
      answerLength: data.answer?.length ?? 0,
      toolCallCount: data.tool_calls?.length ?? 0,
    });

    return data;
  } catch (error) {
    const durationMs = Date.now() - startTime;

    if (error instanceof TypeError && (error as Error).message?.includes('fetch')) {
      log.error(`🚫 Cannot reach Python agent service at ${baseUrl}`, {
        error: (error as Error).message,
        durationMs,
        hint: `The Python agents service is not running. Start it:\n  cd agents_py && source .venv/bin/activate && python -m f1_agents_service\n\nOr set PY_AGENTS_URL env variable to point to the running service.`,
      });
    } else if (!(error instanceof Error && error.message.startsWith('Python agent error'))) {
      log.error(`Python agent call failed`, {
        error: error instanceof Error ? { message: error.message, stack: error.stack?.split('\n').slice(0, 5).join('\n') } : String(error),
        durationMs,
      });
    }

    throw error;
  }
}
