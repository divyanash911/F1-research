import * as api from './src/lib/openf1-client';
import { createLogger } from './src/lib/logger';

const log = createLogger('Test-Script');

const delay = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

async function runTest() {
    log.separator('STARTING LOGGING TEST - ALL ENDPOINTS');

    const sk = { session_key: 9158 };

    const tasks = [
        () => api.getCarData(sk),
        () => api.getLocation(sk),
        () => api.getLaps(sk),
        () => api.getStints(sk),
        () => api.getWeather(sk),
        () => api.getIntervals(sk),
        () => api.getPit(sk),
        () => api.getOvertakes(sk),
        () => api.getRaceControl(sk),
        () => api.getTeamRadio(sk),
        () => api.getDrivers(sk),
        () => api.getSessions({ year: 2026 }),
        () => api.getMeetings({ year: 2026 }),
        () => api.getPositions(sk),
        () => api.getSessionResult(sk),
        () => api.getStartingGrid(sk),
        () => api.getChampionshipDrivers(sk),
        () => api.getChampionshipTeams(sk)
    ];

    for (const task of tasks) {
        await task();
        await delay(350); // Less than 3 req/sec
    }

    log.separator('LOGGING TEST COMPLETE');
    console.log('\n✅ Test script finished. Check f1-debug.log for output.');
}

runTest().catch(console.error);
