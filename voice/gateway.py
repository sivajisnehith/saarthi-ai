import asyncio
import json
import logging
import os
from urllib.parse import urlencode

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import websockets

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
        "model": SARVAM_STT_MODEL,
        "language_code": SARVAM_LANGUAGE_CODE,
    }


@app.websocket("/voice")
async def voice_stream(websocket: WebSocket):
    await websocket.accept()
    logger.info("Exotel WebSocket connected")

    sarvam_ws = None
    sarvam_recv_task = None
    stream_sid = None
    caller = None

    async def sarvam_receiver(ws):
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
                    logger.info("Sarvam STT: Speech started (utterance %s)", data.get("utterance_idx"))
                elif event == "transcript.partial":
                    text = data.get("text", "").strip()
                    if text:
                        logger.debug("Sarvam STT partial: %s", text)
                elif event == "vad.speech_end":
                    logger.info("Sarvam STT: Speech ended (utterance %s)", data.get("utterance_idx"))
                elif event == "transcript.final":
                    text = data.get("text", "").strip()
                    if text:
                        logger.info("CUSTOMER SAID: %s", text)
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
                await asyncio.sleep(0.5)
                break

    except WebSocketDisconnect:
        logger.info("Exotel WebSocket disconnected | SID=%s", stream_sid)

    except Exception:
        logger.exception("Voice stream error")

    finally:
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
