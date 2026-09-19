import base64
import io
import json
import logging
import os
import wave

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("saarthi.voice")

app = FastAPI(title="Saarthi Voice Gateway")

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"

if not SARVAM_API_KEY:
    raise RuntimeError("SARVAM_API_KEY is not configured")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "saarthi-voice-gateway",
    }


async def transcribe_pcm(pcm_audio: bytes) -> str | None:
    """
    Convert Exotel's raw 8kHz PCM audio into an in-memory WAV
    and send it to Sarvam STT.
    """

    wav_buffer = io.BytesIO()

    with wave.open(wav_buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(pcm_audio)

    wav_buffer.seek(0)

    files = {
        "file": (
            "audio.wav",
            wav_buffer,
            "audio/wav",
        )
    }

    data = {
        "model": "saaras:v3",
        "language_code": "unknown",
    }

    headers = {
        "api-subscription-key": SARVAM_API_KEY,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            SARVAM_STT_URL,
            headers=headers,
            files=files,
            data=data,
        )

    if response.status_code != 200:
        logger.error(
            "Sarvam STT failed: HTTP %s - %s",
            response.status_code,
            response.text[:500],
        )
        return None

    result = response.json()

    transcript = result.get("transcript", "").strip()
    language = result.get("language_code")

    if transcript:
        logger.info(
            "Sarvam STT: %s | language=%s",
            transcript,
            language,
        )

    return transcript or None


@app.websocket("/voice")
async def voice_stream(websocket: WebSocket):
    await websocket.accept()

    logger.info("Exotel WebSocket connected")

    # Collect approximately 2 seconds of 8kHz 16-bit mono PCM.
    audio_buffer = bytearray()

    # 8000 samples/sec × 2 bytes/sample × 2 sec
    TARGET_BUFFER_SIZE = 32000

    try:
        while True:
            message = await websocket.receive_text()

            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                logger.warning("Received non-JSON message")
                continue

            event = data.get("event")

            logger.info("Exotel event: %s", event)

            if event == "connected":
                logger.info("Exotel stream connected")

            elif event == "start":
                logger.info("Exotel media stream started")
                logger.info(
                    "Stream SID: %s",
                    data.get("stream_sid"),
                )

            elif event == "media":
                media = data.get("media", {})
                payload = media.get("payload")

                if not payload:
                    continue

                try:
                    pcm_chunk = base64.b64decode(payload)
                except Exception:
                    logger.exception("Failed to decode Exotel audio")
                    continue

                audio_buffer.extend(pcm_chunk)

                logger.info(
                    "Audio buffer: %d / %d bytes",
                    len(audio_buffer),
                    TARGET_BUFFER_SIZE,
                )

                if len(audio_buffer) >= TARGET_BUFFER_SIZE:
                    pcm_to_transcribe = bytes(audio_buffer)
                    audio_buffer.clear()

                    logger.info(
                        "Sending %d bytes to Sarvam STT",
                        len(pcm_to_transcribe),
                    )

                    transcript = await transcribe_pcm(
                        pcm_to_transcribe
                    )

                    if transcript:
                        logger.info(
                            "CUSTOMER SAID: %s",
                            transcript,
                        )

            elif event == "stop":
                logger.info("Exotel stream stopped")
                break

    except WebSocketDisconnect:
        logger.info("Exotel WebSocket disconnected")

    except Exception:
        logger.exception("Voice stream error")

    finally:
        logger.info("Voice session ended")
