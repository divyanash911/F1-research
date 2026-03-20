"""
F1 Research Program - Crew & Task Definitions
Multi-crew research system: each crew has a distinct research mission.
Crews debate, cross-reference, and iteratively refine findings.
"""

import os
from typing import Callable
from crewai import Crew, Task, Process
from logger import (
    log_agent_message, log_debate_round, log_insight,
    log_prediction, log_research_summary, console
)
from tools.research_tools import read_published_insights, retrieve_relevant_insights

SEASON = int(os.getenv("F1_SEASON", "2026"))


def _call_tool_func(tool_obj, **kwargs) -> str:
    func = getattr(tool_obj, "func", None)
    if callable(func):
        return func(**kwargs)
    if callable(tool_obj):
        return tool_obj(**kwargs)
    raise TypeError(f"Object {tool_obj!r} is not callable and has no callable .func")


def _preloaded_memory_block(
    title: str,
    loader: Callable[[], str],
    max_chars: int = 1200,
) -> str:
    try:
        payload = (loader() or "").strip()
    except Exception as exc:
        payload = f'{{"error": "{str(exc)[:180]}"}}'

    payload = payload[:max_chars].strip()
    if not payload:
        payload = '{"status": "empty", "message": "No preloaded memory available."}'

    return (
        f"\nPreloaded memory for this task ({title}):\n"
        "Use this as already-retrieved historical context. Do not repeat the same "
        "retrieval unless you need a narrower follow-up query.\n"
        f"{payload}\n"
    )


# ══════════════════════════════════════════════════════════════════════════════
# CREW 1: Live News & Current Context Crew
# ══════════════════════════════════════════════════════════════════════════════
def build_news_crew(agents: dict) -> tuple[Crew, list[Task]]:
    """Crew that monitors current F1 news and sets context for other crews."""

    news_memory = _preloaded_memory_block(
        "news department memory",
        lambda: _call_tool_func(
            retrieve_relevant_insights,
            query=f"latest F1 news themes current context technical updates FIA regulation {SEASON}",
            department="news",
            date_filter="this_week",
            max_results=4,
            max_chars=1200,
        ),
    )

    t1 = Task(
        description=f"""
        {news_memory}

        Search for the latest F1 news from the past 48 hours. Cover:
        1. Race/qualifying results from the most recent Grand Prix
        2. Team technical updates and car upgrades
        3. Driver statements, controversies, or performance news
        4. FIA regulatory decisions or investigations
        5. Championship standings implications
        
        For each story found, assess its DATA relevance — what telemetry or 
        statistical analysis would confirm or challenge the narrative?
        
        Run no more than 2-3 news searches total.
        Search queries to prefer:
        - "F1 2026 latest race results"
        - "F1 team updates upgrades {SEASON}"
        - "F1 FIA regulation 2026"

        Tool usage note:
        - When calling `search_f1_latest_news`, ALWAYS pass both arguments:
          `query` (non-empty string) and `max_results` (int, prefer 4 or 5).
        - After enough evidence is gathered, stop searching and write the briefing.
        
        Compile a concise news briefing with relevance scores.
        Publish at most 1 high-confidence insight from this task.
        """,
        expected_output=(
            "A structured news briefing with: top stories, data investigation hooks "
            "(what telemetry could confirm/deny each story), and a priority list of "
            "what the research team should analyze based on current news."
        ),
        agent=agents["news_analyst"],
    )

    t2 = Task(
        description=f"""
        {_preloaded_memory_block(
            "today's published insight summaries",
            lambda: _call_tool_func(
                read_published_insights,
                date_filter="today",
                department="news",
                max_chars=900,
            ),
            max_chars=900,
        )}

        Based on the news briefing, get the F1 season schedule and identify:
        1. The most recent completed race (round number and name)
        2. The upcoming next race  
        3. Key questions the research team should answer before the next race
        4. Which circuits are coming up that historically favor which teams
        
        Use the schedule tool to get accurate data, then cross-reference with
        news to provide the research team's priority agenda.
        """,
        expected_output=(
            "A research agenda: current season state, recent event details, "
            "next race information, and prioritized research questions."
        ),
        agent=agents["chief_researcher"],
        context=[t1],
    )

    crew = Crew(
        agents=[agents["news_analyst"], agents["chief_researcher"]],
        tasks=[t1, t2],
        process=Process.sequential,
        verbose=True,
    )
    return crew, [t1, t2]


