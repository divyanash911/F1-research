// ============================================================
// OpenF1 API Client — All 18 Endpoints with Caching & Debug Logging
// ============================================================

import { apiCache } from './cache';
import { createLogger } from './logger';
import type {
    CarData, Location, Lap, Stint, Weather, Interval, Pit,
    Overtake, RaceControl, TeamRadio, Driver, Session, Meeting,
    Position, SessionResult, StartingGrid, ChampionshipDriver, ChampionshipTeam
} from './types';

const log = createLogger('OpenF1-Client');
const BASE_URL = 'https://api.openf1.org/v1';

type QueryParams = Record<string, string | number | boolean | undefined>;

async function fetchAPI<T>(endpoint: string, params: QueryParams = {}, cacheTTL = 300): Promise<T[]> {
    // Build query string
    const searchParams = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
        if (value !== undefined) searchParams.append(key, String(value));
    }
    const qs = searchParams.toString();
    const url = qs ? `${BASE_URL}/${endpoint}?${qs}` : `${BASE_URL}/${endpoint}`;

    // Check cache
    const cached = apiCache.get<T[]>(url);
    if (cached) {
        log.debug(`Cache HIT for ${endpoint}`, { url, resultCount: cached.length });
        return cached;
    }
    log.debug(`Cache MISS for ${endpoint} — fetching from API`, { url });

    const startTime = Date.now();

    try {
        const response = await fetch(url, {
            headers: { 'Accept': 'application/json' },
            next: { revalidate: cacheTTL },
        });

        const durationMs = Date.now() - startTime;

        if (!response.ok) {
            // Read the response body for diagnostic info
            let responseBody = '';
            try {
                responseBody = await response.text();
            } catch {
                responseBody = '[could not read response body]';
            }

            // OpenF1 uses 404 "No results found." when a valid query simply returns no data.
            // We should not treat this as an actual error.
            if (response.status === 404 && responseBody.includes('No results found.')) {
                log.httpRequest('GET', url, 204, durationMs); // Log as pseudo-success (No Content)
                log.debug(`No results found for /${endpoint}`, { url, params });
                // We could optionally cache this empty result too, but returning [] directly is fine
                return [];
            }

            log.httpRequest('GET', url, response.status, durationMs, {
                endpoint,
                params,
                responseBody: responseBody.slice(0, 500),
                statusText: response.statusText,
            });

            log.error(`API returned ${response.status} for /${endpoint}`, {
                url,
                status: response.status,
                statusText: response.statusText,
                body: responseBody.slice(0, 500),
                hint: response.status === 404
                    ? 'Endpoint not found — check the endpoint name against https://openf1.org/docs'
                    : response.status === 429
                        ? 'Rate limited — add delays between requests'
                        : response.status >= 500
                            ? 'OpenF1 server error — may be temporary, retry later'
                            : 'Unexpected error',
            });

            return [];
        }

        const data = await response.json() as T[];
        apiCache.set(url, data, cacheTTL);

        log.httpRequest('GET', url, response.status, durationMs);
        log.dataResult(endpoint, data.length, params as Record<string, unknown>);

        return data;
    } catch (error) {
        const durationMs = Date.now() - startTime;
        log.error(`Network/fetch error for /${endpoint}`, {
            url,
            durationMs,
            error: error instanceof Error ? {
                message: error.message,
                name: error.name,
                stack: error.stack?.split('\n').slice(0, 5).join('\n'),
            } : String(error),
            hint: 'Check network connectivity and DNS resolution',
        });
        return [];
    }
}

// ============================================================
// Endpoint Methods
// ============================================================

export async function getCarData(params: {
    session_key: number;
    driver_number?: number;
    speed_gte?: number;
    date_gt?: string;
    date_lt?: string;
}): Promise<CarData[]> {
    const query: QueryParams = {
        session_key: params.session_key,
        driver_number: params.driver_number,
    };
    if (params.speed_gte) query['speed>='] = params.speed_gte;
    if (params.date_gt) query['date>'] = params.date_gt;
    if (params.date_lt) query['date<'] = params.date_lt;
    return fetchAPI<CarData>('car_data', query, 600);
}

export async function getLocation(params: {
    session_key: number;
    driver_number?: number;
    date_gt?: string;
    date_lt?: string;
}): Promise<Location[]> {
    const query: QueryParams = {
        session_key: params.session_key,
        driver_number: params.driver_number,
    };
    if (params.date_gt) query['date>'] = params.date_gt;
    if (params.date_lt) query['date<'] = params.date_lt;
    return fetchAPI<Location>('location', query, 600);
}

