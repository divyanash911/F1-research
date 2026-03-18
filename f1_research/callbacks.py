"""
F1 Research Program - CrewAI Callback Integration
Hooks into CrewAI's execution pipeline for fine-grained logging
of every agent action, tool call, and LLM response.
"""

import time
import json
from typing import Any, Optional, Union
from datetime import datetime
from crewai.utilities.events import (
    crewai_event_bus,
    AgentExecutionCompletedEvent,
    TaskCompletedEvent,
    CrewKickoffStartedEvent,
    CrewKickoffCompletedEvent,
)
from logger import (
    log_agent_message, log_tool_call, log_llm_response,
    log_insight, log_prediction, console, Colors,
    agent_logger, tool_logger, llm_logger, debate_logger
)


class F1ResearchCallbackHandler:
    """
    Hooks into CrewAI event bus to log all agent activities.
    Provides fine-grained tracing of the research process.
    """
    
    def __init__(self):
        self._active_tools: dict = {}
        self._crew_start: float = 0
        self._task_counter: int = 0
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Register all event handlers."""
        try:
            @crewai_event_bus.on(CrewKickoffStartedEvent)
            def on_crew_start(source, event):
                self._crew_start = time.time()
                console.info(f"🚀 Crew started: {Colors.CYAN}{getattr(source, 'name', 'Unknown Crew')}{Colors.RESET}")
                agent_logger.info(
                    f"\n{'═'*70}\n"
                    f"CREW STARTED: {getattr(source, 'name', 'Unknown')}\n"
                    f"Time: {datetime.now().isoformat()}\n"
                    f"{'═'*70}\n"
                )
            
            @crewai_event_bus.on(CrewKickoffCompletedEvent)
            def on_crew_complete(source, event):
                duration = time.time() - self._crew_start
                console.info(
                    f"✅ Crew completed in {Colors.YELLOW}{duration:.1f}s{Colors.RESET}"
                )
                agent_logger.info(
                    f"\n{'═'*70}\n"
                    f"CREW COMPLETED | Duration: {duration:.1f}s\n"
                    f"Output: {str(getattr(event, 'output', ''))[:500]}\n"
                    f"{'═'*70}\n"
                )
            
            @crewai_event_bus.on(TaskCompletedEvent)
            def on_task_complete(source, event):
                self._task_counter += 1
                task  = getattr(event, 'task', None)
                output = getattr(event, 'output', '')
                agent = getattr(task, 'agent', None)
                role  = getattr(agent, 'role', 'Unknown Agent') if agent else 'Unknown'
                
                log_agent_message(
                    agent_name=role,
                    message_type="TASK_COMPLETE",
                    content=str(output)[:2000]
                )
            
            @crewai_event_bus.on(AgentExecutionCompletedEvent)
            def on_agent_exec(source, event):
                agent = getattr(event, 'agent', source)
                role  = getattr(agent, 'role', 'Unknown') if agent else 'Unknown'
                output = str(getattr(event, 'output', ''))
                
                llm_logger.info(
                    f"\n{'─'*60}\n"
                    f"AGENT EXECUTION COMPLETED | {role}\n"
                    f"Output: {output[:1000]}\n"
                )
        
        except Exception as e:
            console.warning(f"⚠️  Could not set up all event handlers: {e}")
            console.warning("   (Some logging may be limited — this is non-fatal)")


# Instantiate the handler so it registers on import
_handler = None

def setup_callbacks():
    """Call this to initialize all CrewAI logging callbacks."""
    global _handler
    _handler = F1ResearchCallbackHandler()
    console.info("📡 CrewAI logging callbacks initialized")
    return _handler


# ── Standalone tool call wrapper ─────────────────────────────────────────────
def logged_tool_call(agent_name: str, tool_fn, *args, **kwargs):
    """
    Wrapper that logs tool calls with timing.
    Usage: result = logged_tool_call("TelemetryAgent", analyze_lap_times, event="1")
    """
    start  = time.time()
    tool_name = getattr(tool_fn, 'name', tool_fn.__name__ if hasattr(tool_fn, '__name__') else str(tool_fn))
    
    console.debug(f"🔧 {agent_name} calling: {Colors.ORANGE}{tool_name}{Colors.RESET}")
    
    try:
        result   = tool_fn(*args, **kwargs)
        duration = (time.time() - start) * 1000
        
        log_tool_call(
            agent_name=agent_name,
            tool_name=tool_name,
            inputs={**kwargs},
            output=result,
            duration_ms=duration,
        )
        return result
    
    except Exception as e:
        duration = (time.time() - start) * 1000
        log_tool_call(
            agent_name=agent_name,
            tool_name=tool_name,
            inputs={**kwargs},
            output=f"ERROR: {e}",
            duration_ms=duration,
        )
        raise
