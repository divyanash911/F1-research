// ============================================================
// OpenF1 API Response Types — 2026 Season
// ============================================================

export interface CarData {
    brake: number;           // 0-100
    date: string;
    driver_number: number;
    drs: number;             // 2026: maps to active aero modes
    meeting_key: number;
    n_gear: number;          // 0-8
    rpm: number;
    session_key: number;
    speed: number;           // km/h
    throttle: number;        // 0-100
}

export type ActiveAeroMode = 'CORNER' | 'STRAIGHT' | 'OVERTAKE' | 'UNKNOWN';

// Map DRS values to 2026 Active Aero modes
export function getActiveAeroMode(drsValue: number): ActiveAeroMode {
    // Based on FastF1 DRS mapping adapted for 2026 active aero
    if (drsValue === 10 || drsValue === 12 || drsValue === 14) return 'STRAIGHT';
    if (drsValue === 8) return 'CORNER';
    if (drsValue === 0 || drsValue === 1) return 'CORNER';
    if (drsValue >= 10) return 'OVERTAKE';
    return 'UNKNOWN';
}

export interface Location {
    date: string;
    driver_number: number;
    meeting_key: number;
    session_key: number;
    x: number;
    y: number;
    z: number;
}

export interface Lap {
    date_start: string;
    driver_number: number;
    duration_sector_1: number | null;
    duration_sector_2: number | null;
    duration_sector_3: number | null;
    i1_speed: number | null;
    i2_speed: number | null;
    is_pit_out_lap: boolean;
    lap_duration: number | null;
    lap_number: number;
    meeting_key: number;
    segments_sector_1: number[] | null;
    segments_sector_2: number[] | null;
    segments_sector_3: number[] | null;
    session_key: number;
    st_speed: number | null;
}

export interface Stint {
    compound: string;       // SOFT, MEDIUM, HARD, INTERMEDIATE, WET
    driver_number: number;
    lap_end: number;
    lap_start: number;
    meeting_key: number;
    session_key: number;
    stint_number: number;
    tyre_age_at_start: number;
}

export interface Weather {
    air_temperature: number;
    date: string;
    humidity: number;
    meeting_key: number;
    pressure: number;
    rainfall: number;
    session_key: number;
    track_temperature: number;
    wind_direction: number;
    wind_speed: number;
}

export interface Interval {
    date: string;
    driver_number: number;
    gap_to_leader: number | null;
    interval: number | null;
    meeting_key: number;
    session_key: number;
}

export interface Pit {
    date: string;
    driver_number: number;
    lane_duration: number;
    lap_number: number;
    meeting_key: number;
    pit_duration: number;
    session_key: number;
    stop_duration: number;
}

export interface Overtake {
    date: string;
    meeting_key: number;
    overtaken_driver_number: number;
    overtaking_driver_number: number;
    position: number;
    session_key: number;
}

export interface RaceControl {
    category: string;
    date: string;
    driver_number: number | null;
    flag: string | null;
    lap_number: number | null;
    meeting_key: number;
    message: string;
    qualifying_phase: string | null;
    scope: string | null;
    sector: number | null;
    session_key: number;
}

export interface TeamRadio {
    date: string;
    driver_number: number;
    meeting_key: number;
    recording_url: string;
    session_key: number;
}

export interface Driver {
    broadcast_name: string;
    country_code: string;
    driver_number: number;
    first_name: string;
    full_name: string;
    headshot_url: string | null;
    last_name: string;
    meeting_key: number;
    name_acronym: string;
    session_key: number;
    team_colour: string;
    team_name: string;
}

export interface Session {
    circuit_key: number;
    circuit_short_name: string;
    country_code: string;
    country_key: number;
    country_name: string;
    date_end: string;
    date_start: string;
    gmt_offset: string;
    location: string;
    meeting_key: number;
    session_key: number;
    session_name: string;
    session_type: string;
    year: number;
}

export interface Meeting {
    circuit_key: number;
    circuit_short_name: string;
    country_code: string;
    country_key: number;
    country_name: string;
    date_end?: string;
    date_start: string;
    gmt_offset: string;
    location: string;
    meeting_key: number;
    meeting_name: string;
    meeting_official_name: string;
    year: number;
}

