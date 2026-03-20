"""
F1 Research Program - Main Autonomous Research Engine

The core orchestration loop:
1. Fetches current F1 context (news, schedule)
2. Runs deep telemetry analysis on recent race
3. Runs strategy & constructor analysis
4. Runs driver form & anomaly detection
5. Runs race predictions
6. Synthesizes everything into intelligence report
7. Repeats on schedule or on demand

Run: python main.py
     python main.py --event "Bahrain" --session R
     python main.py --mode single --crew telemetry
     python main.py --mode loop --interval 6
"""

import sys
import os
import argparse
import time
import json
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

# Load env first
load_dotenv(dotenv_path=Path(__file__).resolve().parent / "f1_research" / ".env")
os.environ["OTEL_SDK_DISABLED"]        = "true"
os.environ["CREWAI_DISABLE_TELEMETRY"] = "true"

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "agents"))
sys.path.insert(0, str(Path(__file__).parent / "crews"))
sys.path.insert(0, str(Path(__file__).parent / "tools"))

# Initialize logging (must be before other imports)
from logger import (
    print_banner, console, log_research_summary, log_error,
    log_insight, SESSION_ID, SESSION_DIR, Colors
)

from llm_config import get_backend_info
from agents.f1_agents import make_agents
from crews.research_crews import (
    build_news_crew,
    build_telemetry_crew,
    build_strategy_crew,
    build_driver_anomaly_crew,
    build_prediction_crew,
    build_synthesis_crew,
)


# ── Research Session Tracker ────────────────────────────────────────────────
class ResearchSession:
    def __init__(self):
        self.start_time    = datetime.now()
        self.crews_run     = []
        self.insights_count = 0
        self.errors        = []
        self.recent_event  = "1"  # default, will be updated

    def log_crew_complete(self, crew_name: str, duration_s: float, success: bool):
        self.crews_run.append({
            "crew":     crew_name,
            "duration": round(duration_s, 1),
            "success":  success,
        })
        status = "✅" if success else "❌"
        console.info(
            f"{status} {Colors.CYAN}{crew_name}{Colors.RESET} completed in "
            f"{Colors.YELLOW}{duration_s:.1f}s{Colors.RESET}"
        )

    def final_summary(self) -> dict:
        elapsed = (datetime.now() - self.start_time).total_seconds()
        return {
            "session_id":    SESSION_ID,
            "started":       self.start_time.isoformat(),
            "duration_min":  round(elapsed / 60, 1),
            "crews_run":     self.crews_run,
            "errors_count":  len(self.errors),
            "errors":        self.errors[:5],
            "insights_dir":  "insights/",
            "log_dir":       str(SESSION_DIR),
        }


# ── Crew runner with error handling ────────────────────────────────────────
def run_crew_safe(crew, crew_name: str, session: ResearchSession):
    """Run a crew with full error handling, timing, and logging."""
    start = time.time()
    console.info(f"\n{'═'*60}")
    console.info(f"🚀 Starting Crew: {Colors.BOLD}{crew_name}{Colors.RESET}")
    console.info(f"{'═'*60}")
    
    try:
        result = crew.kickoff()
        duration = time.time() - start
        session.log_crew_complete(crew_name, duration, success=True)
        
        # Log crew output
        output_str = str(result) if result else "No output"
        console.info(f"📤 {crew_name} Output Preview:\n{output_str[:300]}...")
        return result
    
    except Exception as e:
        duration = time.time() - start
        session.log_crew_complete(crew_name, duration, success=False)
        error_msg = f"{type(e).__name__}: {str(e)[:200]}"
        session.errors.append({"crew": crew_name, "error": error_msg})
        log_error(crew_name, e, f"Crew execution failed after {duration:.1f}s")
        console.error(f"❌ {crew_name} failed: {error_msg[:100]}")
        console.error(f"   Full trace in: {SESSION_DIR}/errors.log")
        return None


# ── Detect most recent race event ───────────────────────────────────────────
def detect_recent_event() -> str:
    """Auto-detect the most recent completed F1 race round number."""
    try:
        import fastf1
        import pandas as pd
        
        season = int(os.getenv("F1_SEASON", "2026"))
        schedule = fastf1.get_event_schedule(season)
        now = pd.Timestamp.now(tz="UTC")
        
        # Events where the race (Session5) has already happened
        past = schedule[schedule["Session5Date"] < now].sort_values("Session5Date")
        
        if past.empty:
            console.warning("⚠️  No completed races found — using round 1")
            return "1"
        
        most_recent = past.iloc[-1]
        round_num   = str(int(most_recent["RoundNumber"]))
        event_name  = most_recent["EventName"]
        console.info(f"🎯 Auto-detected most recent race: Round {round_num} — {event_name}")
        return round_num
    
    except Exception as e:
        console.warning(f"⚠️  Could not detect recent event: {e}. Using round 1.")
        return "1"


