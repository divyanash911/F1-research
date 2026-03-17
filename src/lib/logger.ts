// ============================================================
// Structured Debug Logger — File + Console Output
// ============================================================

import { appendFileSync, mkdirSync } from 'fs';
import { join } from 'path';

export type LogLevel = 'DEBUG' | 'INFO' | 'WARN' | 'ERROR';

const LOG_FILE = join(process.cwd(), 'f1-debug.log');

const LEVEL_PRIORITY: Record<LogLevel, number> = {
    DEBUG: 0,
    INFO: 1,
    WARN: 2,
    ERROR: 3,
};

const LEVEL_COLORS: Record<LogLevel, string> = {
    DEBUG: '\x1b[36m',  // Cyan
    INFO: '\x1b[32m',   // Green
    WARN: '\x1b[33m',   // Yellow
    ERROR: '\x1b[31m',  // Red
};

const RESET = '\x1b[0m';
const DIM = '\x1b[2m';
const BOLD = '\x1b[1m';

// Minimum level that gets written (configurable via env)
const MIN_LEVEL: LogLevel = (process.env.LOG_LEVEL as LogLevel) || 'DEBUG';

function formatTimestamp(): string {
    return new Date().toISOString();
}

function prettyData(data: unknown): string {
    if (data === undefined || data === null) return '';
    try {
        return JSON.stringify(data, null, 2);
    } catch {
        return String(data);
    }
}

function truncateForLog(data: unknown, maxLen = 2000): string {
    const str = prettyData(data);
    if (str.length <= maxLen) return str;
    return str.slice(0, maxLen) + `\n... [truncated, ${str.length} chars total]`;
}

function writeToFile(entry: string): void {
    try {
        appendFileSync(LOG_FILE, entry + '\n', 'utf-8');
    } catch {
        // If file writing fails, don't crash the app
    }
}

function formatConsole(
    level: LogLevel,
    component: string,
    message: string,
    data?: unknown
): string {
    const ts = formatTimestamp();
    const color = LEVEL_COLORS[level];
    let line = `${DIM}${ts}${RESET} ${color}${BOLD}[${level}]${RESET} ${BOLD}[${component}]${RESET} ${message}`;
    if (data !== undefined && data !== null) {
        const pretty = truncateForLog(data, 1000);
        if (pretty) line += `\n${DIM}${pretty}${RESET}`;
    }
    return line;
}

function formatFile(
    level: LogLevel,
    component: string,
    message: string,
    data?: unknown
): string {
    const ts = formatTimestamp();
    let line = `${ts} [${level}] [${component}] ${message}`;
    if (data !== undefined && data !== null) {
        const pretty = truncateForLog(data);
        if (pretty) line += `\n${pretty}`;
    }
    return line;
}

class Logger {
    private component: string;

    constructor(component: string) {
        this.component = component;
    }

    private log(level: LogLevel, message: string, data?: unknown): void {
        if (LEVEL_PRIORITY[level] < LEVEL_PRIORITY[MIN_LEVEL]) return;

        // Console output (pretty with colors)
        const consoleLine = formatConsole(level, this.component, message, data);
        switch (level) {
            case 'ERROR':
                console.error(consoleLine);
                break;
            case 'WARN':
                console.warn(consoleLine);
                break;
            default:
                console.log(consoleLine);
        }

        // File output (clean text)
        const fileLine = formatFile(level, this.component, message, data);
        writeToFile(fileLine);
    }

    debug(message: string, data?: unknown): void {
        this.log('DEBUG', message, data);
    }

    info(message: string, data?: unknown): void {
        this.log('INFO', message, data);
    }

    warn(message: string, data?: unknown): void {
        this.log('WARN', message, data);
    }

    error(message: string, data?: unknown): void {
        this.log('ERROR', message, data);
    }

    /** Log an HTTP request/response pair */
    httpRequest(method: string, url: string, status?: number, durationMs?: number, extra?: unknown): void {
        const statusEmoji = status && status >= 200 && status < 300 ? '✅' : status ? '❌' : '⏳';
        const parts = [`${statusEmoji} ${method} ${url}`];
        if (status !== undefined) parts.push(`→ ${status}`);
        if (durationMs !== undefined) parts.push(`(${durationMs}ms)`);
        const level: LogLevel = status && status >= 400 ? 'ERROR' : 'DEBUG';
        this.log(level, parts.join(' '), extra);
    }

    /** Log API data fetch results with counts */
    dataResult(endpoint: string, count: number, params?: Record<string, unknown>): void {
        const emoji = count > 0 ? '📊' : '⚠️';
        this.log(
            count > 0 ? 'DEBUG' : 'WARN',
            `${emoji} ${endpoint}: ${count} results`,
            params
        );
    }

    /** Log agent execution start/end */
    agentStart(agentName: string, input?: unknown): void {
        this.log('INFO', `🚀 Agent started: ${agentName}`, input);
    }

    agentEnd(agentName: string, durationMs: number, success: boolean): void {
        const emoji = success ? '✅' : '❌';
        this.log(
            success ? 'INFO' : 'ERROR',
            `${emoji} Agent finished: ${agentName} (${durationMs}ms)`
        );
    }

    /** Separator for visual clarity */
    separator(label?: string): void {
        const sep = label
            ? `═══════════════════ ${label} ═══════════════════`
            : '═══════════════════════════════════════════════';
        this.log('DEBUG', sep);
    }
}

/** Create a scoped logger for a specific component */
export function createLogger(component: string): Logger {
    return new Logger(component);
}

/** Get the log file path */
export function getLogFilePath(): string {
    return LOG_FILE;
}