export interface Position {
    date: string;
    driver_number: number;
    meeting_key: number;
    position: number;
    session_key: number;
}

export interface SessionResult {
    dnf: boolean;
    dns: boolean;
    dsq: boolean;
    driver_number: number;
    duration: number | null;
    gap_to_leader: number | null;
    number_of_laps: number;
    meeting_key: number;
    position: number;
    session_key: number;
}

export interface StartingGrid {
    driver_number: number;
    meeting_key: number;
    position: number;
    session_key: number;
}

export interface ChampionshipDriver {
    driver_number: number;
    meeting_key: number;
    points_current: number;
    points_start: number;
    position_current: number;
    position_start: number;
    session_key: number;
}

export interface ChampionshipTeam {
    meeting_key: number;
    points_current: number;
    points_start: number;
    position_current: number;
    position_start: number;
    session_key: number;
    team_name: string;
}

// ============================================================
// Agent Output Types
// ============================================================

export interface TelemetryReport {
    driver_number: number;
    driver_name: string;
    session_key: number;
    speedAnalysis: {
        maxSpeed: number;
        avgSpeed: number;
        speedTrace: { lap: number; speeds: number[] }[];
    };
    activeAeroAnalysis: {
        straightModePercentage: number;
        cornerModePercentage: number;
        overtakeModeActivations: number;
        avgSpeedGainStraightMode: number;
    };
    energyAnalysis: {
        estimatedDeploymentEfficiency: number;
        harvestingZones: string[];
        liftAndCoastLaps: number[];
    };
    tireAnalysis: {
        stints: {
            compound: string;
            startLap: number;
            endLap: number;
            degradationRate: number;    // sec per lap
            avgLapTime: number;
        }[];
        optimalPitWindow: number | null;
    };
    brakingAnalysis: {
        avgBrakeIntensity: number;
        heavyBrakingZones: number;
    };
    sectorAnalysis: {
        bestSector1: number | null;
        bestSector2: number | null;
        bestSector3: number | null;
        avgSector1: number | null;
        avgSector2: number | null;
        avgSector3: number | null;
    };
    overallRating: number;         // 0-100
    insights: string[];
}

export interface PredictionResult {
    nextRace: {
        name: string;
        circuit: string;
        date: string;
    };
    predictedOrder: {
        position: number;
        driver_number: number;
        driver_name: string;
        team: string;
        confidence: number;          // 0-100
        keyFactors: string[];
    }[];
    keyBattles: string[];
    strategyPredictions: string[];
    narrative: string;
}

export interface NewsItem {
    id: string;
    title: string;
    summary: string;
    category: 'team_update' | 'technical' | 'driver' | 'regulation' | 'prediction';
    impactLevel: 'low' | 'medium' | 'high';
    relatedTeams: string[];
    relatedDrivers: string[];
    timestamp: string;
}

export interface SeasonSnapshot {
    wdc: {
        position: number;
        driver_number: number;
        driver_name: string;
        team: string;
        points: number;
        wins: number;
        podiums: number;
    }[];
    wcc: {
        position: number;
        team: string;
        points: number;
        wins: number;
    }[];
    recentResults: {
        race: string;
        date: string;
        winner: string;
        podium: string[];
    }[];
}

export interface ReplayFrame {
    timestamp: string;
    lap: number;
    cars: {
        driver_number: number;
        x: number;
        y: number;
        z: number;
        position: number;
        speed: number;
        activeAeroMode: ActiveAeroMode;
        inPit: boolean;
    }[];
    events: ReplayEvent[];
}

export interface ReplayEvent {
    type: 'overtake' | 'pit_entry' | 'pit_exit' | 'flag' | 'safety_car' | 'overtake_mode';
    timestamp: string;
    lap: number;
    driver_number: number;
    description: string;
    data?: Record<string, unknown>;
}

export interface ReplayData {
    session: Session;
    drivers: Driver[];
    frames: ReplayFrame[];
    events: ReplayEvent[];
    totalLaps: number;
    duration: number;
}
