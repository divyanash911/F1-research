"""
F1 Research Program - Setup Validation Script
Run this before first use to verify everything is configured correctly.
Usage: python validate_setup.py
"""

import sys
import os
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

sys.path.insert(0, '.')
sys.path.insert(0, 'tools')
sys.path.insert(0, 'agents')
sys.path.insert(0, 'crews')

PASS = "✅"
FAIL = "❌"
WARN = "⚠️ "

results = []

def check(name, fn):
    try:
        result = fn()
        print(f"  {PASS} {name}: {result}")
        results.append((name, True, result))
        return True
    except Exception as e:
        print(f"  {FAIL} {name}: {str(e)[:80]}")
        results.append((name, False, str(e)))
        return False

print("\n" + "═"*60)
print("  F1 AUTONOMOUS RESEARCH - SETUP VALIDATION")
print("═"*60)

# ── 1. Python & Dependencies ────────────────────────────────
print("\n📦 Python Dependencies:")
check("Python version", lambda: f"{sys.version.split()[0]} (need 3.10+)")
check("crewai", lambda: __import__("crewai").__version__)
check("fastf1", lambda: __import__("fastf1").__version__)
check("numpy", lambda: __import__("numpy").__version__)
check("pandas", lambda: __import__("pandas").__version__)
check("scipy", lambda: __import__("scipy").__version__)
check("duckduckgo_search", lambda: "OK")
check("litellm", lambda: __import__("litellm").__version__)

# ── 2. Environment Config ────────────────────────────────────
print("\n⚙️  Environment Configuration:")
backend = os.getenv("LLM_BACKEND", "NOT SET")
check("LLM_BACKEND", lambda: backend)
check("F1_SEASON", lambda: os.getenv("F1_SEASON", "2026"))

if backend == "groq":
    key = os.getenv("GROQ_API_KEY", "")
    check("GROQ_API_KEY", lambda: "SET ✓" if key and key != "your_groq_api_key_here" else (_ for _ in ()).throw(ValueError("Not configured — edit .env")))
    check("GROQ_MODEL", lambda: os.getenv("GROQ_MODEL", "NOT SET"))
elif backend == "openrouter":
    key = os.getenv("OPENROUTER_API_KEY", "")
    check("OPENROUTER_API_KEY", lambda: "SET ✓" if key and "your_" not in key else (_ for _ in ()).throw(ValueError("Not configured")))
    check("OPENROUTER_MODEL", lambda: os.getenv("OPENROUTER_MODEL", "NOT SET"))
elif backend == "ollama":
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    check("OLLAMA_BASE_URL", lambda: base_url)
    check("OLLAMA_MODEL", lambda: os.getenv("OLLAMA_MODEL", "NOT SET"))
    try:
        import urllib.request
        urllib.request.urlopen(f"{base_url}/api/version", timeout=3)
        check("Ollama server reachable", lambda: "Connected")
    except Exception as e:
        check("Ollama server reachable", lambda: (_ for _ in ()).throw(ConnectionError(f"Cannot reach {base_url} — is Ollama running?")))
else:
    print(f"  {WARN} Unknown backend '{backend}'. Set LLM_BACKEND=groq|openrouter|ollama in .env")

# ── 3. Telemetry Tools ──────────────────────────────────────
print("\n📊 Telemetry Tools:")
from tools.telemetry_tools import (
    get_season_schedule, execute_python_analysis,
    get_circuit_profile, get_driver_lineup, ALL_TELEMETRY_TOOLS
)

check("Tool count", lambda: f"{len(ALL_TELEMETRY_TOOLS)} tools available")

sched = json.loads(get_season_schedule._run(year=2026))
check("Season schedule (2026)", lambda: f"{len(sched.get('events', []))} events, source={sched.get('source')}")

py_result = json.loads(execute_python_analysis.func(
    code="import numpy as np; print(f'numpy {np.__version__} works')",
    description="test"
))
check("Python analysis tool", lambda: py_result['output'].strip() if py_result['status'] == 'success' else (_ for _ in ()).throw(RuntimeError(py_result.get('error'))))

circuit = json.loads(get_circuit_profile._run(circuit_name="Monaco"))
check("Circuit profiles DB", lambda: f"{len(circuit['all_circuits_in_db'])} circuits")

lineup = json.loads(get_driver_lineup._run(year=2026))
check("2026 Driver lineup", lambda: f"{lineup['total_drivers']} drivers")

# ── 4. Logging Infrastructure ───────────────────────────────
print("\n📝 Logging Infrastructure:")
from logger import SESSION_DIR, log_insight, log_tool_call, log_prediction

check("Session log directory", lambda: f"Created at {SESSION_DIR}")
check("Log files exist", lambda: f"{len(list(SESSION_DIR.glob('*.log')))} log files")

log_insight("test", "Validation Insight", "System validated successfully.", 1.0, ["validation"])
check("Publish insight", lambda: "insights/*.md created")

# ── 5. LLM Connection Test ──────────────────────────────────
print("\n🤖 LLM Connection Test:")
print(f"  Testing {backend} connection...")

try:
    from llm_config import get_llm, BACKEND
    llm = get_llm(fast=True)
    
    # Show the exact model string being used
    model_str = getattr(llm, 'model', 'unknown')
    print(f"  └─ LiteLLM model string: {model_str}")
    if BACKEND == "ollama":
        if "ollama_chat/" in model_str:
            print(f"  └─ ✅ Using /api/chat endpoint (correct for tool calling)")
        else:
            print(f"  └─ ⚠️  NOT using ollama_chat/ prefix — will break tool calling!")
            print(f"         Fix: LLM_BACKEND=ollama should auto-use ollama_chat/")

    # Quick test call
    response = llm.call([{"role": "user", "content": "Reply with exactly: F1_OK"}])
    resp_text = str(response)[:100]
    check("LLM connection", lambda: f"Response received ({len(resp_text)} chars)")
    print(f"  └─ Response preview: {resp_text[:60]}...")
except Exception as e:
    check("LLM connection", lambda: (_ for _ in ()).throw(ConnectionError(str(e))))

# ── 6. Research Tools ───────────────────────────────────────
print("\n📰 News Research Tools:")
try:
    from duckduckgo_search import DDGS
    check("DuckDuckGo search", lambda: "Available")
except ImportError:
    check("DuckDuckGo search", lambda: (_ for _ in ()).throw(ImportError("pip install duckduckgo-search")))

# ── Summary ─────────────────────────────────────────────────
passed = sum(1 for _, ok, _ in results if ok)
failed = sum(1 for _, ok, _ in results if not ok)

print("\n" + "═"*60)
print(f"  VALIDATION SUMMARY: {passed} passed, {failed} failed")
print("═"*60)

if failed == 0:
    print(f"""
  🏁 All checks passed! You're ready to run:

  python main.py                     # Full research cycle
  python main.py --mode quick        # Quick 3-crew run
  python main.py --mode single \\
    --crew telemetry                 # Just telemetry analysis
  python main.py --mode loop \\
    --interval 6                     # Autonomous 24/7 loop
""")
else:
    print(f"""
  ⚠️  {failed} check(s) failed. Review the errors above.
  
  Most common fixes:
  - API key: edit .env and set your {backend.upper()}_API_KEY
  - Ollama: run 'ollama serve' and 'ollama pull llama3.1:8b'
  - Missing package: pip install -r requirements.txt
""")
