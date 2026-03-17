// ============================================================
// News Intelligence Agent — LLM-Reasoned F1 2026 News Curation
// ============================================================

import { callLLMJSON, isLLMConfigured } from '@/lib/llm-client';
import { createLogger } from '@/lib/logger';
import type { NewsItem } from '@/lib/types';
import { TEAMS_2026 } from '@/lib/constants';

const log = createLogger('NewsAgent');

const NEWS_SYSTEM_PROMPT = `You are a Formula 1 journalism and intelligence analyst specializing in the 2026 season.

Key 2026 context you MUST reference:
- Active aerodynamics (front+rear wing Straight/Corner/Overtake modes replace DRS)
- Power unit: 50/50 ICE/Electric, MGU-K at 350kW, no MGU-H, 100% sustainable fuels, 75 kg/h fuel flow
- New teams: Audi (works) and Cadillac (GM/Ferrari PU)
- 11 teams, 22 drivers, 24 races
- Lighter cars (768kg), narrower tires
- Hamilton at Ferrari, Antonelli at Mercedes, Hadjar at Red Bull, Lindblad at Racing Bulls
- PU manufacturers: Mercedes, Ferrari, Red Bull/Ford, Honda (Aston Martin), Audi

Your role is to generate realistic, contextually-grounded F1 news intelligence that:
1. Covers technical developments, driver performance, team strategies, regulation impact
2. Assesses impact on upcoming race performance
3. Identifies trends and storylines
4. Is specific about 2026 technical regulations and their effects`;

/**
 * Generates LLM-reasoned F1 news intelligence for the 2026 season.
 */
export async function getNewsIntelligence(): Promise<NewsItem[]> {
    const startTime = Date.now();
    log.agentStart('NewsIntelligence', {});

    if (!isLLMConfigured()) {
        log.warn('LLM not configured — using fallback news');
        log.agentEnd('NewsIntelligence', Date.now() - startTime, true);
        return getFallbackNews();
    }

    try {
        const teamContext = Object.values(TEAMS_2026)
            .map(t => `${t.shortName} (${t.powerUnit}): ${t.drivers.map(d => d.name).join(', ')}`)
            .join('\n');

        const prompt = `Generate 6-8 current F1 2026 season news intelligence items. Today's date is ${new Date().toISOString().split('T')[0]}.

The 2026 season has just started. The Australian GP was the first race (Mar 6-8), and the Chinese GP is happening now (Mar 13-15, Sprint weekend).

Team/Driver grid:
${teamContext}

Return a JSON object with a "news" array, each item having:
{
  "news": [
    {
      "id": "unique-id",
      "title": "Headline",
      "summary": "2-3 sentence detailed summary with specific 2026 technical context",
      "category": "team_update" | "technical" | "driver" | "regulation" | "prediction",
      "impactLevel": "low" | "medium" | "high",
      "relatedTeams": ["Team1"],
      "relatedDrivers": ["Driver Name"],
      "timestamp": "ISO date string"
    }
  ]
}

Focus on realistic storylines:
- How teams are adapting to active aero and energy management
- Rookie performances (Hadjar, Antonelli, Lindblad, Bearman, Bortoleto, Colapinto)
- New team progress (Audi, Cadillac)
- PU manufacturer competition
- Strategy evolution with the new rules
- Driver adaptations to the new car characteristics`;

        log.debug('🤖 Calling LLM for news generation');
        const result = await callLLMJSON<{ news: NewsItem[] }>(
            [
                { role: 'system', content: NEWS_SYSTEM_PROMPT },
                { role: 'user', content: prompt },
            ],
            { temperature: 0.8, maxTokens: 3000 }
        );

        const news = result.news || getFallbackNews();
        log.info('✅ News generated', { itemCount: news.length });
        log.agentEnd('NewsIntelligence', Date.now() - startTime, true);
        return news;
    } catch (e) {
        log.error('News agent LLM call failed', {
            error: e instanceof Error ? e.message : String(e),
        });
        log.agentEnd('NewsIntelligence', Date.now() - startTime, false);
        return getFallbackNews();
    }
}

function getFallbackNews(): NewsItem[] {
    const now = new Date().toISOString();
    return [
        {
            id: 'news-active-aero',
            title: 'Active Aero Revolution: Teams Adapt to New Wing Systems',
            summary: 'The 2026 active aerodynamics system is proving to be a game-changer. Teams are finding significant laptime differences in optimizing front and rear wing transition speeds between Corner and Straight modes. McLaren and Red Bull appear to lead in active aero deployment efficiency.',
            category: 'technical',
            impactLevel: 'high',
            relatedTeams: ['McLaren', 'Red Bull'],
            relatedDrivers: [],
            timestamp: now,
        },
        {
            id: 'news-energy-wars',
            title: 'Energy Management Becomes the Key Battleground',
            summary: 'With the MGU-K now producing 350kW and the 50/50 ICE/electric power split, energy management has become the defining factor. Teams with superior battery deployment strategies are gaining up to 0.5s per lap.',
            category: 'technical',
            impactLevel: 'high',
            relatedTeams: ['Mercedes', 'Ferrari', 'Audi'],
            relatedDrivers: [],
            timestamp: now,
        },
        {
            id: 'news-hamilton-ferrari',
            title: 'Hamilton Brings Experience to Ferrari\'s 2026 Project',
            summary: 'Lewis Hamilton\'s move to Ferrari is paying dividends early in the 2026 season. His experience with energy management from his Mercedes years gives Ferrari a unique perspective on the 50/50 power split.',
            category: 'driver',
            impactLevel: 'high',
            relatedTeams: ['Ferrari'],
            relatedDrivers: ['Lewis Hamilton', 'Charles Leclerc'],
            timestamp: now,
        },
        {
            id: 'news-overtake-mode',
            title: 'Overtake Mode Delivers on Promise of Better Racing',
            summary: 'The new Overtake Mode system, replacing DRS, provides extra electrical power and enhanced energy recovery. Early races show a 30% increase in overtaking attempts compared to 2025.',
            category: 'regulation',
            impactLevel: 'medium',
            relatedTeams: [],
            relatedDrivers: [],
            timestamp: now,
        },
        {
            id: 'news-rookies',
            title: 'Rookie Class of 2026: Hadjar, Antonelli, Lindblad Impress',
            summary: 'Isack Hadjar at Red Bull has shown remarkable qualifying pace, while Kimi Antonelli at Mercedes is adapting quickly. Arvid Lindblad at Racing Bulls has been the surprise package of the early season.',
            category: 'driver',
            impactLevel: 'medium',
            relatedTeams: ['Red Bull', 'Mercedes', 'Racing Bulls'],
            relatedDrivers: ['Isack Hadjar', 'Kimi Antonelli', 'Arvid Lindblad'],
            timestamp: now,
        },
        {
            id: 'news-new-teams',
            title: 'New Teams: Audi and Cadillac Finding Their Feet',
            summary: 'Audi\'s first season as a full works team has been challenging but promising. Cadillac, running Ferrari power units in their debut season, are steadily improving with Bottas\'s experience guiding development.',
            category: 'team_update',
            impactLevel: 'medium',
            relatedTeams: ['Audi', 'Cadillac'],
            relatedDrivers: ['Nico Hulkenberg', 'Valtteri Bottas', 'Sergio Perez'],
            timestamp: now,
        },
    ];
}
