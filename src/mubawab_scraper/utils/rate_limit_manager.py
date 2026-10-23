"""
Gestion centralisée du rate limiting Mubawab.
Persiste l'état sur disque pour survivre aux redémarrages.
"""
import json
import os
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from mubawab_scraper.config import settings

log = logging.getLogger(__name__)

STATE_FILE = Path("data/.rate_limit_state.json")


class RateLimitManager:
    """
    Gère le rate limiting avec persistance.
    
    Fonctionnalités :
    - Lecture des headers Retry-After (int ou HTTP-date)
    - Backoff exponentiel si pas de header
    - Persistance sur disque (survit aux redémarrages)
    - Escalade automatique si 429 répétés
    """

    def __init__(self, state_file: Path = STATE_FILE):
        self.state_file = state_file
        self.state = self._load_state()
        self.consecutive_429 = self.state.get("consecutive_429", 0)
        self.last_429_at: Optional[datetime] = None

        # Si on est encore dans une période de blocage, on attend
        self._check_pending_block()

    # ─────────────────────────────────────────────
    # PERSISTANCE
    # ─────────────────────────────────────────────
    def _load_state(self) -> dict:
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text())
            except Exception:
                pass
        return {}

    def _save_state(self):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(self.state, indent=2))

    # ─────────────────────────────────────────────
    # VÉRIFICATION AU DÉMARRAGE
    # ─────────────────────────────────────────────
    def _check_pending_block(self):
        """Si un blocage est encore actif, attend automatiquement."""
        until_str = self.state.get("block_until")
        if not until_str:
            return

        until = datetime.fromisoformat(until_str)
        remaining = (until - datetime.utcnow()).total_seconds()

        if remaining > 0:
            log.warning(
                f"🚫 Blocage actif encore {remaining:.0f}s "
                f"(jusqu'à {until.isoformat()})"
            )
            self._interruptible_sleep(remaining)
        else:
            # Blocage expiré, on nettoie
            self.state.pop("block_until", None)
            self._save_state()

    # ─────────────────────────────────────────────
    # DÉTECTION 429
    # ─────────────────────────────────────────────
    def check_response(self, status_code: int, headers: dict) -> bool:
        """
        Analyse la réponse HTTP.
        Retourne True si rate limited, False sinon.
        """
        if status_code != 429:
            # Reset progressif du compteur si succès
            if self.consecutive_429 > 0:
                self.consecutive_429 = 0
                self.state["consecutive_429"] = 0
                self._save_state()
            return False

        # 429 détecté
        self.consecutive_429 += 1
        self.state["consecutive_429"] = self.consecutive_429
        self.last_429_at = datetime.utcnow()

        # Lire Retry-After (int ou HTTP-date)
        retry_after = self._parse_retry_after(headers)

        # Escalade selon le nombre de 429 consécutifs
        if self.consecutive_429 >= 3:
            # 3 fois de suite → doublement punitif
            retry_after = max(retry_after, 3600 * 6)  # 6h minimum
            log.error(
                f"🚨 3 × 429 consécutifs → blocage renforcé {retry_after}s"
            )

        # Appliquer le blocage
        self._apply_block(retry_after)
        return True

    def _parse_retry_after(self, headers: dict) -> int:
        """Parse Retry-After (int en secondes OU HTTP-date)."""
        raw = headers.get("Retry-After") or headers.get("retry-after")
        if not raw:
            # Pas de header → backoff exponentiel
            backoff = min(300 * (2 ** self.consecutive_429), 7200)
            log.warning(f"⚠️ 429 sans Retry-After → backoff {backoff}s")
            return backoff

        raw = str(raw).strip()

        # Cas 1 : entier (secondes)
        if raw.isdigit():
            return int(raw)

        # Cas 2 : HTTP-date (RFC 7231)
        try:
            from email.utils import parsedate_to_datetime
            target = parsedate_to_datetime(raw)
            now = datetime.now(target.tzinfo)
            delta = (target - now).total_seconds()
            return max(int(delta), 60)
        except Exception:
            log.warning(f"⚠️ Retry-After illisible: {raw}")
            return 300

    # ─────────────────────────────────────────────
    # APPLICATION DU BLOCAGE
    # ─────────────────────────────────────────────
    def _apply_block(self, seconds: int):
        """Enregistre le blocage et attend."""
        # Ajouter marge de sécurité (+10% + 60s)
        wait = int(seconds * 1.1 + 60)

        until = datetime.utcnow() + timedelta(seconds=wait)
        self.state["block_until"] = until.isoformat()
        self.state["last_429_at"] = datetime.utcnow().isoformat()
        self.state["last_retry_after"] = seconds
        self._save_state()

        log.warning(
            f"⏸️  Rate limit → attente {wait}s "
            f"({wait/60:.1f} min) jusqu'à {until.isoformat()}"
        )

        self._interruptible_sleep(wait)

    def _interruptible_sleep(self, seconds: int):
        """
        Dort en affichant la progression (Ctrl+C possible).
        Si Ctrl+C → sauvegarde l'état pour reprise.
        """
        from rich.progress import Progress, TimeRemainingColumn

        try:
            with Progress() as progress:
                task = progress.add_task(
                    "[yellow]⏸️  Attente post-429...",
                    total=seconds,
                )
                for _ in range(seconds):
                    time.sleep(1)
                    progress.update(task, advance=1)
        except KeyboardInterrupt:
            log.warning("⚠️ Interruption manuelle, état sauvegardé")
            self._save_state()
            raise

    # ─────────────────────────────────────────────
    # DÉLAI ENTRE REQUÊTES (jitter)
    # ─────────────────────────────────────────────
    def polite_delay(self):
        """Délai entre deux requêtes (avec jitter)."""
        import random
        delay = random.uniform(
            settings.min_delay, settings.max_delay
        )
        time.sleep(delay)

    def reset(self):
        """Reset manuel de l'état."""
        self.state = {}
        self.consecutive_429 = 0
        self._save_state()
        log.info("✅ État rate limit réinitialisé")