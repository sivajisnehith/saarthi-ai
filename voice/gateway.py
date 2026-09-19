import asyncio
import base64
import json
import logging
import os
import re
from urllib.parse import urlencode

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import websockets

from agent.agent import create_saarthi_agent
from voice.tts import SarvamTTSService

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("saarthi.voice")

app = FastAPI(title="Saarthi Voice Gateway")

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
SARVAM_STT_MODEL = os.getenv("SARVAM_STT_MODEL", "saaras:v3-realtime")
SARVAM_LANGUAGE_CODE = os.getenv("SARVAM_LANGUAGE_CODE", "en-IN")
SARVAM_SAMPLE_RATE = int(os.getenv("SARVAM_SAMPLE_RATE", "8000"))
SARVAM_STREAM_TYPE = os.getenv("SARVAM_STREAM_TYPE", "balanced")

if not SARVAM_API_KEY:
    raise RuntimeError("SARVAM_API_KEY is not configured")

SARVAM_WS_BASE_URL = "wss://api.sarvam.ai/speech-to-text-realtime/ws"

# Exact initial greeting text
INITIAL_GREETING_TEXT = (
    "Hi! I'm Saarthi, your travel assistant. How can I help you today?"
)

# Initialize reusable TTS service
tts_service = SarvamTTSService(
    api_key=SARVAM_API_KEY,
    model="bulbul:v3",
    speaker="kavya",
    target_language_code="en-IN",
    speech_sample_rate=8000,
    pace=1.0,
)


def clean_text_for_tts(text: str) -> str:
    """
    Lightweight text normalization for TTS playback:
    Strips markdown code blocks, links, headers, asterisks, bullet points,
    and converts currency symbols to natural speech.
    """
    if not text:
        return ""

    # Remove code blocks and inline code
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)

    # Remove markdown links: [label](url) -> label
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

    # Remove raw URLs
    text = re.sub(r"https?://\S+", "", text)

    # Replace currency symbols
    text = text.replace("?", " rupees ")

    # Remove markdown emphasis (bold, italics)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    text = re.sub(r"_([^_]+)_", r"\1", text)

    # Remove headers and list bullets
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*?]\s*", "", text, flags=re.MULTILINE)

    # Collapse multiple whitespace / newlines
    text = re.sub(r"\s+", " ", text).strip()

    return text


def get_sarvam_ws_url() -> str:
    params = {
        "model": SARVAM_STT_MODEL,
        "language_code": SARVAM_LANGUAGE_CODE,
        "sample_rate": str(SARVAM_SAMPLE_RATE),
        "stream_type": SARVAM_STREAM_TYPE,
    }
    return f"{SARVAM_WS_BASE_URL}?{urlencode(params)}"


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "saarthi-voice-gateway",
        "stt": "sarvam-realtime-websocket",
        "tts": "sarvam-bulbul-v3",
        "agent": "strands-bedrock",
        "model": SARVAM_STT_MODEL,
        "language_code": SARVAM_LANGUAGE_CODE,
        "sample_rate": SARVAM_SAMPLE_RATE,
    }


