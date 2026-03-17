// ============================================================
// Telemetry Analysis Agent — LLM-Reasoned Deep Analysis (2026)
// ============================================================

import * as api from '@/lib/openf1-client';
import { callLLM, callLLMJSON, isLLMConfigured } from '@/lib/llm-client';
import { getActiveAeroMode } from '@/lib/types';
import { getDriverInfo, COMPOUND_COLORS } from '@/lib/constants';
import { createLogger } from '@/lib/logger';
import type { TelemetryReport, CarData, Lap, Stint, Weather, Pit } from '@/lib/types';

const log = createLogger('TelemetryAgent');

export interface TelemetryAnalysisInput {
    session_key: number;
    driver_number: number;
}

const TELEMETRY_SYSTEM_PROMPT = `You are an elite Formula 1 telemetry analyst and race engineer for the 2026 season.
You have deep expertise in:
- Active aerodynamics (2026 front+rear wings with Straight/Corner/Overtake modes, replacing DRS)
- Energy management (350kW MGU-K, 50/50 ICE/electric split, no MGU-H)
- Tire degradation (narrower 2026 tires, compounds: SOFT/MEDIUM/HARD/INTER/WET)
- Braking performance (enhanced regenerative braking from 350kW MGU-K)
- Power unit analysis (reduced 75 kg/h fuel flow, sustainable fuels)
- Corner-by-corner speed analysis
- Sector performance breakdown
- Race strategy optimization

When given telemetry data, you provide detailed, data-driven analysis with specific numbers and actionable insights.
You reference 2026-specific regulations when they impact performance.
Be precise, technical, and insightful — like a real F1 race engineer debriefing.`;

/**
 * Performs comprehensive LLM-reasoned telemetry analysis.
 */
export async function analyzeTelemetry(input: TelemetryAnalysisInput): Promise<TelemetryReport> {
    const startTime = Date.now();
    const { session_key, driver_number } = input;
    const driverInfo = getDriverInfo(driver_number);

    log.agentStart('TelemetryAnalysis', { session_key, driver_number, driver: driverInfo?.name });

    // Fetch all relevant data in parallel
    const [carData, laps, stints, weather, pit] = await Promise.all([
        api.getCarData({ session_key, driver_number }),
        api.getLaps({ session_key, driver_number }),
        api.getStints({ session_key, driver_number }),
        api.getWeather({ session_key }),
        api.getPit({ session_key, driver_number }),
    ]);

    log.info('📊 Telemetry data fetched', {
        carDataPoints: carData.length,
        laps: laps.length,
        stints: stints.length,
        weatherRecords: weather.length,
        pitStops: pit.length,
    });

    // Compute raw metrics (data extraction — not reasoning)
    const metrics = extractMetrics(carData, laps, stints, weather, pit);

    // Use LLM for reasoning and insight generation
    let insights: string[] = [];
    let overallRating = metrics.computedRating;

    if (isLLMConfigured()) {
        try {
            log.debug('🤖 Calling LLM for telemetry analysis');
            const llmResult = await getLLMAnalysis(
                driverInfo?.name || `Driver #${driver_number}`,
                driverInfo?.team || 'Unknown',
                metrics
            );
            insights = llmResult.insights;
            overallRating = llmResult.overallRating;
            log.info('✅ LLM analysis completed', { insightCount: insights.length, overallRating });
        } catch (e) {
            log.error('LLM analysis failed, using fallback insights', {
                error: e instanceof Error ? e.message : String(e),
            });
            insights = generateFallbackInsights(metrics, driverInfo?.name || `Driver #${driver_number}`);
        }
    } else {
        log.warn('LLM not configured — using fallback insights');
        insights = generateFallbackInsights(metrics, driverInfo?.name || `Driver #${driver_number}`);
    }

    log.agentEnd('TelemetryAnalysis', Date.now() - startTime, true);

    return {
        driver_number,
        driver_name: driverInfo?.name || `Driver #${driver_number}`,
        session_key,
        speedAnalysis: metrics.speed,
        activeAeroAnalysis: metrics.activeAero,
        energyAnalysis: metrics.energy,
        tireAnalysis: metrics.tire,
        brakingAnalysis: metrics.braking,
        sectorAnalysis: metrics.sector,
        overallRating,
        insights,
    };
}

