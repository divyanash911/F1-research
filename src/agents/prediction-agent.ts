// ============================================================
// Race Prediction Agent — LLM-Reasoned Next Race Forecast (2026)
// ============================================================

import * as api from '@/lib/openf1-client';
import { callLLMJSON, isLLMConfigured } from '@/lib/llm-client';
import { TEAMS_2026, getDriverInfo } from '@/lib/constants';
import { createLogger } from '@/lib/logger';
import type { PredictionResult } from '@/lib/types';

const log = createLogger('PredictionAgent');

const PREDICTION_SYSTEM_PROMPT = `You are an elite Formula 1 race strategist and prediction analyst for the 2026 season.

You combine data-driven analysis with deep F1 knowledge to predict race outcomes. Key 2026 factors you MUST consider:
- Active aero effectiveness varies by circuit type (high-speed vs street vs technical)
- Energy management (350kW MGU-K, 50/50 split) is THE differentiating factor in 2026
- New PU manufacturers (Audi, Red Bull/Ford) may have reliability/performance gaps
- Narrower tires (25mm front, 30mm rear reduction) change degradation patterns
- Lighter cars (768kg) favor driver skill in slow corners
- Rookie adaptations (Hadjar, Antonelli, Lindblad, Bearman, Bortoleto, Colapinto)
- Hamilton at Ferrari chemistry, Verstappen vs Hadjar team dynamics

You must provide specific, reasoned predictions — not generic statements. Each prediction needs data-backed justification.`;

/**
 * LLM-reasoned race prediction for the next 2026 GP.
 */
