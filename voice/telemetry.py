"""
Voice Pipeline Latency Audit and Monotonic Instrumentation Module.
Captures sub-millisecond timestamps using time.perf_counter() across every phase:
STT -> Agent Scheduling -> Bedrock -> Tools -> TTS -> Exotel Audio Playback.
"""
import logging
import time
from typing import Dict, List, Optional, Any

logger = logging.getLogger("saarthi.voice.telemetry")


class ToolCallRecord:
    def __init__(self, name: str, start_ts: float):
        self.name = name
        self.start_ts = start_ts
        self.end_ts: Optional[float] = None
        self.duration_ms: float = 0.0

    def complete(self, end_ts: float, duration_s: Optional[float] = None):
        self.end_ts = end_ts
        if duration_s is not None:
            self.duration_ms = round(duration_s * 1000, 2)
        else:
            self.duration_ms = round((end_ts - self.start_ts) * 1000, 2)


class TurnMetrics:
    def __init__(self, turn_id: int):
        self.turn_id = turn_id
        # A. Customer speech
        self.speech_start_ts: Optional[float] = None
        self.speech_end_ts: Optional[float] = None
        # B. STT Finalization
        self.transcript_final_ts: Optional[float] = None
        self.customer_text: str = ""
        # C. Agent Scheduling
        self.agent_start_ts: Optional[float] = None
        # D & E. Bedrock / Tools
        self.model_calls_count: int = 0
        self.model_durations_ms: List[float] = []
        self.current_model_start_ts: Optional[float] = None
        self.tool_calls: List[ToolCallRecord] = []
        # F. Agent Total
        self.agent_end_ts: Optional[float] = None
        self.agent_response_text: str = ""
        # G. TTS
        self.tts_request_start_ts: Optional[float] = None
        self.tts_network_received_ts: Optional[float] = None
        self.tts_pcm_ready_ts: Optional[float] = None
        self.tts_stream_complete_ts: Optional[float] = None
        self.tts_bytes: int = 0
        # H. Playback
        self.first_chunk_ts: Optional[float] = None
        self.last_chunk_ts: Optional[float] = None
        self.total_chunks: int = 0
        self.interrupted: bool = False
        self.interrupted_reason: str = ""

    # Computed metrics in milliseconds
    @property
    def stt_duration_ms(self) -> Optional[float]:
        if self.speech_start_ts and self.speech_end_ts:
            return round((self.speech_end_ts - self.speech_start_ts) * 1000, 2)
        return None

    @property
    def stt_final_latency_ms(self) -> Optional[float]:
        if self.transcript_final_ts:
            ref = self.speech_end_ts or self.speech_start_ts
            if ref:
                return round((self.transcript_final_ts - ref) * 1000, 2)
        return None

    @property
    def agent_start_delay_ms(self) -> Optional[float]:
        if self.agent_start_ts and self.transcript_final_ts:
            return round((self.agent_start_ts - self.transcript_final_ts) * 1000, 2)
        return None

    @property
    def bedrock_total_ms(self) -> float:
        if self.model_durations_ms:
            return round(sum(self.model_durations_ms), 2)
        return 0.0

    @property
    def agent_total_ms(self) -> Optional[float]:
        if self.agent_start_ts and self.agent_end_ts:
            return round((self.agent_end_ts - self.agent_start_ts) * 1000, 2)
        return None

    @property
    def tts_first_audio_ms(self) -> Optional[float]:
        if self.tts_request_start_ts and self.tts_pcm_ready_ts:
            return round((self.tts_pcm_ready_ts - self.tts_request_start_ts) * 1000, 2)
        return None

    @property
    def tts_total_ms(self) -> Optional[float]:
        if self.tts_request_start_ts:
            if self.tts_stream_complete_ts:
                return round((self.tts_stream_complete_ts - self.tts_request_start_ts) * 1000, 2)
            if self.tts_pcm_ready_ts:
                return round((self.tts_pcm_ready_ts - self.tts_request_start_ts) * 1000, 2)
        return None

    @property
    def playback_ms(self) -> Optional[float]:
        if self.first_chunk_ts and self.last_chunk_ts:
            return round((self.last_chunk_ts - self.first_chunk_ts) * 1000, 2)
        return None

    @property
    def response_latency_ms(self) -> Optional[float]:
        """Total perceived response latency: transcript.final -> first outbound audio chunk"""
        if self.first_chunk_ts and self.transcript_final_ts:
            return round((self.first_chunk_ts - self.transcript_final_ts) * 1000, 2)
        return None

    def format_log(self) -> str:
        lines = [f"VOICE TURN {self.turn_id}"]
        if self.stt_duration_ms is not None:
            lines.append(f"  STT_DURATION_MS={self.stt_duration_ms:.0f}")
        if self.stt_final_latency_ms is not None:
            lines.append(f"  STT_FINAL_LATENCY_MS={self.stt_final_latency_ms:.0f}")
        if self.agent_start_delay_ms is not None:
            lines.append(f"  AGENT_START_DELAY_MS={self.agent_start_delay_ms:.0f}")
        if self.bedrock_total_ms > 0:
            lines.append(f"  BEDROCK_TOTAL_MS={self.bedrock_total_ms:.0f}")
        for tc in self.tool_calls:
            clean_name = tc.name.upper().replace("-", "_")
            lines.append(f"  TOOL_{clean_name}_MS={tc.duration_ms:.0f}")
        if self.agent_total_ms is not None:
            lines.append(f"  AGENT_TOTAL_MS={self.agent_total_ms:.0f}")
        if self.tts_first_audio_ms is not None:
            lines.append(f"  TTS_FIRST_AUDIO_MS={self.tts_first_audio_ms:.0f}")
        if self.tts_total_ms is not None:
            lines.append(f"  TTS_TOTAL_MS={self.tts_total_ms:.0f}")
        if self.playback_ms is not None:
            lines.append(f"  PLAYBACK_MS={self.playback_ms:.0f}")
        if self.response_latency_ms is not None:
            lines.append(f"  RESPONSE_LATENCY_MS={self.response_latency_ms:.0f}")
        if self.interrupted:
            lines.append(f"  STATUS=INTERRUPTED ({self.interrupted_reason})")
        return "\n".join(lines)