# ── Full Research Cycle ──────────────────────────────────────────────────────
def run_full_research(event: str = None, mode: str = "full", specific_crew: str = None):
    """
    Run a complete F1 research cycle.
    
    Args:
        event: Race round number or name (auto-detected if None)
        mode:  'full' (all crews) | 'quick' (news+telemetry+predict) | 'single' (one crew)
        specific_crew: Which crew to run in 'single' mode
    """
    session = ResearchSession()
    print_banner()
    
    # Backend info
    info = get_backend_info()
    console.info(f"🔧 Backend: {Colors.CYAN}{info['backend'].upper()}{Colors.RESET}")
    console.info(f"🔧 Model:   {Colors.CYAN}{info['main_model']}{Colors.RESET}")
    console.info(f"🔧 Season:  {Colors.CYAN}{info['f1_season']}{Colors.RESET}")
    console.info(f"🔧 Mode:    {Colors.CYAN}{mode}{Colors.RESET}")
    console.info("")
    
    # Detect event
    if event is None:
        event = detect_recent_event()
    session.recent_event = event
    console.info(f"📍 Target Event: {Colors.GREEN}{event}{Colors.RESET}\n")
    
    # Build agents (shared across crews)
    console.info("🤖 Initializing research agents...")
    try:
        agents = make_agents()
        console.info(f"✅ {len(agents)} agents initialized\n")
    except Exception as e:
        log_error("MAIN", e, "Failed to initialize agents")
        console.error(f"❌ Agent initialization failed: {e}")
        console.error("Check your LLM_BACKEND and API keys in .env")
        sys.exit(1)

    # ── CREW EXECUTION PLAN ─────────────────────────────────────────────
    
    if mode == "single" and specific_crew:
        # Run just one specified crew
        crew_map = {
            "news":      lambda: build_news_crew(agents),
            "telemetry": lambda: build_telemetry_crew(agents, event),
            "strategy":  lambda: build_strategy_crew(agents, event),
            "drivers":   lambda: build_driver_anomaly_crew(agents, event),
            "predict":   lambda: build_prediction_crew(agents, event),
            "synthesis": lambda: build_synthesis_crew(agents),
        }
        if specific_crew in crew_map:
            crew, _ = crew_map[specific_crew]()
            run_crew_safe(crew, specific_crew, session)
        else:
            console.error(f"Unknown crew: {specific_crew}. Options: {list(crew_map.keys())}")

    elif mode == "quick":
        # News → Telemetry → Predictions
        news_crew, _  = build_news_crew(agents)
        tel_crew, _   = build_telemetry_crew(agents, event)
        pred_crew, _  = build_prediction_crew(agents, event)
        
        run_crew_safe(news_crew, "News & Context", session)
        run_crew_safe(tel_crew,  "Telemetry Analysis", session)
        run_crew_safe(pred_crew, "Race Prediction", session)

    else:
        # FULL: all 6 crews in sequence
        # Phase 1: Context gathering
        console.info(f"\n{'🏁'*20}")
        console.info("PHASE 1: NEWS & CONTEXT")
        console.info(f"{'🏁'*20}")
        news_crew, _ = build_news_crew(agents)
        run_crew_safe(news_crew, "News & Context Crew", session)

        # Phase 2: Telemetry deep dive
        console.info(f"\n{'📊'*20}")
        console.info("PHASE 2: DEEP TELEMETRY ANALYSIS")
        console.info(f"{'📊'*20}")
        tel_crew, _ = build_telemetry_crew(agents, event)
        run_crew_safe(tel_crew, "Telemetry Deep Dive Crew", session)

        # Phase 3: Strategy & constructors
        console.info(f"\n{'🏎️ '*10}")
        console.info("PHASE 3: STRATEGY & CONSTRUCTOR ANALYSIS")
        console.info(f"{'🏎️ '*10}")
        strat_crew, _ = build_strategy_crew(agents, event)
        run_crew_safe(strat_crew, "Strategy & Constructor Crew", session)

        # Phase 4: Driver form & anomalies
        console.info(f"\n{'🔍'*20}")
        console.info("PHASE 4: DRIVER FORM & ANOMALY DETECTION")
        console.info(f"{'🔍'*20}")
        driver_crew, _ = build_driver_anomaly_crew(agents, event)
        run_crew_safe(driver_crew, "Driver & Anomaly Crew", session)

        # Phase 5: Predictions
        console.info(f"\n{'🔮'*20}")
        console.info("PHASE 5: RACE PREDICTIONS")
        console.info(f"{'🔮'*20}")
        pred_crew, _ = build_prediction_crew(agents, event)
        run_crew_safe(pred_crew, "Prediction Crew", session)

        # Phase 6: Synthesis
        console.info(f"\n{'⭐'*20}")
        console.info("PHASE 6: SYNTHESIS & INTELLIGENCE REPORT")
        console.info(f"{'⭐'*20}")
        synth_crew, _ = build_synthesis_crew(agents)
        run_crew_safe(synth_crew, "Synthesis Crew", session)

    # ── Final summary ───────────────────────────────────────────────────
    summary = session.final_summary()
    log_research_summary(summary)
    
    console.info(f"\n{'═'*60}")
    console.info(f"✅ {Colors.GREEN}Research Session Complete{Colors.RESET}")
    console.info(f"{'═'*60}")
    console.info(f"⏱️  Total Duration: {Colors.CYAN}{summary['duration_min']} minutes{Colors.RESET}")
    console.info(f"📊 Crews Run:      {Colors.CYAN}{len(summary['crews_run'])}{Colors.RESET}")
    console.info(f"❌ Errors:         {Colors.RED if summary['errors_count'] > 0 else Colors.GREEN}{summary['errors_count']}{Colors.RESET}")
    console.info(f"💡 Insights:       {Colors.YELLOW}insights/ directory{Colors.RESET}")
    console.info(f"📁 Full Logs:      {Colors.YELLOW}{SESSION_DIR}{Colors.RESET}")
    console.info(f"{'═'*60}\n")
    
    # List published insight files
    insights_dir = Path("insights")
    if insights_dir.exists():
        files = list(insights_dir.glob("*.md"))
        if files:
            console.info("📁 Published Insights:")
            for f in sorted(files)[-5:]:
                console.info(f"   └─ {f.name}")
    
    return summary