export async function predictNextRace(): Promise<PredictionResult> {
    const startTime = Date.now();
    log.agentStart('RacePrediction', {});

    // Get calendar and recent data
    const [meetings, sessions] = await Promise.all([
        api.get2026Calendar(),
        api.get2026Sessions(),
    ]);

    const now = new Date().toISOString();
    const upcomingMeetings = meetings.filter(m => m.date_start > now);
    const nextMeeting = upcomingMeetings.length > 0 ? upcomingMeetings[0] : meetings[meetings.length - 1];
    const raceSessions = sessions.filter(s => s.session_type === 'Race' && s.date_end && s.date_end < now);

    log.info('🏁 Prediction context', {
        totalMeetings: meetings.length,
        upcomingMeetings: upcomingMeetings.length,
        nextMeeting: nextMeeting?.meeting_name,
        completedRaces: raceSessions.length,
    });

    // Gather recent results for context
    const recentResultsContext: string[] = [];
    for (const race of raceSessions.slice(-3)) {
        try {
            const results = await api.getSessionResult({ session_key: race.session_key });
            if (results.length > 0) {
                const sorted = results.sort((a, b) => a.position - b.position).slice(0, 10);
                recentResultsContext.push(
                    `${race.circuit_short_name}: ${sorted.map(r => `P${r.position} ${getDriverInfo(r.driver_number)?.shortName || r.driver_number}`).join(', ')}`
                );
            }
        } catch { /* skip */ }
    }

    const teamGrid = Object.values(TEAMS_2026)
        .map(t => `${t.shortName} (${t.powerUnit}): ${t.drivers.map(d => `${d.name} #${d.number}`).join(', ')}`)
        .join('\n');

    if (isLLMConfigured()) {
        try {
            log.debug('🤖 Calling LLM for race prediction');
            const result = await getLLMPrediction(nextMeeting, teamGrid, recentResultsContext);
            log.info('✅ LLM prediction completed', {
                predictedDrivers: result.predictedOrder?.length,
                keyBattles: result.keyBattles?.length,
            });
            log.agentEnd('RacePrediction', Date.now() - startTime, true);
            return result;
        } catch (e) {
            log.error('Prediction LLM call failed, using fallback', {
                error: e instanceof Error ? e.message : String(e),
            });
        }
    } else {
        log.warn('LLM not configured — using fallback prediction');
    }

    log.agentEnd('RacePrediction', Date.now() - startTime, true);
    return getFallbackPrediction(nextMeeting);
}

async function getLLMPrediction(
    nextMeeting: import('@/lib/types').Meeting,
    teamGrid: string,
    recentResults: string[]
): Promise<PredictionResult> {
    const prompt = `Predict the outcome of the upcoming ${nextMeeting.meeting_name || 'Grand Prix'} at ${nextMeeting.circuit_short_name || nextMeeting.location} (${nextMeeting.date_start}).

## 2026 Grid
${teamGrid}

## Recent Race Results
${recentResults.length > 0 ? recentResults.join('\n') : 'Season just started — limited data available. Use pre-season testing form and team strength estimations.'}

## Circuit Characteristics
Consider the specific demands of ${nextMeeting.circuit_short_name || nextMeeting.location} and how the 2026 regulations interact:
- Active aero effectiveness at this circuit
- Energy management demands (number of heavy braking zones for MGU-K harvesting)
- Tire degradation expectations with 2026 narrower tires
- Historical team/driver performance at this venue

## Your Task

Return a JSON object:
{
  "predictedOrder": [
    {
      "position": 1,
      "driver_number": 1,
      "driver_name": "Max Verstappen",
      "team": "Red Bull",
      "confidence": 85,
      "keyFactors": ["Reason 1", "Reason 2"]
    }
    // ... all 22 drivers
  ],
  "keyBattles": ["Battle 1 description", "Battle 2", "Battle 3"],
  "strategyPredictions": ["Strategy insight 1", "Strategy insight 2", "Strategy insight 3"],
  "narrative": "A 150-200 word race preview narrative covering the key storylines, expected battles, and technical factors that will decide this race under 2026 regulations."
}

CRITICAL: Include ALL 22 drivers. Be specific with confidence scores (higher = more certain). Reference 2026-specific factors in key factors and strategy predictions.`;

    const result = await callLLMJSON<{
        predictedOrder: PredictionResult['predictedOrder'];
        keyBattles: string[];
        strategyPredictions: string[];
        narrative: string;
    }>(
        [
            { role: 'system', content: PREDICTION_SYSTEM_PROMPT },
            { role: 'user', content: prompt },
        ],
        { temperature: 0.7, maxTokens: 4096 }
    );

    return {
        nextRace: {
            name: nextMeeting.meeting_name || 'Next Race',
            circuit: nextMeeting.circuit_short_name || nextMeeting.location || 'TBD',
            date: nextMeeting.date_start || '',
        },
        predictedOrder: result.predictedOrder || [],
        keyBattles: result.keyBattles || [],
        strategyPredictions: result.strategyPredictions || [],
        narrative: result.narrative || '',
    };
}

function getFallbackPrediction(nextMeeting: import('@/lib/types').Meeting): PredictionResult {
    const teamBaseline: Record<string, number> = {
        'Red Bull': 92, 'McLaren': 90, 'Ferrari': 91, 'Mercedes': 88,
        'Aston Martin': 78, 'Williams': 75, 'Racing Bulls': 72, 'Alpine': 70,
        'Haas': 68, 'Audi': 62, 'Cadillac': 58,
    };
    const expBonus: Record<number, number> = {
        1: 10, 44: 10, 14: 8, 4: 9, 16: 8, 63: 7, 81: 6,
        55: 7, 10: 6, 77: 6, 11: 6, 23: 5, 31: 5, 27: 6,
        18: 4, 30: 3, 87: 2, 43: 2, 12: 2, 20: 2, 38: 1, 5: 2,
    };

    const allDrivers = Object.values(TEAMS_2026).flatMap(team =>
        team.drivers.map(d => ({
            driver_number: d.number,
            driver_name: d.name,
            team: team.shortName,
            score: (teamBaseline[team.shortName] || 65) + (expBonus[d.number] || 3),
        }))
    ).sort((a, b) => b.score - a.score);

    return {
        nextRace: {
            name: nextMeeting?.meeting_name || 'Next Race',
            circuit: nextMeeting?.circuit_short_name || nextMeeting?.location || 'TBD',
            date: nextMeeting?.date_start || '',
        },
        predictedOrder: allDrivers.map((d, i) => ({
            position: i + 1,
            driver_number: d.driver_number,
            driver_name: d.driver_name,
            team: d.team,
            confidence: Math.max(10, Math.min(95, Math.round(d.score - i * 2))),
            keyFactors: ['Based on team baseline strength and driver experience'],
        })),
        keyBattles: [
            'Verstappen vs Norris vs Leclerc — expected fight for victory',
            'Hamilton vs Piastri — podium battle between Ferrari and McLaren',
            'Rookie battle: Hadjar vs Antonelli vs Lindblad',
        ],
        strategyPredictions: [
            'Energy management will be critical under 2026 50/50 power split rules.',
            'Active aero straight mode optimization will differentiate the top teams.',
            'Expect 1-2 pit stops depending on narrower 2026 tire degradation.',
        ],
        narrative: `The ${nextMeeting?.meeting_name || 'next GP'} will test how teams have adapted to the 2026 regulations. Verstappen, Norris, and Leclerc are expected to lead, with energy management being the decisive factor.`,
    };
}