// ============================================================
// Raw Metrics Extraction (data processing, not reasoning)
// ============================================================
interface RawMetrics {
    speed: TelemetryReport['speedAnalysis'];
    activeAero: TelemetryReport['activeAeroAnalysis'];
    energy: TelemetryReport['energyAnalysis'];
    tire: TelemetryReport['tireAnalysis'];
    braking: TelemetryReport['brakingAnalysis'];
    sector: TelemetryReport['sectorAnalysis'];
    computedRating: number;
    weatherSummary: { avgTrackTemp: number; avgAirTemp: number; hadRain: boolean; avgWind: number };
    pitSummary: { numStops: number; avgStopDuration: number; fastestStop: number };
    lapTimeSummary: { fastest: number; average: number; total: number };
}

function extractMetrics(carData: CarData[], laps: Lap[], stints: Stint[], weather: Weather[], pit: Pit[]): RawMetrics {
    // Speed analysis
    const speeds = carData.map(d => d.speed).filter(s => s > 0);
    const maxSpeed = speeds.length > 0 ? Math.max(...speeds) : 0;
    const avgSpeed = speeds.length > 0 ? Math.round((speeds.reduce((a, b) => a + b, 0) / speeds.length) * 10) / 10 : 0;
    const speedTrace = laps.slice(0, 20).map(lap => ({
        lap: lap.lap_number,
        speeds: carData
            .filter(d => {
                const ct = new Date(d.date).getTime();
                const ls = new Date(lap.date_start).getTime();
                return ct >= ls && ct < ls + (lap.lap_duration || 120) * 1000;
            })
            .map(d => d.speed).filter(s => s > 0).slice(0, 50),
    }));

    // Active aero analysis
    const modes = carData.map(d => getActiveAeroMode(d.drs));
    const total = modes.length || 1;
    const straightCount = modes.filter(m => m === 'STRAIGHT').length;
    const cornerCount = modes.filter(m => m === 'CORNER').length;
    const overtakeCount = modes.filter(m => m === 'OVERTAKE').length;
    const straightSpeeds = carData.filter(d => getActiveAeroMode(d.drs) === 'STRAIGHT').map(d => d.speed);
    const cornerSpeeds = carData.filter(d => getActiveAeroMode(d.drs) === 'CORNER').map(d => d.speed);
    const avgStraight = straightSpeeds.length > 0 ? straightSpeeds.reduce((a, b) => a + b, 0) / straightSpeeds.length : 0;
    const avgCorner = cornerSpeeds.length > 0 ? cornerSpeeds.reduce((a, b) => a + b, 0) / cornerSpeeds.length : 0;

    // Energy management
    const liftAndCoastSamples = carData.filter(d => d.throttle < 50 && d.speed > 200 && d.brake === 0);
    const throttleValues = carData.map(d => d.throttle).filter(t => t > 0);
    const avgThrottle = throttleValues.length > 0 ? throttleValues.reduce((a, b) => a + b, 0) / throttleValues.length : 0;
    const heavyBrakingSamples = carData.filter(d => d.brake > 50 && d.speed > 100);
    const harvestingZones: string[] = [];
    if (heavyBrakingSamples.length > 0) harvestingZones.push('Heavy braking zones (MGU-K regen)');
    if (liftAndCoastSamples.length / (carData.length || 1) > 0.05) harvestingZones.push('Lift-and-coast phases');
    const liftAndCoastLaps: number[] = [];
    for (const lap of laps) {
        const ls = new Date(lap.date_start).getTime();
        const le = ls + (lap.lap_duration || 120) * 1000;
        const c = liftAndCoastSamples.filter(d => { const t = new Date(d.date).getTime(); return t >= ls && t < le; });
        if (c.length > 3) liftAndCoastLaps.push(lap.lap_number);
    }

    // Tire degradation
    const analyzedStints = stints.map(stint => {
        const stintLaps = laps.filter(l => l.lap_number >= stint.lap_start && l.lap_number <= stint.lap_end && l.lap_duration && l.lap_duration > 0 && !l.is_pit_out_lap);
        const lapTimes = stintLaps.map(l => l.lap_duration!);
        const avgLapTime = lapTimes.length > 0 ? lapTimes.reduce((a, b) => a + b, 0) / lapTimes.length : 0;
        let degradationRate = 0;
        if (lapTimes.length >= 3) {
            const n = lapTimes.length;
            const sumX = lapTimes.reduce((_, __, i) => _ + i, 0);
            const sumY = lapTimes.reduce((a, b) => a + b, 0);
            const sumXY = lapTimes.reduce((sum, y, i) => sum + i * y, 0);
            const sumX2 = lapTimes.reduce((sum, _, i) => sum + i * i, 0);
            degradationRate = (n * sumXY - sumX * sumY) / (n * sumX2 - sumX * sumX);
        }
        return { compound: stint.compound, startLap: stint.lap_start, endLap: stint.lap_end, degradationRate: Math.round(degradationRate * 1000) / 1000, avgLapTime: Math.round(avgLapTime * 1000) / 1000 };
    });

    // Braking
    const brakeData = carData.filter(d => d.brake > 0);
    const avgBrakeIntensity = brakeData.length > 0 ? Math.round(brakeData.reduce((a, b) => a + b.brake, 0) / brakeData.length) : 0;

    // Sectors
    const validLaps = laps.filter(l => !l.is_pit_out_lap && l.lap_duration && l.lap_duration > 0);
    const s1 = validLaps.map(l => l.duration_sector_1).filter((t): t is number => t !== null && t > 0);
    const s2 = validLaps.map(l => l.duration_sector_2).filter((t): t is number => t !== null && t > 0);
    const s3 = validLaps.map(l => l.duration_sector_3).filter((t): t is number => t !== null && t > 0);
    const best = (a: number[]) => a.length > 0 ? Math.round(Math.min(...a) * 1000) / 1000 : null;
    const avg = (a: number[]) => a.length > 0 ? Math.round((a.reduce((x, y) => x + y, 0) / a.length) * 1000) / 1000 : null;

    // Weather summary
    const avgTrackTemp = weather.length > 0 ? Math.round(weather.reduce((a, w) => a + w.track_temperature, 0) / weather.length * 10) / 10 : 0;
    const avgAirTemp = weather.length > 0 ? Math.round(weather.reduce((a, w) => a + w.air_temperature, 0) / weather.length * 10) / 10 : 0;
    const hadRain = weather.some(w => w.rainfall > 0);
    const avgWind = weather.length > 0 ? Math.round(weather.reduce((a, w) => a + w.wind_speed, 0) / weather.length * 10) / 10 : 0;

    // Pit summary
    const numStops = pit.length;
    const avgStopDuration = pit.length > 0 ? Math.round(pit.reduce((a, p) => a + p.stop_duration, 0) / pit.length * 10) / 10 : 0;
    const fastestStop = pit.length > 0 ? Math.min(...pit.map(p => p.stop_duration)) : 0;

    // Lap time summary
    const lapDurations = validLaps.map(l => l.lap_duration!);
    const fastestLap = lapDurations.length > 0 ? Math.min(...lapDurations) : 0;
    const avgLap = lapDurations.length > 0 ? lapDurations.reduce((a, b) => a + b, 0) / lapDurations.length : 0;

    // Computed rating
    let rating = 50;
    if (maxSpeed > 320) rating += 10;
    if (maxSpeed > 330) rating += 5;
    const avgDeg = analyzedStints.length > 0 ? analyzedStints.reduce((a, s) => a + s.degradationRate, 0) / analyzedStints.length : 0;
    if (avgDeg < 0.1) rating += 15; else if (avgDeg < 0.2) rating += 10;
    if (s1.length > 0 && best(s1) && avg(s1)) { const v = avg(s1)! - best(s1)!; if (v < 0.5) rating += 5; if (v < 0.3) rating += 5; }

    return {
        speed: { maxSpeed, avgSpeed, speedTrace },
        activeAero: { straightModePercentage: Math.round((straightCount / total) * 100), cornerModePercentage: Math.round((cornerCount / total) * 100), overtakeModeActivations: overtakeCount, avgSpeedGainStraightMode: Math.round((avgStraight - avgCorner) * 10) / 10 },
        energy: { estimatedDeploymentEfficiency: Math.min(100, Math.round(avgThrottle * 1.2)), harvestingZones, liftAndCoastLaps: liftAndCoastLaps.slice(0, 10) },
        tire: { stints: analyzedStints, optimalPitWindow: analyzedStints.length > 0 && analyzedStints[0].degradationRate > 0.05 ? analyzedStints[0].startLap + Math.min(Math.round(1 / analyzedStints[0].degradationRate), 30) : null },
        braking: { avgBrakeIntensity, heavyBrakingZones: Math.min(heavyBrakingSamples.length, 20) },
        sector: { bestSector1: best(s1), bestSector2: best(s2), bestSector3: best(s3), avgSector1: avg(s1), avgSector2: avg(s2), avgSector3: avg(s3) },
        computedRating: Math.max(0, Math.min(100, Math.round(rating))),
        weatherSummary: { avgTrackTemp, avgAirTemp, hadRain, avgWind },
        pitSummary: { numStops, avgStopDuration, fastestStop },
        lapTimeSummary: { fastest: Math.round(fastestLap * 1000) / 1000, average: Math.round(avgLap * 1000) / 1000, total: validLaps.length },
    };
}

