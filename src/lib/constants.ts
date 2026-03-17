// ============================================================
// 2026 F1 Season Constants — Teams, Drivers, Colors
// ============================================================

export interface TeamInfo {
    name: string;
    shortName: string;
    color: string;
    secondaryColor: string;
    powerUnit: string;
    drivers: { number: number; name: string; shortName: string; country: string }[];
}

export const TEAMS_2026: Record<string, TeamInfo> = {
    red_bull: {
        name: 'Oracle Red Bull Racing',
        shortName: 'Red Bull',
        color: '#3671C6',
        secondaryColor: '#1B2A4A',
        powerUnit: 'Red Bull/Ford',
        drivers: [
            { number: 1, name: 'Max Verstappen', shortName: 'VER', country: 'NED' },
            { number: 20, name: 'Isack Hadjar', shortName: 'HAD', country: 'FRA' },
        ],
    },
    mclaren: {
        name: 'McLaren F1 Team',
        shortName: 'McLaren',
        color: '#FF8000',
        secondaryColor: '#47483D',
        powerUnit: 'Mercedes',
        drivers: [
            { number: 4, name: 'Lando Norris', shortName: 'NOR', country: 'GBR' },
            { number: 81, name: 'Oscar Piastri', shortName: 'PIA', country: 'AUS' },
        ],
    },
    ferrari: {
        name: 'Scuderia Ferrari',
        shortName: 'Ferrari',
        color: '#E8002D',
        secondaryColor: '#FFCD00',
        powerUnit: 'Ferrari',
        drivers: [
            { number: 16, name: 'Charles Leclerc', shortName: 'LEC', country: 'MON' },
            { number: 44, name: 'Lewis Hamilton', shortName: 'HAM', country: 'GBR' },
        ],
    },
    mercedes: {
        name: 'Mercedes-AMG Petronas F1 Team',
        shortName: 'Mercedes',
        color: '#27F4D2',
        secondaryColor: '#00A19C',
        powerUnit: 'Mercedes',
        drivers: [
            { number: 63, name: 'George Russell', shortName: 'RUS', country: 'GBR' },
            { number: 12, name: 'Kimi Antonelli', shortName: 'ANT', country: 'ITA' },
        ],
    },
    aston_martin: {
        name: 'Aston Martin Aramco F1 Team',
        shortName: 'Aston Martin',
        color: '#229971',
        secondaryColor: '#0A3A2A',
        powerUnit: 'Honda',
        drivers: [
            { number: 14, name: 'Fernando Alonso', shortName: 'ALO', country: 'ESP' },
            { number: 18, name: 'Lance Stroll', shortName: 'STR', country: 'CAN' },
        ],
    },
    williams: {
        name: 'Williams Racing',
        shortName: 'Williams',
        color: '#64C4FF',
        secondaryColor: '#00274D',
        powerUnit: 'Mercedes',
        drivers: [
            { number: 23, name: 'Alex Albon', shortName: 'ALB', country: 'THA' },
            { number: 55, name: 'Carlos Sainz', shortName: 'SAI', country: 'ESP' },
        ],
    },
    racing_bulls: {
        name: 'Visa Cash App Racing Bulls',
        shortName: 'Racing Bulls',
        color: '#6692FF',
        secondaryColor: '#1A2B4D',
        powerUnit: 'Red Bull/Ford',
        drivers: [
            { number: 30, name: 'Liam Lawson', shortName: 'LAW', country: 'NZL' },
            { number: 38, name: 'Arvid Lindblad', shortName: 'LIN', country: 'GBR' },
        ],
    },
    alpine: {
        name: 'BWT Alpine F1 Team',
        shortName: 'Alpine',
        color: '#FF87BC',
        secondaryColor: '#2E2244',
        powerUnit: 'Mercedes',
        drivers: [
            { number: 10, name: 'Pierre Gasly', shortName: 'GAS', country: 'FRA' },
            { number: 43, name: 'Franco Colapinto', shortName: 'COL', country: 'ARG' },
        ],
    },
    haas: {
        name: 'MoneyGram Haas F1 Team',
        shortName: 'Haas',
        color: '#B6BABD',
        secondaryColor: '#1A1A1A',
        powerUnit: 'Ferrari',
        drivers: [
            { number: 87, name: 'Oliver Bearman', shortName: 'BEA', country: 'GBR' },
            { number: 31, name: 'Esteban Ocon', shortName: 'OCO', country: 'FRA' },
        ],
    },
    audi: {
        name: 'Audi F1 Team',
        shortName: 'Audi',
        color: '#FF0000',
        secondaryColor: '#000000',
        powerUnit: 'Audi',
        drivers: [
            { number: 27, name: 'Nico Hulkenberg', shortName: 'HUL', country: 'GER' },
            { number: 5, name: 'Gabriel Bortoleto', shortName: 'BOR', country: 'BRA' },
        ],
    },
    cadillac: {
        name: 'Cadillac F1 Team',
        shortName: 'Cadillac',
        color: '#CCAA00',
        secondaryColor: '#1C1C1C',
        powerUnit: 'Ferrari',
        drivers: [
            { number: 77, name: 'Valtteri Bottas', shortName: 'BOT', country: 'FIN' },
            { number: 11, name: 'Sergio Perez', shortName: 'PER', country: 'MEX' },
        ],
    },
};

// Map driver number → team key
export function getTeamForDriver(driverNumber: number): TeamInfo | undefined {
    for (const team of Object.values(TEAMS_2026)) {
        if (team.drivers.some(d => d.number === driverNumber)) {
            return team;
        }
    }
    return undefined;
}

// Map driver number → driver info
export function getDriverInfo(driverNumber: number) {
    for (const team of Object.values(TEAMS_2026)) {
        const driver = team.drivers.find(d => d.number === driverNumber);
        if (driver) return { ...driver, team: team.shortName, teamColor: team.color };
    }
    return undefined;
}

// All driver numbers
export const ALL_DRIVER_NUMBERS = Object.values(TEAMS_2026).flatMap(t => t.drivers.map(d => d.number));

// 2026 Regulation Constants
export const REGULATIONS_2026 = {
    MGU_K_POWER_KW: 350,
    ICE_POWER_SPLIT: 0.5,
    ELECTRIC_POWER_SPLIT: 0.5,
    FUEL_FLOW_MAX_KG_H: 75,
    MIN_WEIGHT_KG: 768,
    MAX_WHEELBASE_MM: 3400,
    MAX_WIDTH_MM: 1900,
    ACTIVE_AERO_MODES: ['CORNER', 'STRAIGHT', 'OVERTAKE'] as const,
    TIRE_COMPOUNDS: ['SOFT', 'MEDIUM', 'HARD', 'INTERMEDIATE', 'WET'] as const,
};

// Compound colors
export const COMPOUND_COLORS: Record<string, string> = {
    SOFT: '#FF3333',
    MEDIUM: '#FFD700',
    HARD: '#FFFFFF',
    INTERMEDIATE: '#39B54A',
    WET: '#0070C0',
};