# ══════════════════════════════════════════════════════════════════════════════
# CREW 2: Deep Telemetry Analysis Crew
# ══════════════════════════════════════════════════════════════════════════════
def build_telemetry_crew(agents: dict, recent_event: str = "1") -> tuple[Crew, list[Task]]:
    """Deep telemetry analysis crew for the most recent race weekend."""

    race_pace_memory = _preloaded_memory_block(
        "telemetry memory: race pace",
        lambda: _call_tool_func(
            retrieve_relevant_insights,
            query=f"event {recent_event} recent race pace tyre degradation consistency anomaly",
            department="telemetry",
            date_filter="all",
            max_results=4,
            max_chars=1200,
        ),
    )
    qualifying_memory = _preloaded_memory_block(
        "telemetry memory: qualifying",
        lambda: _call_tool_func(
            retrieve_relevant_insights,
            query=f"event {recent_event} qualifying sector dominance theoretical best top speed setup",
            department="telemetry",
            date_filter="all",
            max_results=4,
            max_chars=1200,
        ),
    )
    battle_memory = _preloaded_memory_block(
        "telemetry memory: driver battles",
        lambda: _call_tool_func(
            retrieve_relevant_insights,
            query=f"event {recent_event} driver battle qualifying gap race gap sector comparison top teams",
            department="telemetry",
            date_filter="all",
            max_results=4,
            max_chars=1200,
        ),
    )

    t_lap = Task(
        description=f"""
        {race_pace_memory}

        Perform a comprehensive race pace analysis for the most recent F1 race 
        (event: '{recent_event}', year: {SEASON}).

        First call `retrieve_relevant_insights` with a query about recent race pace
        and `department='telemetry'` so you know what telemetry findings already exist.
        First call `build_race_pace_evidence`. Treat that evidence packet as your
        primary source. Use raw telemetry/statistics tools only if the evidence packet
        clearly leaves a gap you must fill.

        From the evidence packet, explain:
        1. Race-trim pace hierarchy
        2. Best and worst tyre degradation signals
        3. Which drivers combined pace with consistency
        4. The strongest anomaly or outlier pattern

        Keep the writeup evidence-first and compact.
        Publish your single strongest race-pace finding.
        """,
        expected_output=(
            "Detailed lap time analysis with pace rankings, degradation curves, "
            "statistical patterns, and at least 1 published insight about the race pace findings."
        ),
        agent=agents["telemetry_analyst"],
    )

    t_qual = Task(
        description=f"""
        {qualifying_memory}

        Analyze the qualifying session for the most recent race weekend 
        (event: '{recent_event}', year: {SEASON}).

        First call `retrieve_relevant_insights` with a qualifying-focused query and
        `department='telemetry'` to avoid repeating old qualifying observations.
        First call `build_qualifying_evidence`. Treat that evidence packet as your
        main input. Only call raw qualifying/sector/car tools if a specific detail
        is missing from the packet.

        From the evidence packet, explain:
        1. Grid hierarchy and the main pace spread
        2. Who left the most time on the table versus theoretical best
        3. Sector dominance map
        4. Straight-line speed context and what it implies about setup
        5. One clear connection between qualifying shape and likely race behavior

        Publish one key qualifying insight.
        """,
        expected_output=(
            "Full qualifying deep-dive with sector analysis, theoretical lap gaps, "
            "car performance insights, and published findings."
        ),
        agent=agents["telemetry_analyst"],
    )

    t_compare = Task(
        description=f"""
        {battle_memory}

        Run head-to-head telemetry comparisons for the top 4 teams' driver pairs
        from the qualifying session (event: '{recent_event}', year: {SEASON}).

        First call `retrieve_relevant_insights` with a driver-battle query and
        `department='telemetry'` so your scorecard builds on prior findings.
        First call `build_driver_battle_evidence`. Use that evidence packet as the
        primary source. Only drill into raw comparison tools if one battle needs
        deeper explanation.

        From the evidence packet, explain:
        1. Exact qualifying gap per top team
        2. Which sectors each driver tends to win
        3. Whether the same driver advantage persists into the race
        4. The qualifying-vs-race gap correlation
        5. Which battle is closest and which is most one-sided

        Keep the answer compact and evidence-first.
        Publish a "Driver Battle Scorecard" insight.
        """,
        expected_output=(
            "Telemetry-level driver comparisons for top teams with statistical "
            "analysis of qualifying-to-race correlation and a published scorecard."
        ),
        agent=agents["telemetry_analyst"],
        context=[t_lap, t_qual],
    )

    crew = Crew(
        agents=[agents["telemetry_analyst"]],
        tasks=[t_lap, t_qual, t_compare],
        process=Process.sequential,
        verbose=True,
    )
    return crew, [t_lap, t_qual, t_compare]


