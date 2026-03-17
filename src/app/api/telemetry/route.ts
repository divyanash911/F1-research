import { NextResponse } from 'next/server';
import { orchestrate } from '@/agents/orchestrator';
import { createLogger } from '@/lib/logger';

const log = createLogger('API-Telemetry');

export async function GET(request: Request) {
    const { searchParams } = new URL(request.url);
    const session_key = searchParams.get('session_key');
    const driver_number = searchParams.get('driver_number');

    log.info(`GET /api/telemetry`, { session_key, driver_number });

    if (!session_key || !driver_number) {
        log.warn('Missing session_key or driver_number');
        return NextResponse.json({ error: 'session_key and driver_number required' }, { status: 400 });
    }
    const startTime = Date.now();
    try {
        const result = await orchestrate({
            type: 'telemetry',
            input: { session_key: parseInt(session_key), driver_number: parseInt(driver_number) },
        });
        log.info(`✅ GET /api/telemetry success`, { durationMs: Date.now() - startTime });
        return NextResponse.json(result);
    } catch (e) {
        log.error(`❌ GET /api/telemetry failed`, {
            error: e instanceof Error ? { message: e.message, stack: e.stack } : String(e),
            durationMs: Date.now() - startTime
        });
        return NextResponse.json({ error: 'Telemetry analysis failed' }, { status: 500 });
    }
}