export async function getLaps(params: {
    session_key: number;
    driver_number?: number;
    lap_number?: number;
}): Promise<Lap[]> {
    return fetchAPI<Lap>('laps', params, 600);
}

export async function getStints(params: {
    session_key: number;
    driver_number?: number;
}): Promise<Stint[]> {
    return fetchAPI<Stint>('stints', params, 600);
}

export async function getWeather(params: {
    meeting_key?: number;
    session_key?: number;
}): Promise<Weather[]> {
    return fetchAPI<Weather>('weather', params, 120);
}

export async function getIntervals(params: {
    session_key: number;
    driver_number?: number;
}): Promise<Interval[]> {
    return fetchAPI<Interval>('intervals', params, 300);
}

export async function getPit(params: {
    session_key: number;
    driver_number?: number;
}): Promise<Pit[]> {
    return fetchAPI<Pit>('pit', params, 600);
}

export async function getOvertakes(params: {
    session_key: number;
    overtaking_driver_number?: number;
}): Promise<Overtake[]> {
    return fetchAPI<Overtake>('overtakes', params, 600);
}

export async function getRaceControl(params: {
    session_key: number;
    flag?: string;
    driver_number?: number;
}): Promise<RaceControl[]> {
    return fetchAPI<RaceControl>('race_control', params, 300);
}

export async function getTeamRadio(params: {
    session_key: number;
    driver_number?: number;
}): Promise<TeamRadio[]> {
    return fetchAPI<TeamRadio>('team_radio', params, 600);
}

export async function getDrivers(params: {
    session_key?: number;
    meeting_key?: number;
    driver_number?: number;
}): Promise<Driver[]> {
    return fetchAPI<Driver>('drivers', params, 3600);
}

export async function getSessions(params: {
    year?: number;
    meeting_key?: number;
    session_name?: string;
    session_type?: string;
    country_name?: string;
}): Promise<Session[]> {
    return fetchAPI<Session>('sessions', params, 3600);
}

export async function getMeetings(params: {
    year?: number;
    meeting_key?: number;
    country_name?: string;
}): Promise<Meeting[]> {
    return fetchAPI<Meeting>('meetings', params, 3600);
}

export async function getPositions(params: {
    session_key: number;
    driver_number?: number;
}): Promise<Position[]> {
    return fetchAPI<Position>('position', params, 300);
}

export async function getSessionResult(params: {
    session_key: number;
    position_lte?: number;
}): Promise<SessionResult[]> {
    const query: QueryParams = { session_key: params.session_key };
    if (params.position_lte) query['position<='] = params.position_lte;
    return fetchAPI<SessionResult>('session_result', query, 600);
}

export async function getStartingGrid(params: {
    session_key: number;
}): Promise<StartingGrid[]> {
    return fetchAPI<StartingGrid>('starting_grid', params, 3600);
}

export async function getChampionshipDrivers(params: {
    session_key: number;
    driver_number?: number;
}): Promise<ChampionshipDriver[]> {
    return fetchAPI<ChampionshipDriver>('championship_drivers', params, 3600);
}

export async function getChampionshipTeams(params: {
    session_key: number;
}): Promise<ChampionshipTeam[]> {
    return fetchAPI<ChampionshipTeam>('championship_teams', params, 3600);
}

// ============================================================
// Convenience Methods
// ============================================================

/** Get the most recent race session for 2026 */
export async function getLatestRaceSession(): Promise<Session | null> {
    log.info('🏁 Looking up latest 2026 race session');
    const sessions = await getSessions({ year: 2026 });
    const raceSessions = sessions.filter(s => s.session_type === 'Race');
    log.debug(`Found ${raceSessions.length} race sessions out of ${sessions.length} total`);

    if (raceSessions.length === 0) {
        log.warn('No race sessions found for 2026');
        return null;
    }

    const now = new Date().toISOString();
    const completed = raceSessions.filter(s => s.date_end < now);
    const result = completed.length > 0 ? completed[completed.length - 1] : raceSessions[0];
    log.info(`Latest race session: ${result.session_name} (key: ${result.session_key})`, {
        circuit: result.circuit_short_name,
        date: result.date_start,
    });
    return result;
}

/** Get all 2026 meetings */
export async function get2026Calendar(): Promise<Meeting[]> {
    log.info('📅 Fetching 2026 calendar');
    const meetings = await getMeetings({ year: 2026 });
    log.debug(`Calendar: ${meetings.length} meetings found`);
    return meetings;
}

/** Get all 2026 sessions */
export async function get2026Sessions(): Promise<Session[]> {
    log.info('📋 Fetching all 2026 sessions');
    const sessions = await getSessions({ year: 2026 });
    log.debug(`Sessions: ${sessions.length} sessions found`);
    return sessions;
}
