// ============================================================
// Race Replay Agent — LLM-Enhanced Race Reconstruction (2026)
// ============================================================

import * as api from '@/lib/openf1-client';
import { callLLM, isLLMConfigured } from '@/lib/llm-client';
import { getDriverInfo } from '@/lib/constants';
import { getActiveAeroMode } from '@/lib/types';
import { createLogger } from '@/lib/logger';
import type { ReplayData, ReplayFrame, ReplayEvent, Session } from '@/lib/types';

const log = createLogger('ReplayAgent');

const REPLAY_SYSTEM_PROMPT = `You are an F1 race commentator and analyst for the 2026 season.
You provide vivid, exciting commentary for key race moments — overtakes, pit stops, safety cars, and strategy calls.
Reference 2026 regulations when relevant (active aero overtake mode, energy management battles, new PU tech).
Keep each commentary piece to 1-2 sentences — punchy and broadcast-style.`;

/**
 * Reconstructs a race from telemetry data with LLM-generated commentary.
 */
export async function getReplayData(session_key: number): Promise<ReplayData> {
    const startTime = Date.now();
    log.agentStart('RaceReplay', { session_key });

    const [sessionList, drivers, positions, pits, overtakes, raceControl, laps] = await Promise.all([
        api.getSessions({ year: 2026 }),
        api.getDrivers({ session_key }),
        api.getPositions({ session_key }),
        api.getPit({ session_key }),
        api.getOvertakes({ session_key }),
        api.getRaceControl({ session_key }),
        api.getLaps({ session_key }),
    ]);

    log.info('📊 Replay data fetched', {
        sessions: sessionList.length,
        drivers: drivers.length,
        positions: positions.length,
        pits: pits.length,
        overtakes: overtakes.length,
        raceControl: raceControl.length,
        laps: laps.length,
    });

    const session = sessionList.find(s => s.session_key === session_key);
    if (!session) {
        log.warn(`Session ${session_key} not found in 2026 session list`);
        log.agentEnd('RaceReplay', Date.now() - startTime, false);
        return { session: {} as Session, drivers: [], frames: [], events: [], totalLaps: 0, duration: 0 };
    }

    // Build events timeline
    const events: ReplayEvent[] = [];

    for (const ov of overtakes) {
        const overtaker = getDriverInfo(ov.overtaking_driver_number);
        const overtaken = getDriverInfo(ov.overtaken_driver_number);
        events.push({
            type: 'overtake',
            timestamp: ov.date,
            lap: 0,
            driver_number: ov.overtaking_driver_number,
            description: `${overtaker?.shortName || ov.overtaking_driver_number} overtakes ${overtaken?.shortName || ov.overtaken_driver_number} for P${ov.position}`,
        });
    }

    for (const pit of pits) {
        const driver = getDriverInfo(pit.driver_number);
        events.push({
            type: 'pit_entry',
            timestamp: pit.date,
            lap: pit.lap_number,
            driver_number: pit.driver_number,
            description: `${driver?.shortName || pit.driver_number} pits — ${pit.stop_duration}s stop`,
            data: { stop_duration: pit.stop_duration, lane_duration: pit.lane_duration },
        });
    }

    for (const rc of raceControl) {
        if (rc.flag || rc.category === 'SafetyCar') {
            events.push({
                type: rc.category === 'SafetyCar' ? 'safety_car' : 'flag',
                timestamp: rc.date,
                lap: rc.lap_number || 0,
                driver_number: rc.driver_number || 0,
                description: rc.message,
            });
        }
    }

    events.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());

    // Generate LLM commentary for key events
    if (isLLMConfigured() && events.length > 0) {
        try {
            const keyEvents = events.filter(e => e.type === 'overtake' || e.type === 'safety_car').slice(0, 5);
            if (keyEvents.length > 0) {
                log.debug('🤖 Generating LLM commentary for key events', { count: keyEvents.length });
                const eventDescriptions = keyEvents.map((e, i) => `${i + 1}. ${e.description}`).join('\n');
                const commentary = await callLLM(
                    [
                        { role: 'system', content: REPLAY_SYSTEM_PROMPT },
                        { role: 'user', content: `Provide brief, exciting commentary for these key race moments:\n${eventDescriptions}\n\nReturn one line of commentary per event, numbered to match.` },
                    ],
                    { temperature: 0.8, maxTokens: 500 }
                );

                // Enrich events with LLM commentary
                const commentaryLines = commentary.split('\n').filter(l => l.trim());
                keyEvents.forEach((event, i) => {
                    if (commentaryLines[i]) {
                        event.description = commentaryLines[i].replace(/^\d+\.\s*/, '');
                    }
                });
                log.info('✅ LLM commentary generated', { linesProduced: commentaryLines.length });
            }
        } catch (e) {
            log.error('Replay commentary LLM call failed', {
                error: e instanceof Error ? e.message : String(e),
            });
        }
    } else if (events.length > 0) {
        log.warn('LLM not configured — skipping commentary generation');
    }

    // Build frames from position data
    const positionsByTime = new Map<string, Map<number, number>>();
    for (const pos of positions) {
        const timeKey = pos.date.substring(0, 19);
        if (!positionsByTime.has(timeKey)) positionsByTime.set(timeKey, new Map());
        positionsByTime.get(timeKey)!.set(pos.driver_number, pos.position);
    }

    const frames: ReplayFrame[] = [];
    const timeKeys = Array.from(positionsByTime.keys()).sort();
    const sampleRate = Math.max(1, Math.floor(timeKeys.length / 500));

    for (let i = 0; i < timeKeys.length; i += sampleRate) {
        const timeKey = timeKeys[i];
        const posMap = positionsByTime.get(timeKey)!;
        const frameTime = new Date(timeKey).getTime();

        let currentLap = 1;
        for (const lap of laps) {
            if (new Date(lap.date_start).getTime() <= frameTime) {
                currentLap = Math.max(currentLap, lap.lap_number);
            }
        }

        const cars = Array.from(posMap.entries()).map(([driverNum, position]) => ({
            driver_number: driverNum,
            x: 0, y: 0, z: 0,
            position,
            speed: 0,
            activeAeroMode: 'CORNER' as const,
            inPit: pits.some(p => p.driver_number === driverNum && Math.abs(new Date(p.date).getTime() - frameTime) < 30000),
        }));

        const frameEvents = events.filter(e => Math.abs(new Date(e.timestamp).getTime() - frameTime) < 5000);

        frames.push({ timestamp: timeKey, lap: currentLap, cars, events: frameEvents });
    }

    const totalLaps = laps.length > 0 ? Math.max(...laps.map(l => l.lap_number)) : 0;
    const duration = session.date_start && session.date_end
        ? (new Date(session.date_end).getTime() - new Date(session.date_start).getTime()) / 1000
        : 0;

    log.info('🏁 Replay constructed', {
        totalLaps,
        durationSec: duration,
        frameCount: frames.length,
        eventCount: events.length,
    });
    log.agentEnd('RaceReplay', Date.now() - startTime, true);

    return { session, drivers, frames, events, totalLaps, duration };
}