# ── Autonomous Loop Mode ─────────────────────────────────────────────────────
def run_autonomous_loop(interval_hours: float = 6, event: str = None):
    """
    Run the research program continuously, re-running every N hours.
    Perfect for 24/7 autonomous F1 research during a race weekend.
    """
    console.info(f"🔄 Starting AUTONOMOUS LOOP mode (interval: {interval_hours}h)")
    console.info("   Press Ctrl+C to stop gracefully\n")
    
    cycle = 0
    while True:
        cycle += 1
        console.info(f"\n{'🏁'*30}")
        console.info(f"AUTONOMOUS RESEARCH CYCLE #{cycle}")
        console.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        console.info(f"{'🏁'*30}\n")
        
        # Re-detect event each cycle (race weekend might change)
        current_event = event or detect_recent_event()
        
        try:
            run_full_research(event=current_event, mode="full")
        except KeyboardInterrupt:
            console.info("\n🛑 Graceful shutdown requested.")
            break
        except Exception as e:
            log_error("AUTONOMOUS_LOOP", e, f"Cycle {cycle} failed")
            console.error(f"❌ Cycle {cycle} error: {e}")
        
        next_run = datetime.now() + timedelta(hours=interval_hours)
        console.info(f"\n💤 Next run at: {Colors.CYAN}{next_run.strftime('%H:%M:%S')}{Colors.RESET}")
        console.info(f"   Sleeping for {interval_hours * 3600:.0f} seconds...")
        
        try:
            time.sleep(interval_hours * 3600)
        except KeyboardInterrupt:
            console.info("\n🛑 Loop interrupted by user.")
            break


# ── CLI ──────────────────────────────────────────────────────────────────────
def parse_args():
    parser = argparse.ArgumentParser(
        description="F1 Autonomous Research Program",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                                  # Full research on most recent race
  python main.py --event 1                       # Research on round 1 (Bahrain)
  python main.py --event "Monaco"                # Research on Monaco GP
  python main.py --mode quick                    # Quick analysis (3 crews)
  python main.py --mode single --crew telemetry  # Just telemetry analysis
  python main.py --mode single --crew predict    # Just predictions
  python main.py --mode loop --interval 6        # Autonomous loop every 6 hours
  
Crew options for --crew: news | telemetry | strategy | drivers | predict | synthesis
        """
    )
    parser.add_argument("--event",    default=None,    help="Race round number or name")
    parser.add_argument("--mode",     default="full",  choices=["full", "quick", "single", "loop"])
    parser.add_argument("--crew",     default=None,    help="Specific crew (for --mode single)")
    parser.add_argument("--interval", default=6.0,     type=float, help="Hours between loop cycles")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    
    if args.mode == "loop":
        run_autonomous_loop(interval_hours=args.interval, event=args.event)
    else:
        run_full_research(
            event=args.event,
            mode=args.mode,
            specific_crew=args.crew,
        )