# ══════════════════════════════════════════════════════════════════════════════
# CREW 3: Strategy & Constructor Analysis Crew
# ══════════════════════════════════════════════════════════════════════════════
def build_strategy_crew(agents: dict, recent_event: str = "1") -> tuple[Crew, list[Task]]:
    strategy_memory = _preloaded_memory_block(
        "strategy department memory",
        lambda: _call_tool_func(
            retrieve_relevant_insights,
            query=f"event {recent_event} strategy tyre degradation pit stop undercut overcut safety car",
            department="strategy",
            date_filter="all",
            max_results=4,
            max_chars=1100,
        ),
    )
    constructor_memory = _preloaded_memory_block(
        "constructor and development memory",
        lambda: _call_tool_func(
            retrieve_relevant_insights,
            query=f"event {recent_event} constructor pace trend technical development top speed qualifying race pace",
            department="news",
            date_filter="all",
            max_results=4,
            max_chars=1100,
        ),
    )

    t_strategy = Task(
        description=f"""
        {strategy_memory}

        Perform a deep post-race strategy analysis for event '{recent_event}', {SEASON}.
        
        Use the tyre strategy analysis tool to get all stint data, then:
        1. Was the dominant strategy optimal? Model the alternative strategies.
        2. Which teams made strategic mistakes? Calculate the time loss.
        3. Identify undercut/overcut attempts — which worked and why?
        4. How did safety car periods affect strategy execution?
        5. What was the tyre degradation rate per compound? Did any compound
           perform unexpectedly (better or worse than predicted)?
        6. Which driver benefited most from strategy vs pure pace?
        
        Run a Python analysis to model what the race result would have been
        with mathematically optimal strategies for the top 5 finishers.
        
        Publish: "Strategy Review: [Event Name] GP" with confidence 0.9.
        """,
        expected_output=(
            "Comprehensive strategy analysis with optimal vs actual comparison, "
            "degradation rates, strategic winners/losers, and published insight."
        ),
        agent=agents["strategy_analyst"],
    )

    t_constructor = Task(
        description=f"""
        {constructor_memory}

        Analyze constructor championship performance across all recent races.
        
        Use the championship standings tool, then do car performance analysis
        for the most recent 2 events ('{recent_event}' and prior round):
        
        1. Which constructor is currently best in RACE pace vs QUALIFYING pace?
           (Some teams qualify better than they race and vice versa)
        2. Top speed hierarchy across teams — who has PU advantage?
        3. Identify: which teams are closing the gap fastest? (trend analysis)
        4. Which circuit types favor which constructors? Use your knowledge.
        5. Constructor championship scenarios: who needs what to win?
        
        Use Python to calculate: if current pace deltas hold for remaining races,
        what is the expected constructor points gap at season end?
        
        Publish one constructor championship outlook with confidence score.
        """,
        expected_output=(
            "Constructor analysis with pace trends, top speed data, championship "
            "scenarios, and mathematical projection of final standings."
        ),
        agent=agents["constructor_analyst"],
    )

    t_weather = Task(
        description=f"""
        {strategy_memory}

        Analyze weather impact on performance for recent races and upcoming events.
        
        Use the weather analysis tool for the most recent race and qualifying sessions.
        Then cross-reference with lap time data to find:
        1. Track temperature vs lap time correlation (run Python regression analysis)
        2. At what track temperature do tyres hit the performance cliff?
        3. How did wind conditions affect sector times?
        4. Which drivers/teams perform best in high vs low track temperature?
        
        Search for weather forecasts for the upcoming race using news tools.
        Assess strategic implications for the next race weekend.
        
        Publish: "Weather-Performance Correlation Analysis" as a statistical finding.
        """,
        expected_output=(
            "Weather impact analysis with statistical correlations, temperature "
            "thresholds, and strategic implications for upcoming race."
        ),
        agent=agents["strategy_analyst"],
        context=[t_strategy],
    )

    crew = Crew(
        agents=[agents["strategy_analyst"], agents["constructor_analyst"]],
        tasks=[t_strategy, t_constructor, t_weather],
        process=Process.sequential,
        verbose=True,
    )
    return crew, [t_strategy, t_constructor, t_weather]


