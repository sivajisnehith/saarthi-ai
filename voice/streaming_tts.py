import asyncio
import base64
import json
import logging
import time
from typing import AsyncIterator, Optional

import websockets
import websockets.exceptions

from voice.key_manager import SarvamKeyManager, sarvam_key_manager

logger = logging.getLogger("saarthi.voice.streaming_tts")

SARVAM_STREAMING_TTS_WS_URL = "wss://api.sarvam.ai/text-to-speech/ws"


class SarvamStreamingTTSService:
    """
    Streaming TTS service utilizing Sarvam's WebSocket API (bulbul:v3).
    Yields progressive raw 8000 Hz, 16-bit mono little-endian PCM audio chunks
    as they are synthesized on Sarvam servers, reducing time-to-first-audio to ~300 ms.
    Supports key rotation across fallback API keys and instant cancellation on barge-in.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        key_manager: Optional[SarvamKeyManager] = None,
        model: str = "bulbul:v3",
        speaker: str = "kavya",
        target_language_code: str = "en-IN",
        speech_sample_rate: int = 8000,
        pace: float = 1.0,
        timeout_seconds: float = 10.0,
    ):
        if key_manager is not None:
            self.key_manager = key_manager
        elif api_key:
            self.key_manager = SarvamKeyManager(keys=[api_key])
        else:
            self.key_manager = sarvam_key_manager

        self.model = model
        self.speaker = speaker
        self.target_language_code = target_language_code
        self.speech_sample_rate = speech_sample_rate
        self.pace = pace
        self.timeout_seconds = timeout_seconds

    async def stream_pcm_chunks(
        self,
        text: str,
        cancel_event: Optional[asyncio.Event] = None,
        language_code: Optional[str] = None,
    ) -> AsyncIterator[bytes]:
        """
        Asynchronously streams raw 8000 Hz, 16-bit mono little-endian PCM audio chunks.
        Strips WAV headers on the first chunk and delivers PCM chunks immediately as they arrive.
        Checks cancel_event to abort network streaming immediately upon barge-in.
        """
        if not text or not text.strip():
            return

        effective_lang = language_code or self.target_language_code
        keys = self.key_manager.get_all_keys()
        total_keys = len(keys)
        attempts = 0
        last_error = None

        url = f"{SARVAM_STREAMING_TTS_WS_URL}?model={self.model}&send_completion_event=true"

        while attempts < total_keys:
            if cancel_event and cancel_event.is_set():
                logger.info("Streaming TTS aborted before connection: cancel_event is set")
                return

            active_key = self.key_manager.get_current_key()
            headers = {"Api-Subscription-Key": active_key}
            t_connect_start = time.perf_counter()

            ws = None
            try:
                # 1. Connect to WebSocket
                ws = await asyncio.wait_for(
                    websockets.connect(url, additional_headers=headers),
                    timeout=self.timeout_seconds,
                )
                t_connect_end = time.perf_counter()
                logger.info(
                    "Sarvam streaming TTS connected | key=%s | lang=%s | connect_ms=%.1f",
                    self.key_manager.mask_key(active_key),
                    effective_lang,
                    (t_connect_end - t_connect_start) * 1000,
                )

                # 2. Send Config message
                cfg = {
                    "type": "config",
                    "data": {
                        "language_code": effective_lang,
                        "speaker": self.speaker,
                        "output_audio_codec": "wav",
                        "speech_sample_rate": self.speech_sample_rate,
                        "pace": self.pace,
                    },
                }
                await ws.send(json.dumps(cfg))

                # 3. Send Text message
                text_msg = {
                    "type": "text",
                    "data": {"text": text},
                }
                await ws.send(json.dumps(text_msg))

                # 4. Send Flush message to trigger synthesis
                await ws.send(json.dumps({"type": "flush"}))

                header_parsed = False
                total_bytes_yielded = 0
                chunk_index = 0
                sample_remainder = b""

                # 5. Receive chunks progressively
                while True:
                    if cancel_event and cancel_event.is_set():
                        logger.info("Streaming TTS loop cancelled by barge-in")
                        break

                    try:
                        raw_msg = await asyncio.wait_for(ws.recv(), timeout=self.timeout_seconds)
                    except asyncio.TimeoutError:
                        logger.warning("Streaming TTS timed out waiting for audio chunk")
                        break

                    msg = json.loads(raw_msg)
                    msg_type = msg.get("type")

                    if msg_type == "audio":
                        audio_b64 = msg.get("data", {}).get("audio", "")
                        if not audio_b64:
                            continue

                        pcm_chunk = base64.b64decode(audio_b64)

                        # Handle RIFF WAV header on initial chunk
                        if not header_parsed:
                            header_parsed = True
                            if pcm_chunk.startswith(b"RIFF"):
                                data_idx = pcm_chunk.find(b"data")
                                if data_idx != -1 and len(pcm_chunk) >= data_idx + 8:
                                    pcm_chunk = pcm_chunk[data_idx + 8:]
                                elif len(pcm_chunk) > 44:
                                    pcm_chunk = pcm_chunk[44:]
                                else:
                                    continue

                        if sample_remainder:
                            pcm_chunk = sample_remainder + pcm_chunk
                            sample_remainder = b""

                        # Ensure 16-bit sample alignment (multiple of 2 bytes)
                        if len(pcm_chunk) % 2 != 0:
                            sample_remainder = pcm_chunk[-1:]
                            pcm_chunk = pcm_chunk[:-1]

                        if pcm_chunk:
                            chunk_index += 1
                            total_bytes_yielded += len(pcm_chunk)
                            yield pcm_chunk

                    elif msg_type == "event":
                        event_type = msg.get("data", {}).get("event_type")
                        if event_type == "final":
                            logger.info(
                                "Sarvam streaming TTS final event received | chunks=%d | bytes=%d",
                                chunk_index,
                                total_bytes_yielded,
                            )
                            break

                    elif msg_type == "completion":
                        logger.info("Sarvam streaming TTS completion received")
                        break

                    elif msg_type == "error":
                        err_data = msg.get("data", {})
                        logger.error("Sarvam streaming TTS error event: %s", err_data)
                        raise RuntimeError(f"Sarvam streaming TTS error: {err_data}")

                # Successfully finished this stream
                return

            except websockets.exceptions.InvalidStatus as e:
                last_error = e
                status_code = getattr(e.response, "status_code", None)
                logger.warning(
                    "Sarvam streaming TTS HTTP %s on connect (Key #%d %s): %s",
                    status_code,
                    self.key_manager.get_current_index() + 1,
                    self.key_manager.mask_key(active_key),
                    e,
                )
                if status_code in (401, 402, 403, 429) and total_keys > 1:
                    self.key_manager.mark_key_exhausted(
                        active_key,
                        reason=f"WebSocket HTTP {status_code}",
                    )
                    attempts += 1
                    continue
                else:
                    raise
            except Exception as e:
                last_error = e
                logger.warning("Sarvam streaming TTS exception: %s", e)
                raise
            finally:
                if ws:
                    try:
                        await ws.close()
                    except Exception:
                        pass

        raise RuntimeError(
            f"All {total_keys} Sarvam API keys exhausted or failed for streaming TTS. Last error: {last_error}"
        )
