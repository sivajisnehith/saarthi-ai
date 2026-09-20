import time
import base64
import io
import logging
import os
import wave
import httpx
from typing import Optional

from voice.key_manager import SarvamKeyManager, sarvam_key_manager

logger = logging.getLogger("saarthi.voice.tts")

SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"


class SarvamTTSService:
    def __init__(
        self,
        api_key: Optional[str] = None,
        key_manager: Optional[SarvamKeyManager] = None,
        model: str = "bulbul:v3",
        speaker: str = "kavya",
        target_language_code: str = "en-IN",
        speech_sample_rate: int = 8000,
        pace: float = 1.0,
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

    async def synthesize(self, text: str, language_code: Optional[str] = None) -> bytes:
        """
        Synthesizes text into raw 8000 Hz, 16-bit mono little-endian PCM bytes.
        Validates WAV container properties and strips the RIFF header.
        Automatically falls back across all available Sarvam API keys if credits
        are exhausted (HTTP 402/401/403/429 or quota limit).
        """
        if not text or not text.strip():
            return b""

        effective_lang = language_code or self.target_language_code
        payload = {
            "text": text,
            "target_language_code": effective_lang,
            "speaker": self.speaker,
            "model": self.model,
            "speech_sample_rate": self.speech_sample_rate,
            "output_audio_codec": "wav",
            "pace": self.pace,
        }

        keys = self.key_manager.get_all_keys()
        total_keys = len(keys)
        attempts = 0
        last_error = None

        while attempts < total_keys:
            active_key = self.key_manager.get_current_key()
            headers = {
                "api-subscription-key": active_key,
                "Content-Type": "application/json",
            }

            try:
                t_req_start = time.perf_counter()
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(SARVAM_TTS_URL, headers=headers, json=payload)
                t_req_end = time.perf_counter()

                if resp.status_code == 200:
                    data = resp.json()
                    audios = data.get("audios")
                    if not audios or not audios[0]:
                        raise RuntimeError("Sarvam TTS returned empty audio list")

                    audio_bytes = base64.b64decode(audios[0])

                    with wave.open(io.BytesIO(audio_bytes), "rb") as wav_file:
                        nchannels = wav_file.getnchannels()
                        sampwidth = wav_file.getsampwidth()
                        framerate = wav_file.getframerate()
                        nframes = wav_file.getnframes()
                        comptype = wav_file.getcomptype()

                        if nchannels != 1:
                            raise ValueError(f"Expected 1 channel (mono), got {nchannels}")
                        if sampwidth != 2:
                            raise ValueError(f"Expected 16-bit PCM (2 bytes sample width), got {sampwidth}")
                        if framerate != self.speech_sample_rate:
                            raise ValueError(f"Expected {self.speech_sample_rate} Hz, got {framerate}")
                        if comptype != "NONE":
                            raise ValueError(f"Expected uncompressed PCM, got {comptype}")

                        pcm_data = wav_file.readframes(nframes)

                    t_decode_end = time.perf_counter()
                    logger.info(
                        "Sarvam TTS timing | network_ms=%.1f | decode_ms=%.1f | total_ms=%.1f | bytes=%d",
                        (t_req_end - t_req_start) * 1000,
                        (t_decode_end - t_req_end) * 1000,
                        (t_decode_end - t_req_start) * 1000,
                        len(pcm_data),
                    )
                    return pcm_data

                # Non-200 response
                resp_text = resp.text[:300]
                logger.warning(
                    "Sarvam TTS failed with HTTP %s (Key #%d %s): %s",
                    resp.status_code,
                    self.key_manager.get_current_index() + 1,
                    self.key_manager.mask_key(active_key),
                    resp_text,
                )

                is_credit_or_auth_error = resp.status_code in (401, 402, 403, 429) or any(
                    term in resp_text.lower()
                    for term in ["credit", "quota", "insufficient", "balance", "payment", "limit"]
                )

                if is_credit_or_auth_error and total_keys > 1:
                    self.key_manager.mark_key_exhausted(
                        active_key,
                        reason=f"HTTP {resp.status_code}: {resp_text[:80]}",
                    )
                    attempts += 1
                    continue
                else:
                    raise RuntimeError(f"Sarvam TTS failed with HTTP {resp.status_code}: {resp_text}")

            except Exception as e:
                last_error = e
                # If error is credit or auth related, advance to next key if available
                if attempts < total_keys - 1 and any(
                    err_cls in type(e).__name__ for err_cls in ["HTTP", "Runtime", "Status"]
                ):
                    self.key_manager.mark_key_exhausted(active_key, reason=str(e)[:80])
                    attempts += 1
                    continue
                raise

        raise RuntimeError(
            f"All {total_keys} Sarvam API keys exhausted or failed for TTS. Last error: {last_error}"
        )
