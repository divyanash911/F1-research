import { NextResponse } from 'next/server';

// Proxies the Python agents service autonomous insights feed.
// Keep the browser insulated from CORS and allow the UI to stay same-origin.

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const limit = searchParams.get('limit') ?? '25';

  const base = process.env.PY_AGENTS_BASE_URL || 'http://localhost:8000';
  const url = `${base.replace(/\/$/, '')}/autonomous/insights?limit=${encodeURIComponent(limit)}`;

  try {
    const res = await fetch(url, { cache: 'no-store' });
    const text = await res.text();
    return new NextResponse(text, {
      status: res.status,
      headers: {
        'content-type': res.headers.get('content-type') || 'application/json',
        'cache-control': 'no-store',
      },
    });
  } catch (e: unknown) {
    return NextResponse.json(
      { error: 'Failed to fetch autonomous insights', details: e instanceof Error ? e.message : String(e) },
      { status: 502 }
    );
  }
}