# ══════════════════════════════════════════════════════════════════════════════
# CREW 4: Driver Form & Anomaly Detection Crew
# ══════════════════════════════════════════════════════════════════════════════
def build_driver_anomaly_crew(agents: dict, recent_event: str = "1") -> tuple[Crew, list[Task]]:
    driver_memory = _preloaded_memory_block(
        "driver department memory",
        lambda: _call_tool_func(
            retrieve_relevant_insights,
            query=f"{SEASON} driver form teammate battle race day improvement qualifying pace",
            department="driver",
            date_filter="all",
            max_results=4,
            max_chars=1100,
        ),
    )
    anomaly_memory = _preloaded_memory_block(
        "anomaly department memory",
        lambda: _call_tool_func(
            retrieve_relevant_insights,
            query=f"event {recent_event} anomaly autocorrelation degradation statistical pattern",
            department="anomaly",
            date_filter="all",
            max_results=4,
            max_chars=1100,
        ),
    )
    today_insights = _preloaded_memory_block(
        "today's insight summaries",
        lambda: _call_tool_func(
            read_published_insights,
            date_filter="today",
            max_chars=1100,
        ),
        max_chars=1100,
    )

    t_driver_form = Task(
        description=f"""
        {driver_memory}

        Analyze individual driver form and performance trends for the {SEASON} season.
        
        Use championship standings to get the full driver picture, then deep-dive:
        1. Who is in the best form right now? Compute a "form index" based on:
           - Last 3 races points percentage
           - Qualifying vs expected grid position
           - Race finishing position vs grid position
        2. Who is significantly underperforming vs their career baseline?
        3. Teammate battles: who is winning the most within each team?
           Use teammate analysis for the recent event.
        4. Identify: which drivers improve most on race day vs qualifying?
           (Convert raw quali pace to race pace probability)
        5. Wet weather specialists: search for historical wet race performance data
        
        Publish a "Driver Form Guide" with form ratings 1-10 for the top 5 drivers.
        """,
        expected_output=(
            "Comprehensive driver form analysis with numerical ratings, teammate "
            "battle scorecards, and a published form guide for next race betting."
        ),
        agent=agents["driver_analyst"],
    )

    t_anomaly = Task(
        description=f"""
        {anomaly_memory}

        Hunt for statistical anomalies and hidden patterns in {SEASON} F1 data.
        
        Use the statistical patterns detection tool for the most recent race.
        Then write and execute custom Python analysis to test hypotheses:
        
        HYPOTHESIS 1: "Lap time autocorrelation reveals car balance issues"
        - High positive autocorrelation (slow laps follow slow laps) = car balance issue
        - Test: which drivers showed this pattern and in which stints?
        
        HYPOTHESIS 2: "Second half degradation varies systematically by constructor"
        - Calculate pace_delta_2nd_half for all drivers grouped by constructor
        - Which constructor's cars fade most/least?
        
        HYPOTHESIS 3: "There exists an optimal stint length for each compound"
        - Using stint data, fit a quadratic model to pace vs stint lap number
        - Find the inflection point where degradation accelerates
        
        Run Python code (use execute_python_analysis) to test each hypothesis
        with real numbers. Report p-values or evidence scores.
        
        Publish any confirmed anomaly with the evidence supporting it.
        """,
        expected_output=(
            "Statistical anomaly report with tested hypotheses, Python analysis "
            "results, evidence scores, and published confirmed patterns."
        ),
        agent=agents["anomaly_hunter"],
        context=[t_driver_form],
    )

    t_challenge = Task(
        description=f"""
        {today_insights}

        You are the devil's advocate. Review ALL insights published today using
        the read_published_insights tool (filter: 'today'). If a specific claim needs
        more context, use `retrieve_relevant_insights` with a focused query instead of
        loading large historical content.
        
        For each insight:
        1. Identify the key claim being made
        2. List 2-3 alternative explanations for the same data pattern
        3. Identify any confounding variables the analysis might have missed
        4. Rate the robustness of the evidence (1-5 stars)
        5. For weak insights, suggest what additional analysis would strengthen them
        
        Then, identify the 2 STRONGEST insights (most evidence, least alternative
        explanations) and the 2 WEAKEST insights (could easily be confounded).
        
        Publish a "Research Quality Assessment" insight that grades today's findings
        and identifies the most reliable discoveries.
        
        This debate and quality control process is critical for scientific integrity.
        Don't hold back — challenge everything rigorously.
        """,
        expected_output=(
            "Quality assessment of all published insights: rated by robustness, "
            "alternative explanations identified, and a published quality report."
        ),
        agent=agents["debate_agent"],
        context=[t_driver_form, t_anomaly],
    )

    crew = Crew(
        agents=[agents["driver_analyst"], agents["anomaly_hunter"], agents["debate_agent"]],
        tasks=[t_driver_form, t_anomaly, t_challenge],
        process=Process.sequential,
        verbose=True,
    )
    return crew, [t_driver_form, t_anomaly, t_challenge]


