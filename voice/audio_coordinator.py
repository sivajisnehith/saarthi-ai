"""
Saarthi AI Audio Playback Coordinator Module.

Guarantees single-producer audio playback over the Exotel WebSocket media stream:
1. Only one TTS producer can send PCM frames to Exotel at any moment (via per-call asyncio.Lock).
2. Mutual exclusion between progress speech, final response speech, greetings, and error speech.
3. Every playback task has a unique turn_id and audio_generation_id.
4. Stale or cancelled generations silently drop remaining audio frames.
5. Instant barge-in cancellation and lock release.
6. Structured concurrency audit logs:
   - AUDIO ACQUIRE: <type> turn=<id>
   - AUDIO RELEASE: <type> turn=<id>
   - AUDIO CANCELLED: <type> turn=<id>
   - AUDIO STALE DROP: <type> turn=<id>
   - AUDIO OVERLAP PREVENTED: existing=<type> new=<type>
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional, Set

logger = logging.getLogger("saarthi.voice.coordinator")


class AudioPlaybackCoordinator:
    """
    Coordinates and arbitrates all audio playback tasks for a single telephone call.
    Prevents audio overlap, chunk interleaving, and race conditions.
    """

    def __init__(self):
        self._lock = asyncio.Lock()
        self.active_turn_id: int = 0
        self.active_generation_id: int = 0
        self._generation_counter: int = 0

        self.current_holder_type: Optional[str] = None
        self.current_holder_turn: Optional[int] = None
        self.current_holder_gen_id: Optional[int] = None

        self.cancel_event: asyncio.Event = asyncio.Event()
        self._cancelled_generations: Set[int] = set()
        self._logged_cancelled_generations: Set[int] = set()
        self._active_tasks: Set[asyncio.Task] = set()

    def register_task(self, task: asyncio.Task) -> asyncio.Task:
        """Tracks an active playback task for clean cancellation."""
        self._active_tasks.add(task)
        task.add_done_callback(self._active_tasks.discard)
        return task

    def new_generation(self, playback_type: str, turn_id: int) -> int:
        """
        Creates and returns a new unique audio_generation_id for a TTS task.
        """
        self._generation_counter += 1
        gen_id = self._generation_counter
        if self.active_turn_id == 0:
            self.active_turn_id = turn_id
        if self.active_turn_id == turn_id and self.active_generation_id == 0:
            self.active_generation_id = gen_id
        return gen_id

    def start_new_turn(self, turn_id: int) -> int:
        """
        Starts a new customer turn.
        Cancels all previous turn tasks and marks previous generations as stale.
        """
        self.active_turn_id = turn_id

        # Cancel active producer if one is holding the lock
        if self.current_holder_gen_id:
            self._cancelled_generations.add(self.current_holder_gen_id)
            if self.current_holder_type and self.current_holder_turn is not None:
                self.log_cancelled(self.current_holder_type, self.current_holder_turn, self.current_holder_gen_id)

        self._generation_counter += 1
        self.active_generation_id = 0

        # Signal cancellation to active producers
        self.cancel_event.set()
        self.cancel_active_tasks(reason=f"new_turn_{turn_id}")

        # Fresh cancel event for the new turn
        self.cancel_event = asyncio.Event()
        return self._generation_counter

    def cancel_active_playback(self, source: str = "barge-in"):
        """
        Immediately cancels all active playback tasks and signals cancel event.
        Releases the lock as soon as the active producer exits.
        """
        self.cancel_event.set()
        if self.current_holder_gen_id:
            self._cancelled_generations.add(self.current_holder_gen_id)
            if self.current_holder_type and self.current_holder_turn is not None:
                self.log_cancelled(self.current_holder_type, self.current_holder_turn, self.current_holder_gen_id)
        self.cancel_active_tasks(reason=source)

    def cancel_generation(self, turn_id: int, generation_id: int, playback_type: str):
        """Cancels a specific generation (e.g. progress TTS cancelled in favor of final)."""
        self._cancelled_generations.add(generation_id)
        self.log_cancelled(playback_type, turn_id, generation_id)

    def log_cancelled(self, playback_type: str, turn_id: int, generation_id: int):
        """Logs AUDIO CANCELLED at most once per generation."""
        if generation_id not in self._logged_cancelled_generations:
            self._logged_cancelled_generations.add(generation_id)
            logger.info("AUDIO CANCELLED: %s turn=%s", playback_type, turn_id)

    def cancel_active_tasks(self, reason: str = "cancel"):
        """Cancels all registered active tasks."""
        for task in list(self._active_tasks):
            if not task.done():
                task.cancel()

    def is_cancelled(self, turn_id: int, generation_id: int) -> bool:
        """Returns True if the generation or call is cancelled."""
        return (
            self.cancel_event.is_set()
            or generation_id in self._cancelled_generations
        )

    def is_stale(self, turn_id: int, generation_id: int) -> bool:
        """Returns True if the generation belongs to an older turn."""
        return turn_id != self.active_turn_id

    def is_generation_active(self, turn_id: int, generation_id: int) -> bool:
        """
        Verifies that this generation is still the active, valid generation.
        Returns False if cancelled, stale turn, or superseded.
        """
        if self.is_cancelled(turn_id, generation_id):
            return False
        if self.is_stale(turn_id, generation_id):
            return False
        # If another generation is currently holding the lock, this generation is not active
        if self.current_holder_gen_id is not None and self.current_holder_gen_id != generation_id:
            return False
        return True

    @asynccontextmanager
    async def acquire_playback(self, playback_type: str, turn_id: int, generation_id: int):
        """
        Exclusive playback lock acquisition.
        Guarantees that only ONE producer can send PCM frames to Exotel at any instant.
        """
        # Detect if another producer is holding the lock
        if self._lock.locked() and self.current_holder_type:
            logger.info(
                "AUDIO OVERLAP PREVENTED: existing=%s new=%s",
                self.current_holder_type,
                playback_type,
            )

        # Acquire exclusive lock
        try:
            await self._lock.acquire()
        except asyncio.CancelledError:
            self.log_cancelled(playback_type, turn_id, generation_id)
            raise

        # Check if generation was cancelled or invalidated while waiting for the lock
        if not self.is_generation_active(turn_id, generation_id):
            self._lock.release()
            logger.info("AUDIO STALE DROP: %s turn=%s", playback_type, turn_id)
            self.log_cancelled(playback_type, turn_id, generation_id)
            raise asyncio.CancelledError(f"Stale generation {generation_id} for turn {turn_id}")

        self.current_holder_type = playback_type
        self.current_holder_turn = turn_id
        self.current_holder_gen_id = generation_id
        self.active_generation_id = generation_id

        logger.info("AUDIO ACQUIRE: %s turn=%s", playback_type, turn_id)
        try:
            yield
        except asyncio.CancelledError:
            self.log_cancelled(playback_type, turn_id, generation_id)
            raise
        except Exception as e:
            logger.exception("Error during audio playback for %s turn=%s: %s", playback_type, turn_id, e)
            raise
        finally:
            self.current_holder_type = None
            self.current_holder_turn = None
            self.current_holder_gen_id = None
            self._lock.release()
            logger.info("AUDIO RELEASE: %s turn=%s", playback_type, turn_id)