// ============================================================
// LLM-Powered Analysis & Insight Generation
// ============================================================
async function getLLMAnalysis(
    driverName: string,
    teamName: string,
    metrics: RawMetrics
): Promise<{ insights: string[]; overallRating: number }> {
    const prompt = `Analyze the following telemetry data for ${driverName} (${teamName}) in this 2026 F1 session.

## Raw Telemetry Metrics

**Speed**: Max ${metrics.speed.maxSpeed} km/h, Avg ${metrics.speed.avgSpeed} km/h
**Active Aero**: Straight mode ${metrics.activeAero.straightModePercentage}%, Corner mode ${metrics.activeAero.cornerModePercentage}%, Overtake mode activations: ${metrics.activeAero.overtakeModeActivations}, Speed gain in straight mode: ${metrics.activeAero.avgSpeedGainStraightMode} km/h
**Energy Management**: Deployment efficiency: ${metrics.energy.estimatedDeploymentEfficiency}%, Harvesting zones: ${metrics.energy.harvestingZones.join(', ') || 'None detected'}, Lift-and-coast on ${metrics.energy.liftAndCoastLaps.length} laps
**Tire Degradation**: ${metrics.tire.stints.map(s => `${s.compound}: laps ${s.startLap}-${s.endLap}, deg rate ${s.degradationRate}s/lap, avg ${s.avgLapTime}s`).join('; ') || 'No stint data'}
**Braking**: Avg intensity ${metrics.braking.avgBrakeIntensity}%, Heavy braking zones: ${metrics.braking.heavyBrakingZones}
**Sectors**: Best S1: ${metrics.sector.bestSector1}s, S2: ${metrics.sector.bestSector2}s, S3: ${metrics.sector.bestSector3}s | Avg S1: ${metrics.sector.avgSector1}s, S2: ${metrics.sector.avgSector2}s, S3: ${metrics.sector.avgSector3}s
**Weather**: Track ${metrics.weatherSummary.avgTrackTemp}°C, Air ${metrics.weatherSummary.avgAirTemp}°C, Rain: ${metrics.weatherSummary.hadRain ? 'Yes' : 'No'}, Wind: ${metrics.weatherSummary.avgWind} m/s
**Pit Stops**: ${metrics.pitSummary.numStops} stops, Fastest: ${metrics.pitSummary.fastestStop}s, Avg: ${metrics.pitSummary.avgStopDuration}s
**Lap Times**: Fastest: ${metrics.lapTimeSummary.fastest}s, Average: ${metrics.lapTimeSummary.average}s, Total laps: ${metrics.lapTimeSummary.total}

## Your Task

Provide your expert analysis as a JSON object with exactly these fields:
{
  "insights": ["insight1", "insight2", ...],  // 5-8 detailed, technical insights referencing 2026 regulations
  "overallRating": 75  // 0-100 performance rating based on the data
}

Each insight should:
1. Reference specific data points from the metrics
2. Explain the significance in context of 2026 regulations (active aero, energy management, new PU)
3. Compare against expected norms where applicable
4. Provide actionable recommendations where relevant`;

    return callLLMJSON<{ insights: string[]; overallRating: number }>(
        [
            { role: 'system', content: TELEMETRY_SYSTEM_PROMPT },
            { role: 'user', content: prompt },
        ],
        { temperature: 0.6, maxTokens: 2048 }
    );
}

// ============================================================
// Fallback insights when LLM is not available
// ============================================================
function generateFallbackInsights(metrics: RawMetrics, driverName: string): string[] {
    const insights: string[] = [];
    if (metrics.speed.maxSpeed > 330) insights.push(`${driverName} reached ${metrics.speed.maxSpeed} km/h — strong active aero straight mode performance.`);
    if (metrics.activeAero.overtakeModeActivations > 5) insights.push(`${metrics.activeAero.overtakeModeActivations} overtake mode activations — aggressive racing.`);
    if (metrics.energy.estimatedDeploymentEfficiency > 80) insights.push(`Efficient energy deployment at ${metrics.energy.estimatedDeploymentEfficiency}%.`);
    if (metrics.tire.stints.length > 0) {
        const s = metrics.tire.stints[0];
        insights.push(`${s.compound} tires: ${s.degradationRate}s/lap degradation rate.`);
    }
    if (insights.length === 0) insights.push(`${driverName} completed the session with consistent metrics.`);
    return insights;
}
