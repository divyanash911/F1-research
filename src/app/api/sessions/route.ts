import { NextResponse } from 'next/server';
import * as api from '@/lib/openf1-client';
import { createLogger } from '@/lib/logger';

const log = createLogger('API-Sessions');

export async function GET(request: Request) {
    const { searchParams } = new URL(request.url);
    const year = parseInt(searchParams.get('year') || '2026');
    const meeting_key = searchParams.get('meeting_key');

    log.info(`GET /api/sessions`, { year, meeting_key });
    const startTime = Date.now();

    try {
        const sessions = meeting_key
            ? await api.getSessions({ year, meeting_key: parseInt(meeting_key) })
            : await api.getSessions({ year });

        log.info(`✅ GET /api/sessions success`, { durationMs: Date.now() - startTime, sessionCount: sessions.length });
        return NextResponse.json(sessions);
    } catch (e) {
        log.error(`❌ GET /api/sessions failed`, {
            error: e instanceof Error ? { message: e.message, stack: e.stack } : String(e),
            durationMs: Date.now() - startTime
        });
        return NextResponse.json({ error: 'Failed to fetch sessions' }, { status: 500 });
    }
}