# ══════════════════════════════════════════════════════════════════════════════
# CREW 5: Race Prediction Crew
# ══════════════════════════════════════════════════════════════════════════════
def build_prediction_crew(agents: dict, recent_event: str = "1") -> tuple[Crew, list[Task]]:
    prediction_memory = _preloaded_memory_block(
        "prediction department memory",
        lambda: _call_tool_func(
            retrieve_relevant_insights,
            query=f"next race prediction circuit suitability race pace qualifying form dark horse reliability",
            department="prediction",
            date_filter="all",
            max_results=4,
            max_chars=1100,
        ),
    )
    telemetry_prediction_memory = _preloaded_memory_block(
        "telemetry memory for prediction",
        lambda: _call_tool_func(
            retrieve_relevant_insights,
            query=f"recent telemetry race pace qualifying hierarchy event {recent_event}",
            department="telemetry",
            date_filter="all",
            max_results=4,
            max_chars=1100,
        ),
    )
    today_insights = _preloaded_memory_block(
        "today's insight summaries",
        lambda: _call_tool_func(
            read_published_insights,
            date_filter="today",
            max_chars=1100,
        ),
        max_chars=1100,
    )

    t_next_race_info = Task(
        description=f"""
        {prediction_memory}

        Gather all available information about the NEXT F1 race.
        
        1. Use get_next_race_info to identify the upcoming race
        2. Search for: "[circuit name] F1 circuit characteristics"
        3. Search for: "[circuit name] F1 historical results"
        4. Search for: "F1 [upcoming race] preview 2026"
        5. Search for: weather forecast for [city/country] race weekend
        
        Compile: circuit characteristics (high/low downforce, tyre demands,
        overtaking difficulty), historical winners, and any relevant news.
        Assess which teams/drivers historically excel at this circuit.
        """,
        expected_output=(
            "Comprehensive next race briefing: circuit profile, historical data, "
            "weather outlook, and initial team/driver advantage assessment."
        ),
        agent=agents["news_analyst"],
    )

    t_prediction = Task(
        description=f"""
        {today_insights}
        {telemetry_prediction_memory}

        Generate a detailed, probability-weighted race prediction for the next F1 race.
        
        Read all today's published insights (use read_published_insights, filter='today')
        to incorporate current form data. Then call `retrieve_relevant_insights` with
        a next-race prediction query and `department='prediction'` or `department='telemetry'`
        to pull only the most relevant prior memory. Also use championship standings.
        
        Your prediction must include:
        
        1. **Win Probability Distribution** (must sum to 100%):
           Top 8 drivers with % probability of winning
           Based on: qualifying form, race pace, circuit suitability, reliability
        
        2. **Podium Probability** for top 5 drivers
        
        3. **Expected Race Pace Hierarchy** (race trim pace order)
           Based on recent telemetry pace data
        
        4. **Key Strategic Variable**: what one factor will most decide this race?
           (safety car timing, tyre deg difference, weather, etc.)
        
        5. **Dark Horse**: who at 10%+ odds could upset the favourites and why?
        
        6. **Confidence Assessment**: rate your prediction confidence 1-10 and
           identify the 2 main uncertainties that could make you wrong
        
        Use Python (execute_python_analysis) to model win probabilities using:
        - Base rate of winning from pole/P2/P3/etc at similar circuits
        - Current form adjustment (+/- 5% based on last 3 races)
        - Reliability factor (DNF rates this season)
        
        Keep the response compact. If evidence is incomplete, still provide the
        top probabilities and explicitly label uncertainties instead of failing.
        Publish the full prediction with confidence: 0.65
        """,
        expected_output=(
            "Full race prediction with win probability distributions, podium odds, "
            "strategic scenario analysis, and Python-modeled probability calculations."
        ),
        agent=agents["prediction_analyst"],
        context=[t_next_race_info],
    )

    t_championship = Task(
        description=f"""
        {prediction_memory}

        Generate a championship outlook and prediction for the rest of the {SEASON} season.
        
        Use championship standings to get current points gaps, then:
        1. Calculate: points available remaining in the season
        2. For each title contender: what is their mathematically required 
           average finish to win the championship?
        3. Run Python analysis: Monte Carlo simulation (300 iterations) of the
           remaining season where each race's winner is drawn probabilistically
           from recent form data. Output: championship win probability per driver.
        4. Identify: which upcoming circuits favor which championship contender?
        5. Key swing races: which 3 races will be most decisive for the championship?
        
        Publish: "Championship Outlook {SEASON}" as a high-confidence prediction.
        """,
        expected_output=(
            "Championship mathematical analysis with Monte Carlo probabilities, "
            "key circuit assessments, and published championship outlook."
        ),
        agent=agents["prediction_analyst"],
        context=[t_next_race_info, t_prediction],
    )

    crew = Crew(
        agents=[agents["news_analyst"], agents["prediction_analyst"]],
        tasks=[t_next_race_info, t_prediction, t_championship],
        process=Process.sequential,
        verbose=True,
    )
    return crew, [t_next_race_info, t_prediction, t_championship]