class CallTelemetry:
    def __init__(self, call_sid: str = ""):
        self.call_sid = call_sid
        self.call_start_ts: float = time.perf_counter()
        self.call_end_ts: Optional[float] = None
        self.turns: Dict[int, TurnMetrics] = {}
        self._current_speech_start_ts: Optional[float] = None
        self._current_speech_end_ts: Optional[float] = None

    def get_or_create_turn(self, turn_id: int) -> TurnMetrics:
        if turn_id not in self.turns:
            self.turns[turn_id] = TurnMetrics(turn_id)
        return self.turns[turn_id]

    def on_speech_start(self, utterance_idx: Optional[int] = None):
        self._current_speech_start_ts = time.perf_counter()

    def on_speech_end(self, utterance_idx: Optional[int] = None):
        self._current_speech_end_ts = time.perf_counter()

    def on_transcript_final(self, turn_id: int, text: str):
        now = time.perf_counter()
        turn = self.get_or_create_turn(turn_id)
        turn.transcript_final_ts = now
        turn.customer_text = text
        turn.speech_start_ts = self._current_speech_start_ts
        turn.speech_end_ts = self._current_speech_end_ts
        # Reset speech markers for next utterance
        self._current_speech_start_ts = None
        self._current_speech_end_ts = None

    def on_agent_start(self, turn_id: int):
        now = time.perf_counter()
        turn = self.get_or_create_turn(turn_id)
        turn.agent_start_ts = now

    def on_model_start(self, turn_id: int):
        now = time.perf_counter()
        turn = self.get_or_create_turn(turn_id)
        turn.current_model_start_ts = now
        turn.model_calls_count += 1

    def on_model_end(self, turn_id: int):
        now = time.perf_counter()
        turn = self.get_or_create_turn(turn_id)
        if turn.current_model_start_ts:
            duration_ms = (now - turn.current_model_start_ts) * 1000
            turn.model_durations_ms.append(duration_ms)
            turn.current_model_start_ts = None

    def on_tool_start(self, turn_id: int, tool_name: str):
        now = time.perf_counter()
        turn = self.get_or_create_turn(turn_id)
        record = ToolCallRecord(tool_name, now)
        turn.tool_calls.append(record)

    def on_tool_end(self, turn_id: int, tool_name: str, duration_s: Optional[float] = None):
        now = time.perf_counter()
        turn = self.get_or_create_turn(turn_id)
        for tc in reversed(turn.tool_calls):
            if tc.name == tool_name and tc.end_ts is None:
                tc.complete(now, duration_s)
                break

    def on_agent_end(self, turn_id: int, response_text: str):
        now = time.perf_counter()
        turn = self.get_or_create_turn(turn_id)
        turn.agent_end_ts = now
        turn.agent_response_text = response_text

    def on_tts_start(self, turn_id: int):
        now = time.perf_counter()
        turn = self.get_or_create_turn(turn_id)
        turn.tts_request_start_ts = now

    def on_tts_audio_ready(self, turn_id: int, pcm_bytes_len: int):
        now = time.perf_counter()
        turn = self.get_or_create_turn(turn_id)
        turn.tts_pcm_ready_ts = now
        turn.tts_bytes = pcm_bytes_len

    def on_tts_stream_complete(self, turn_id: int, total_bytes: int):
        now = time.perf_counter()
        turn = self.get_or_create_turn(turn_id)
        turn.tts_stream_complete_ts = now
        turn.tts_bytes = total_bytes

    def on_first_chunk_sent(self, turn_id: int):
        now = time.perf_counter()
        turn = self.get_or_create_turn(turn_id)
        turn.first_chunk_ts = now

    def on_last_chunk_sent(self, turn_id: int, total_chunks: int):
        now = time.perf_counter()
        turn = self.get_or_create_turn(turn_id)
        turn.last_chunk_ts = now
        turn.total_chunks = total_chunks
        # Log completed turn
        logger.info("\n" + turn.format_log())

    def on_turn_interrupted(self, turn_id: int, reason: str = "barge-in"):
        now = time.perf_counter()
        turn = self.get_or_create_turn(turn_id)
        turn.interrupted = True
        turn.interrupted_reason = reason
        if not turn.last_chunk_ts and turn.first_chunk_ts:
            turn.last_chunk_ts = now
        logger.info("\n" + turn.format_log())

    def end_call(self):
        self.call_end_ts = time.perf_counter()
        summary = self.format_call_summary()
        logger.info("\n" + summary)
        return summary

    def format_call_summary(self) -> str:
        end_ts = self.call_end_ts or time.perf_counter()
        total_call_duration_ms = (end_ts - self.call_start_ts) * 1000

        valid_turns = [t for t in self.turns.values() if t.turn_id > 0]
        completed_turns = len(valid_turns)

        stt_finals = [t.stt_final_latency_ms for t in valid_turns if t.stt_final_latency_ms is not None]
        avg_stt_final = sum(stt_finals) / len(stt_finals) if stt_finals else 0.0

        agent_latencies = [t.agent_total_ms for t in valid_turns if t.agent_total_ms is not None]
        avg_agent = sum(agent_latencies) / len(agent_latencies) if agent_latencies else 0.0

        all_tool_durations = [
            tc.duration_ms for t in valid_turns for tc in t.tool_calls if tc.duration_ms > 0
        ]
        avg_tool = sum(all_tool_durations) / len(all_tool_durations) if all_tool_durations else 0.0

        tts_first_audios = [t.tts_first_audio_ms for t in valid_turns if t.tts_first_audio_ms is not None]
        avg_tts_first = sum(tts_first_audios) / len(tts_first_audios) if tts_first_audios else 0.0

        response_latencies = [t.response_latency_ms for t in valid_turns if t.response_latency_ms is not None]
        avg_response = sum(response_latencies) / len(response_latencies) if response_latencies else 0.0

        speech_durations = [t.stt_duration_ms for t in valid_turns if t.stt_duration_ms is not None]
        total_speech = sum(speech_durations)

        playback_durations = [t.playback_ms for t in valid_turns if t.playback_ms is not None]
        total_playback = sum(playback_durations)

        # Estimated wait time: total time caller spent waiting between speech_end and first outbound audio
        estimated_wait = sum(response_latencies)

        lines = [
            "CALL LATENCY SUMMARY",
            f"  turns={completed_turns}",
            f"  avg_stt_final_latency_ms={avg_stt_final:.0f}",
            f"  avg_agent_latency_ms={avg_agent:.0f}",
            f"  avg_tool_latency_ms={avg_tool:.0f}",
            f"  avg_tts_first_audio_ms={avg_tts_first:.0f}",
            f"  avg_response_latency_ms={avg_response:.0f}",
            f"  total_call_duration_ms={total_call_duration_ms:.0f}",
            f"  total_customer_speech_ms={total_speech:.0f}",
            f"  total_saarthi_playback_ms={total_playback:.0f}",
            f"  estimated_wait_time_ms={estimated_wait:.0f}",
        ]
        return "\n".join(lines)


