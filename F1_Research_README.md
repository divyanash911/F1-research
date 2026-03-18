# 🏎️ F1 Autonomous Research Program

> A fully autonomous, multi-agent F1 research system powered by **CrewAI**, **FastF1**, and your choice of **Ollama**, **OpenRouter**, or **Groq** as the LLM backend.

## Architecture Overview

```
f1_research/
├── main.py                  # 🚀 Entry point & research orchestrator
├── llm_config.py            # 🔧 Multi-backend LLM (Ollama/OpenRouter/Groq)
├── logger.py                # 📝 Fine-grained logging infrastructure
├── callbacks.py             # 📡 CrewAI event hooks for deep tracing
├── .env.example             # ⚙️  Environment configuration template
│
├── agents/
│   └── f1_agents.py         # 🤖 9 specialized research agents
│
├── crews/
│   └── research_crews.py    # 👥 6 research crews with debate tasks
│
├── tools/
│   ├── telemetry_tools.py   # 📊 12 FastF1 telemetry analysis tools
│   └── research_tools.py    # 📰 5 news & research tools
│
├── logs/                    # 📁 Auto-created per-session log directories
│   └── {SESSION_ID}/
│       ├── agent_conversations.log   # All agent messages
│       ├── tool_calls.log            # JSON log of every tool call
│       ├── llm_responses.log         # Raw LLM responses
│       ├── telemetry_analysis.log    # Telemetry findings
│       ├── published_insights.log    # Insight publication log
│       ├── agent_debates.log         # Agent debate rounds
│       ├── race_predictions.log      # All predictions
│       ├── news_feed.log             # F1 news items
│       ├── research_summary.log      # Session summaries
│       ├── errors.log                # Error traces (JSON)
│       └── performance.log           # Timing metrics
│
├── insights/                # 💡 Published research findings (Markdown)
│   └── YYYY-MM-DD_*.md
│
└── telemetry_cache/         # 🗄️  FastF1 data cache (auto-managed)
```

## The 9 Research Agents

| Agent | Role | Key Capability |
|-------|------|----------------|
| **Chief Research Officer** | Orchestrator & synthesizer | Delegates, debates, synthesizes |
| **Telemetry Analyst** | Microscopic telemetry analysis | Speed traces, throttle/brake patterns |
| **Strategy Analyst** | Pit stop & tyre strategy | Degradation models, optimal windows |
| **Driver Analyst** | Driver form & performance | Teammate comparisons, form indices |
| **Constructor Analyst** | Car & team performance | Car development trajectories |
| **Prediction Analyst** | Race forecasting | Monte Carlo win probabilities |
| **News Analyst** | Current F1 context | News + data cross-referencing |
| **Anomaly Hunter** | Statistical pattern detection | Hypothesis testing, Python analysis |
| **Debate Agent** | Devil's advocate | Quality control, alternative hypotheses |

## The 6 Research Crews

1. **News & Context Crew** → Fetches current F1 news, builds research agenda
2. **Telemetry Deep Dive Crew** → Race/quali lap analysis, driver comparisons
3. **Strategy & Constructor Crew** → Tyre strategy, constructor championship
4. **Driver & Anomaly Crew** → Form analysis, statistical pattern hunting, debates
5. **Prediction Crew** → Next race predictions with probability distributions
6. **Synthesis Crew** → Combines all findings into intelligence report

## The 12 Telemetry Tools (FastF1)

| Tool | What It Analyzes |
|------|-----------------|
| `get_season_schedule` | Full F1 season calendar |
| `analyze_lap_times` | Race pace, degradation, consistency metrics |
| `compare_driver_telemetry` | Head-to-head speed/throttle/brake/DRS comparison |
| `analyze_tyre_strategy` | Stint lengths, compound choice, degradation curves |
| `analyze_qualifying` | Q1/Q2/Q3 evolution, theoretical best laps |
| `analyze_weather` | Air/track temp, wind, rain impact |
| `analyze_teammates` | Intra-team pace battles |
| `analyze_sectors` | Sector dominance, theoretical lap gaps |
| `analyze_car_performance` | Power unit, top speed, aerodynamic efficiency |
| `get_championship_standings` | Points, gaps, win rates, DNF analysis |
| `execute_python_analysis` | Custom Python/math/stats (agents write code!) |
| `detect_statistical_patterns` | Autocorrelation, outliers, trends, IQR |

