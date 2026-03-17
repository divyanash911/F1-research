// ============================================================
// Agent Orchestrator — Coordinates All Specialized Agents
// ============================================================

import { analyzeTelemetry, type TelemetryAnalysisInput } from './telemetry-agent';
import { getNewsIntelligence } from './news-agent';
import { getSeasonStats } from './season-stats-agent';
import { predictNextRace } from './prediction-agent';
import { getReplayData } from './replay-agent';
import { createLogger } from '@/lib/logger';

import type {
    TelemetryReport, NewsItem, SeasonSnapshot, PredictionResult, ReplayData
} from '@/lib/types';

const log = createLogger('Orchestrator');

export type AgentTask =
    | { type: 'telemetry'; input: TelemetryAnalysisInput }
    | { type: 'news' }
    | { type: 'season_stats' }
    | { type: 'prediction' }
    | { type: 'replay'; input: { session_key: number } }
    | { type: 'full_analysis'; input: TelemetryAnalysisInput };

export interface OrchestratorResult {
    telemetry?: TelemetryReport;
    news?: NewsItem[];
    seasonStats?: SeasonSnapshot;
    prediction?: PredictionResult;
    replay?: ReplayData;
    executionTime: number;
    agentsUsed: string[];
}

/**
 * The Orchestrator dispatches tasks to specialized agents
 * and aggregates their results.
 */
export async function orchestrate(task: AgentTask): Promise<OrchestratorResult> {
    const startTime = Date.now();
    log.separator(`Orchestrator: ${task.type}`);
    log.info(`🎯 Dispatching task: ${task.type}`, 'input' in task ? task.input : undefined);

    const result: OrchestratorResult = {
        executionTime: 0,
        agentsUsed: [],
    };

    try {
        switch (task.type) {
            case 'telemetry':
                result.telemetry = await analyzeTelemetry(task.input);
                result.agentsUsed.push('Telemetry Analysis Agent');
                break;

            case 'news':
                result.news = await getNewsIntelligence();
                result.agentsUsed.push('News Intelligence Agent');
                break;

            case 'season_stats':
                result.seasonStats = await getSeasonStats();
                result.agentsUsed.push('Season Stats Agent');
                break;

            case 'prediction':
                result.prediction = await predictNextRace();
                result.agentsUsed.push('Race Prediction Agent');
                break;

            case 'replay':
                result.replay = await getReplayData(task.input.session_key);
                result.agentsUsed.push('Race Replay Agent');
                break;

            case 'full_analysis':
                // Run all agents in parallel for comprehensive analysis
                const [telemetry, news, seasonStats, prediction] = await Promise.all([
                    analyzeTelemetry(task.input),
                    getNewsIntelligence(),
                    getSeasonStats(),
                    predictNextRace(),
                ]);
                result.telemetry = telemetry;
                result.news = news;
                result.seasonStats = seasonStats;
                result.prediction = prediction;
                result.agentsUsed.push(
                    'Telemetry Analysis Agent',
                    'News Intelligence Agent',
                    'Season Stats Agent',
                    'Race Prediction Agent',
                );
                break;
        }
    } catch (error) {
        log.error('Orchestrator error', {
            task: task.type,
            error: error instanceof Error ? {
                message: error.message,
                stack: error.stack?.split('\n').slice(0, 5).join('\n'),
            } : String(error),
        });
    }

    result.executionTime = Date.now() - startTime;
    log.info(`✅ Orchestration complete`, {
        task: task.type,
        executionTime: `${result.executionTime}ms`,
        agentsUsed: result.agentsUsed,
    });
    return result;
}