def attach_strands_telemetry(
    agent: Any,
    telemetry: CallTelemetry,
    turn_id_provider: Any,
    before_tool_callback: Optional[Any] = None,
):
    """
    Attaches Strands hook callbacks to monitor Bedrock model and tool invocations,
    with support for pre-tool progress message execution.
    """
    import inspect
    from strands.hooks import (
        BeforeModelCallEvent,
        AfterModelCallEvent,
        BeforeToolCallEvent,
        AfterToolCallEvent,
    )

    def _extract_tool_name(event: Any) -> str:
        tool_use = getattr(event, "tool_use", None)
        if isinstance(tool_use, dict):
            return tool_use.get("name", "unknown_tool")
        elif hasattr(tool_use, "name"):
            return str(tool_use.name)
        selected_tool = getattr(event, "selected_tool", None)
        if hasattr(selected_tool, "name"):
            return str(selected_tool.name)
        return "unknown_tool"

    def on_before_model(event: BeforeModelCallEvent):
        current_turn = turn_id_provider()
        telemetry.on_model_start(current_turn)

    def on_after_model(event: AfterModelCallEvent):
        current_turn = turn_id_provider()
        telemetry.on_model_end(current_turn)

    async def on_before_tool(event: BeforeToolCallEvent):
        current_turn = turn_id_provider()
        tool_name = _extract_tool_name(event)
        telemetry.on_tool_start(current_turn, tool_name)
        logger.info("TOOL START: %s (turn %s)", tool_name, current_turn)
        if before_tool_callback:
            try:
                if inspect.iscoroutinefunction(before_tool_callback):
                    await before_tool_callback(tool_name, current_turn)
                else:
                    before_tool_callback(tool_name, current_turn)
            except Exception as ex:
                logger.error("Error executing before_tool_callback for tool '%s': %s", tool_name, ex)

    def on_after_tool(event: AfterToolCallEvent):
        current_turn = turn_id_provider()
        tool_name = _extract_tool_name(event)
        duration = getattr(event, "duration", None)
        telemetry.on_tool_end(current_turn, tool_name, duration)
        dur_ms = (duration * 1000) if duration is not None else 0.0
        logger.info("TOOL COMPLETE: %s duration_ms=%.1f (turn %s)", tool_name, dur_ms, current_turn)

    agent.add_hook(BeforeModelCallEvent, on_before_model)
    agent.add_hook(AfterModelCallEvent, on_after_model)
    agent.add_hook(BeforeToolCallEvent, on_before_tool)
    agent.add_hook(AfterToolCallEvent, on_after_tool)
