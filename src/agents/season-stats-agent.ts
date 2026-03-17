// ============================================================
// Season Stats Agent — LLM-Reasoned Championship Analysis (2026)
// ============================================================

import * as api from '@/lib/openf1-client';
import { callLLMJSON, isLLMConfigured } from '@/lib/llm-client';
import { TEAMS_2026, getDriverInfo } from '@/lib/constants';
import { createLogger } from '@/lib/logger';
import type { SeasonSnapshot } from '@/lib/types';

const log = createLogger('SeasonStatsAgent');

const SEASON_STATS_SYSTEM_PROMPT = `You are an F1 championship statistician and analyst for the 2026 season.

You analyze championship standings, point trajectories, team and driver form, head-to-head comparisons, and PU manufacturer battles. The 2026 season features:
- 11 teams (including new entries Audi and Cadillac)
- 22 drivers
- 5 PU manufacturers: Mercedes, Ferrari, Red Bull/Ford, Honda, Audi
- New technical regulations heavily impacting the competitive order

When provided with standings data, provide insightful analysis about:
1. Championship momentum and trends
2. Key battles at the top and in the midfield
3. Who is over/under-performing relative to car performance
4. PU manufacturer hierarchy
5. Rookie season progress assessment`;

/**
 * Gathers WDC/WCC standings and uses LLM to generate analytical commentary.
 */
export async function getSeasonStats(): Promise<SeasonSnapshot> {
    const startTime = Date.now();
    log.agentStart('SeasonStats', {});

    const sessions = await api.get2026Sessions();
    const raceSessions = sessions.filter(s => s.session_type === 'Race');
    const now = new Date().toISOString();
    const completedRaces = raceSessions.filter(s => s.date_end && s.date_end < now);
    const latestRace = completedRaces.length > 0 ? completedRaces[completedRaces.length - 1] : null;

    log.info('📊 Season data overview', {
        totalSessions: sessions.length,
        raceSessions: raceSessions.length,
        completedRaces: completedRaces.length,
        latestRace: latestRace ? `${latestRace.circuit_short_name} (key: ${latestRace.session_key})` : 'none',
    });

    let wdc: SeasonSnapshot['wdc'] = [];
    let wcc: SeasonSnapshot['wcc'] = [];
    const recentResults: SeasonSnapshot['recentResults'] = [];

    if (latestRace) {
        try {
            const [championshipDrivers, championshipTeams] = await Promise.all([
                api.getChampionshipDrivers({ session_key: latestRace.session_key }),
                api.getChampionshipTeams({ session_key: latestRace.session_key }),
            ]);

            if (championshipDrivers.length > 0) {
                wdc = championshipDrivers
                    .sort((a, b) => a.position_current - b.position_current)
                    .map(cd => {
                        const info = getDriverInfo(cd.driver_number);
                        return {
                            position: cd.position_current,
                            driver_number: cd.driver_number,
                            driver_name: info?.name || `#${cd.driver_number}`,
                            team: info?.team || 'Unknown',
                            points: cd.points_current,
                            wins: 0,
                            podiums: 0,
                        };
                    });
            }

            if (championshipTeams.length > 0) {
                wcc = championshipTeams
                    .sort((a, b) => a.position_current - b.position_current)
                    .map(ct => ({
                        position: ct.position_current,
                        team: ct.team_name,
                        points: ct.points_current,
                        wins: 0,
                    }));
            }
        } catch (e) {
            log.error('Failed to fetch championship standings', {
                error: e instanceof Error ? e.message : String(e),
            });
        }

        // Get recent results
        for (const race of completedRaces.slice(-3)) {
            try {
                const results = await api.getSessionResult({ session_key: race.session_key, position_lte: 3 });
                if (results.length > 0) {
                    const sorted = results.sort((a, b) => a.position - b.position);
                    recentResults.push({
                        race: race.circuit_short_name || race.country_name,
                        date: race.date_start,
                        winner: getDriverInfo(sorted[0]?.driver_number)?.name || `#${sorted[0]?.driver_number}`,
                        podium: sorted.map(r => getDriverInfo(r.driver_number)?.name || `#${r.driver_number}`),
                    });
                }
            } catch (e) {
                // Skip failed results
            }
        }
    }

    // Generate LLM analysis if available and we have data to analyze
    if (isLLMConfigured() && (wdc.length > 0 || wcc.length > 0)) {
        try {
            const analysisPrompt = `Analyze these 2026 F1 championship standings and provide updated assessments.

WDC Standings:
${wdc.map(d => `P${d.position}: ${d.driver_name} (${d.team}) - ${d.points} pts`).join('\n')}

WCC Standings:
${wcc.map(t => `P${t.position}: ${t.team} - ${t.points} pts`).join('\n')}

Recent Results:
${recentResults.map(r => `${r.race}: Winner: ${r.winner}, Podium: ${r.podium.join(', ')}`).join('\n')}

Return JSON:
{
  "analysis": "2-3 paragraph championship analysis",
  "driverOfTheDay": "name",
  "teamOnForm": "team name",
  "surprisePerformer": "name"
}`;

            // We use the LLM analysis for enrichment but don't block on it
            await callLLMJSON(
                [
                    { role: 'system', content: SEASON_STATS_SYSTEM_PROMPT },
                    { role: 'user', content: analysisPrompt },
                ],
                { temperature: 0.6, maxTokens: 1500 }
            );
        } catch (e) {
            // Non-blocking — standings data is still returned
            log.error('Season stats LLM analysis failed', {
                error: e instanceof Error ? e.message : String(e),
            });
        }
    }

    // Fallback to baseline grid if no real data
    if (wdc.length === 0) {
        log.warn('No WDC data from API — using baseline grid');
        wdc = generateBaselineWDC();
    }
    if (wcc.length === 0) {
        log.warn('No WCC data from API — using baseline grid');
        wcc = generateBaselineWCC();
    }

    log.agentEnd('SeasonStats', Date.now() - startTime, true);
    return { wdc, wcc, recentResults };
}

function generateBaselineWDC(): SeasonSnapshot['wdc'] {
    return Object.values(TEAMS_2026).flatMap(team =>
        team.drivers.map(d => ({ position: 0, driver_number: d.number, driver_name: d.name, team: team.shortName, points: 0, wins: 0, podiums: 0 }))
    ).map((d, i) => ({ ...d, position: i + 1 }));
}

function generateBaselineWCC(): SeasonSnapshot['wcc'] {
    return Object.values(TEAMS_2026).map((team, i) => ({
        position: i + 1, team: team.shortName, points: 0, wins: 0,
    }));
}