@app.websocket("/voice")
async def voice_stream(websocket: WebSocket):
    await websocket.accept()
    logger.info("Exotel WebSocket connected")

    # Create an isolated Saarthi Agent for this specific phone call session
    call_agent = create_saarthi_agent(voice=True)
    logger.info("Initialized per-call Saarthi agent | session_id=%s", call_agent.session_id)

    sarvam_ws = None
    sarvam_recv_task = None
    agent_task = None
    greeting_task = None

    stream_sid = None
    caller = None
    exotel_chunk_counter = 0
    session_active = True
    greeting_started = False
    send_lock = asyncio.Lock()

    async def play_tts_response(response_text: str, sid: str):
        nonlocal exotel_chunk_counter
        try:
            logger.info("Generating TTS response...")
            pcm_data = await tts_service.synthesize(response_text)
            if not pcm_data:
                return

            logger.info("TTS generated successfully | bytes=%d", len(pcm_data))

            chunk_size = 1600  # 100 ms of 8000 Hz, 16-bit mono PCM (multiple of 320)
            total_chunks = (len(pcm_data) + chunk_size - 1) // chunk_size
            logger.info("Sending TTS to Exotel | chunks=%d", total_chunks)

            for i in range(0, len(pcm_data), chunk_size):
                if not session_active:
                    logger.info("Session ended, stopping TTS playback")
                    break

                chunk = pcm_data[i : i + chunk_size]
                exotel_chunk_counter += 1
                timestamp_ms = int(i / 16)  # 16 bytes per millisecond

                payload_b64 = base64.b64encode(chunk).decode("ascii")
                media_msg = {
                    "event": "media",
                    "stream_sid": sid,
                    "media": {
                        "chunk": str(exotel_chunk_counter),
                        "timestamp": str(timestamp_ms),
                        "payload": payload_b64,
                    },
                }

                async with send_lock:
                    if session_active:
                        await websocket.send_text(json.dumps(media_msg))

                # Real-time pacing (~100 ms per 1600 bytes)
                await asyncio.sleep(len(chunk) / 16000.0)

            if session_active:
                logger.info("TTS playback sent")

        except asyncio.CancelledError:
            logger.info("TTS playback cancelled")
        except Exception:
            logger.exception("Error during TTS generation or playback")

    async def play_initial_greeting(sid: str):
        try:
            logger.info("Saarthi initial greeting starting...")
            logger.info("SAARTHI GREETING: %s", INITIAL_GREETING_TEXT)
            await play_tts_response(INITIAL_GREETING_TEXT, sid)
            if session_active:
                logger.info("Initial greeting playback completed")
        except asyncio.CancelledError:
            logger.info("Initial greeting playback cancelled")
        except Exception:
            logger.exception("Error during initial greeting playback")

    async def handle_agent_and_tts(customer_text: str, sid: str):
        try:
            logger.info("Saarthi agent processing...")
            try:
                agent_result = await asyncio.wait_for(
                    call_agent.invoke_async(customer_text),
                    timeout=25.0,
                )
                raw_response = str(agent_result).strip()
            except asyncio.TimeoutError:
                logger.warning("Agent invocation timed out")
                raw_response = "Sorry, I took a little too long to respond. Could you please say that again?"
            except Exception:
                logger.exception("Agent invocation failed")
                raw_response = "Sorry, I had trouble processing that. Could you please say that again?"

            if not raw_response:
                raw_response = "Sorry, I didn't catch that. Could you please say that again?"

            logger.info("SAARTHI SAID: %s", raw_response)

            if not session_active:
                logger.info("Session ended during agent processing, aborting TTS")
                return

            tts_text = clean_text_for_tts(raw_response)
            if not tts_text:
                return

            await play_tts_response(tts_text, sid)

        except asyncio.CancelledError:
            logger.info("Agent/TTS task cancelled")
        except Exception:
            logger.exception("Error in agent/TTS handler")

    async def sarvam_receiver(ws):
        nonlocal agent_task
        try:
            async for message in ws:
                try:
                    data = json.loads(message)
                except Exception:
                    continue

                event = data.get("event")
                if event == "session.begin":
                    req_id = data.get("request_id")
                    logger.info("Sarvam STT session started | request_id=%s", req_id)
                elif event == "vad.speech_start":
                    logger.info(
                        "Sarvam STT: Speech started (utterance %s)",
                        data.get("utterance_idx"),
                    )
                elif event == "transcript.partial":
                    text = data.get("text", "").strip()
                    if text:
                        logger.debug("Sarvam STT partial: %s", text)
                elif event == "vad.speech_end":
                    logger.info(
                        "Sarvam STT: Speech ended (utterance %s)",
                        data.get("utterance_idx"),
                    )
                elif event == "transcript.final":
                    text = data.get("text", "").strip()
                    if text:
                        logger.info("CUSTOMER SAID: %s", text)
                        # Process through Saarthi Strands agent -> TTS -> Exotel
                        if stream_sid and session_active:
                            is_greeting_playing = (
                                greeting_task is not None and not greeting_task.done()
                            )
                            is_agent_playing = (
                                agent_task is not None and not agent_task.done()
                            )
                            if is_greeting_playing or is_agent_playing:
                                logger.info(
                                    "Agent/TTS playback already in progress, skipping overlapping utterance"
                                )
                            else:
                                agent_task = asyncio.create_task(
                                    handle_agent_and_tts(text, stream_sid)
                                )
                elif event == "error":
                    logger.error("Sarvam STT error: %s", data)
                elif event == "session.end":
                    logger.info("Sarvam STT session ended: %s", data)
        except asyncio.CancelledError:
            pass
        except websockets.exceptions.ConnectionClosed as e:
            logger.info("Sarvam STT connection closed: code=%s, reason=%s", e.code, e.reason)
        except Exception:
            logger.exception("Error in Sarvam STT receiver loop")

    try:
        sarvam_url = get_sarvam_ws_url()
        headers = {"api-subscription-key": SARVAM_API_KEY}
        logger.info("Connecting to Sarvam Realtime STT: %s", sarvam_url)
        try:
            sarvam_ws = await websockets.connect(sarvam_url, additional_headers=headers)
            logger.info("Sarvam STT connected")
            sarvam_recv_task = asyncio.create_task(sarvam_receiver(sarvam_ws))
        except Exception:
            logger.exception("Failed to connect to Sarvam Realtime STT")

        while True:
            message = await websocket.receive_text()
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                logger.warning("Received non-JSON message from Exotel")
                continue

            event = data.get("event")

            if event == "connected":
                logger.info("Exotel stream connected")

            elif event == "start":
                start_data = data.get("start", {})
                stream_sid = data.get("stream_sid") or start_data.get("stream_sid")
                caller = start_data.get("from")
                logger.info("Exotel media stream started | SID=%s | Caller=%s", stream_sid, caller)

                # Immediately trigger initial greeting (once per call)
                if not greeting_started and stream_sid and session_active:
                    greeting_started = True
                    greeting_task = asyncio.create_task(play_initial_greeting(stream_sid))

            elif event == "media":
                media = data.get("media", {})
                payload = media.get("payload")

                if payload and sarvam_ws is not None:
                    try:
                        msg = json.dumps({"event": "audio_input", "audio": payload})
                        await sarvam_ws.send(msg)
                    except websockets.exceptions.ConnectionClosed:
                        logger.warning("Sarvam STT connection closed while sending audio")
                        sarvam_ws = None
                    except Exception:
                        logger.exception("Error sending audio to Sarvam STT")

            elif event == "stop":
                logger.info("Exotel stream stopped | SID=%s", stream_sid)
                session_active = False
                await asyncio.sleep(0.5)
                break

    except WebSocketDisconnect:
        logger.info("Exotel WebSocket disconnected | SID=%s", stream_sid)

    except Exception:
        logger.exception("Voice stream error")

    finally:
        session_active = False

        if greeting_task and not greeting_task.done():
            greeting_task.cancel()
            try:
                await greeting_task
            except asyncio.CancelledError:
                pass

        if agent_task and not agent_task.done():
            agent_task.cancel()
            try:
                await agent_task
            except asyncio.CancelledError:
                pass

        if sarvam_recv_task and not sarvam_recv_task.done():
            sarvam_recv_task.cancel()
            try:
                await sarvam_recv_task
            except asyncio.CancelledError:
                pass

        if sarvam_ws is not None:
            try:
                await sarvam_ws.close()
            except Exception:
                pass

        logger.info("Voice session ended | SID=%s", stream_sid)
