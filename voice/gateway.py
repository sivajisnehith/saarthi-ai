import json
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("saarthi.voice")

app = FastAPI(title="Saarthi Voice Gateway")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "saarthi-voice-gateway",
    }


@app.websocket("/voice")
async def voice_stream(websocket: WebSocket):
    await websocket.accept()

    logger.info("Exotel WebSocket connected")

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
                logger.info("Start payload: %s", data)

            elif event == "media":
                # Audio will come here.
                # We are NOT sending it to Sarvam yet.
                media = data.get("media", {})
                payload = media.get("payload")

                if payload:
                    logger.info(
                        "Received audio payload (%d chars)",
                        len(payload),
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