## Setup

### 1. Clone & Install

```bash
git clone <repo>
cd f1_research
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your chosen backend:
```

**Groq (fastest, free tier available):**
```env
LLM_BACKEND=groq
GROQ_API_KEY=gsk_your_key_here
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_FAST_MODEL=llama-3.1-8b-instant
```

**OpenRouter (most model options):**
```env
LLM_BACKEND=openrouter
OPENROUTER_API_KEY=sk-or-your_key_here
OPENROUTER_MODEL=meta-llama/llama-3.3-70b-instruct
OPENROUTER_FAST_MODEL=meta-llama/llama-3.1-8b-instruct
```

**Ollama (fully local, no API key needed):**
```bash
# First: install Ollama and pull models
ollama pull llama3.1:8b
ollama pull llama3.2:3b
```
```env
LLM_BACKEND=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
```

### 3. Run Research

```bash
# Full autonomous research on most recent race
python main.py

# Research on specific race
python main.py --event "Bahrain"
python main.py --event 1

# Quick mode (3 crews, ~10 mins)
python main.py --mode quick

# Single crew for targeted analysis
python main.py --mode single --crew telemetry
python main.py --mode single --crew predict
python main.py --mode single --crew news

# Autonomous loop (re-runs every 6 hours, perfect for race weekends)
python main.py --mode loop --interval 6
```

## Log Files Explained

After each run, a timestamped session folder is created in `logs/`:

```
logs/20250318_143022/
├── agent_conversations.log    # Every message between agents
├── tool_calls.log             # JSON: every tool call with inputs/outputs
├── llm_responses.log          # Raw model responses (for debugging)
├── telemetry_analysis.log     # FastF1 analysis findings
├── published_insights.log     # Insight publication history
├── agent_debates.log          # Debate rounds between agents
├── race_predictions.log       # All predictions with reasoning
├── news_feed.log              # F1 news items found
├── research_summary.log       # Overall session summary
├── errors.log                 # Errors with full stack traces
├── performance.log            # Timing per operation
└── console_output.log         # Terminal output copy
```

Published insights are written to `insights/YYYY-MM-DD_type.md` as readable Markdown.

## Research Output Examples

The system autonomously publishes findings like:

```markdown
## Verstappen's Sector 2 Dominance is Statistically Significant
**Type:** telemetry_finding | **Confidence:** 87%

In the last 4 races, Verstappen's S2 advantage over his nearest rival averages 
+0.183s — statistically significant (p=0.02) and driven by superior throttle 
application at the apex of medium-speed corners (telemetry shows 12% more time 
at full throttle in S2 vs Hamilton). This is NOT explained by PU performance 
(top speeds are within 1.2 km/h) but by car rotation characteristics.
```

## Adding Custom Analysis

To add a new telemetry tool, add to `tools/telemetry_tools.py`:

```python
@tool("Your Custom Analysis Tool")
def my_custom_analysis(event: str, year: int = SEASON) -> str:
    """Clear description of what this tool does — agents read this!"""
    sess, err = _load_session(year, event, "R")
    # ... your analysis ...
    return json.dumps(results, indent=2)
```

Then add it to `ALL_TELEMETRY_TOOLS` at the bottom of the file.

## LLM Backend Recommendation

| Backend | Speed | Cost | Quality | Best For |
|---------|-------|------|---------|----------|
| Groq | ⚡⚡⚡ Fast | 💰 Free tier | ⭐⭐⭐ Good | Development & testing |
| OpenRouter | ⚡⚡ Medium | 💰💰 Per token | ⭐⭐⭐⭐ Great | Production research |
| Ollama | ⚡ Slow | Free | ⭐⭐⭐ Good | Privacy, offline use |

For race weekend research, **Groq** is recommended (fastest inference = faster research cycles).

---
*This system is unofficial and not affiliated with Formula 1 or the FIA.*
*FastF1 data comes from F1's live timing service.*
