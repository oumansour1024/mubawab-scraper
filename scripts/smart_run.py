#!/usr/bin/env python
"""
Lance le scraper UNIQUEMENT si l'état rate limit le permet.
"""
import subprocess
import sys
from pathlib import Path
from datetime import datetime

STATE_FILE = Path("data/.rate_limit_state.json")


def is_blocked() -> tuple[bool, int]:
    """Retourne (est_bloqué, secondes_restantes)."""
    if not STATE_FILE.exists():
        return False, 0

    import json
    state = json.loads(STATE_FILE.read_text())
    until_str = state.get("block_until")
    if not until_str:
        return False, 0

    until = datetime.fromisoformat(until_str)
    remaining = (until - datetime.utcnow()).total_seconds()

    if remaining > 0:
        return True, int(remaining)
    return False, 0


def main():
    blocked, remaining = is_blocked()

    if blocked:
        mins = remaining / 60
        print(f"🚫 Blocage actif : {mins:.1f} min restantes")
        print(f"   Prochaine tentative possible à "
              f"{(datetime.utcnow().timestamp() + remaining):.0f}")
        print("   ⏭️  Skip ce run.")
        sys.exit(0)

    print("✅ Pas de blocage, lancement du scraper...")
    result = subprocess.run(
        [sys.executable, "-m", "mubawab_scraper", "details",
         "--transaction", "all",
         "--city", "all",
         "--limit", "0",
         "--workers", "4"],
        cwd=Path(__file__).parent.parent,
    )
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()