# ══════════════════════════════════════════════════════════════════════════════
# CREW 6: Synthesis & Summary Crew
# ══════════════════════════════════════════════════════════════════════════════
def build_synthesis_crew(agents: dict) -> tuple[Crew, list[Task]]:
    """Final crew that synthesizes everything into a research report."""

    today_insights = _preloaded_memory_block(
        "today's insight summaries",
        lambda: _call_tool_func(
            read_published_insights,
            date_filter="today",
            max_chars=1200,
        ),
        max_chars=1200,
    )
    synthesis_memory = _preloaded_memory_block(
        "synthesis department memory",
        lambda: _call_tool_func(
            retrieve_relevant_insights,
            query="intelligence report executive summary strongest discoveries narrative busters",
            department="synthesis",
            date_filter="all",
            max_results=4,
            max_chars=1100,
        ),
        max_chars=1100,
    )

    t_synthesize = Task(
        description=f"""
        {today_insights}
        {synthesis_memory}

        You are the Chief Research Officer. Read all insights published today
        (read_published_insights, filter='today'). Use `retrieve_relevant_insights`
        for any section where you need prior context, so you work from compact ranked
        memory instead of large raw files.
        
        Synthesize the day's research into a comprehensive F1 Intelligence Report:
        
        ## Section 1: Executive Summary (3-5 bullet points of key takeaways)
        
        ## Section 2: Most Important Discoveries (ranked by significance)
        What are the 3-5 genuinely new insights that weren't obvious before analysis?
        
        ## Section 3: Data-Confirmed Narratives
        Which popular narratives in F1 media are supported by the data?
        
        ## Section 4: Narrative Busters
        Which popular narratives are NOT supported by data? What does the data
        actually say instead?
        
        ## Section 5: Next Race Prediction Summary
        Concise version of race predictions with top 3 probabilities
        
        ## Section 6: Research Confidence Assessment
        Overall confidence in today's findings and key remaining uncertainties
        
        ## Section 7: Tomorrow's Research Agenda
        What should the team investigate next? What questions remain unanswered?
        
        If the available insights are incomplete, still publish a shorter report
        that clearly distinguishes confirmed findings from open questions.
        Publish this as an "Intelligence Report" insight with high confidence (0.85).
        This becomes the daily research digest.
        """,
        expected_output=(
            "A comprehensive F1 Intelligence Report covering all research findings, "
            "predictions, narrative analysis, and tomorrow's research agenda."
        ),
        agent=agents["chief_researcher"],
    )

    crew = Crew(
        agents=[agents["chief_researcher"]],
        tasks=[t_synthesize],
        process=Process.sequential,
        verbose=True,
    )
    return crew, [t_synthesize]
