import base64
import io
import logging
import os
import wave
import httpx

logger = logging.getLogger("saarthi.voice.tts")

SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"


class SarvamTTSService:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = "bulbul:v3",
        speaker: str = "kavya",
        target_language_code: str = "en-IN",
        speech_sample_rate: int = 8000,
        pace: float = 1.0,
    ):
        self.api_key = api_key or os.getenv("SARVAM_API_KEY")
        if not self.api_key:
            raise RuntimeError("SARVAM_API_KEY is not configured for TTS")
        self.model = model
        self.speaker = speaker
        self.target_language_code = target_language_code
        self.speech_sample_rate = speech_sample_rate
        self.pace = pace

    async def synthesize(self, text: str) -> bytes:
        """
        Synthesizes text into raw 8000 Hz, 16-bit mono little-endian PCM bytes.
        Validates WAV container properties and strips the RIFF header.
        """
        if not text or not text.strip():
            return b""

        headers = {
            "api-subscription-key": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "text": text,
            "target_language_code": self.target_language_code,
            "speaker": self.speaker,
            "model": self.model,
            "speech_sample_rate": self.speech_sample_rate,
            "output_audio_codec": "wav",
            "pace": self.pace,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(SARVAM_TTS_URL, headers=headers, json=payload)

        if resp.status_code != 200:
            logger.error("Sarvam TTS failed: HTTP %s - %s", resp.status_code, resp.text[:300])
            raise RuntimeError(f"Sarvam TTS failed with HTTP {resp.status_code}")

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

        return pcm_data
