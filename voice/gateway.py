import asyncio
import base64
import json
import logging
import os
import re
from typing import Any, Optional
from urllib.parse import urlencode

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import websockets

from agent.agent import create_saarthi_agent
from voice.tts import SarvamTTSService
from voice.streaming_tts import SarvamStreamingTTSService

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("saarthi.voice")

app = FastAPI(title="Saarthi Voice Gateway")

from voice.key_manager import SarvamKeyManager, sarvam_key_manager
from voice.time_formatter import format_time_for_speech, format_spoken_times
from voice.telemetry import CallTelemetry, attach_strands_telemetry

SARVAM_STT_MODEL = os.getenv("SARVAM_STT_MODEL", "saaras:v3-realtime")
SARVAM_LANGUAGE_CODE = os.getenv("SARVAM_LANGUAGE_CODE", "en-IN")
SARVAM_SAMPLE_RATE = int(os.getenv("SARVAM_SAMPLE_RATE", "8000"))
SARVAM_STREAM_TYPE = os.getenv("SARVAM_STREAM_TYPE", "balanced")

SARVAM_WS_BASE_URL = "wss://api.sarvam.ai/speech-to-text-realtime/ws"

# Exact initial greeting text
INITIAL_GREETING_TEXT = (
    "Hi! I'm Saarthi, your travel assistant. How can I help you today?"
)

# Initialize reusable TTS service with fallback key manager
tts_service = SarvamTTSService(
    key_manager=sarvam_key_manager,
    model="bulbul:v3",
    speaker="kavya",
    target_language_code="en-IN",
    speech_sample_rate=8000,
    pace=1.0,
)

# Initialize streaming TTS service (primary playback path)
streaming_tts_service = SarvamStreamingTTSService(
    key_manager=sarvam_key_manager,
    model="bulbul:v3",
    speaker="kavya",
    target_language_code="en-IN",
    speech_sample_rate=8000,
    pace=1.0,
)



from voice.sanitizer import (
    INTERNAL_TAGS,
    INTERNAL_PHRASES,
    is_internal_sentence,
    sanitize_agent_text,
    sanitize_multilingual_contamination,
    detect_response_language,
    enforce_concise_voice_response,
    clean_text_for_tts,
    extract_agent_response,
)
from voice.progress import (
    TOOL_PROGRESS_STAGES,
    ProgressManager,
    strip_redundant_progress_prefix,
    set_active_progress_callback,
)



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
        "sarvam_keys_count": len(sarvam_key_manager.get_all_keys()),
        "sarvam_active_key_index": sarvam_key_manager.get_current_index() + 1,
    }


@app.websocket("/voice")
async def voice_stream(websocket: WebSocket):
    await websocket.accept()
    logger.info("Exotel WebSocket connected")

    # Create an isolated Saarthi Agent for this specific phone call session
    call_telemetry = CallTelemetry()
    call_agent = create_saarthi_agent(voice=True)
    progress_manager = ProgressManager()

    sarvam_ws = None
    sarvam_recv_task = None
    agent_task = None
    tts_task = None
    greeting_task = None
    progress_tts_task = None
    progress_first_chunk_sent = False

    stream_sid = None
    caller = None
    exotel_chunk_counter = 0
    session_active = True
    greeting_started = False
    send_lock = asyncio.Lock()

    # Per-call barge-in and playback control state
    current_turn_id = 0
    playback_active = False
    playback_cancel_event = asyncio.Event()

    def cancel_active_playback(source: str = "barge-in"):
        nonlocal playback_active
        is_greeting = greeting_task is not None and not greeting_task.done()
        is_tts = tts_task is not None and not tts_task.done()
        is_progress = progress_tts_task is not None and not progress_tts_task.done()
        if playback_active or is_greeting or is_tts or is_progress:
            logger.info("Customer barge-in detected – cancelling TTS (%s)", source)
            playback_cancel_event.set()
            playback_active = False
            if tts_task and not tts_task.done():
                tts_task.cancel()
            if progress_tts_task and not progress_tts_task.done():
                progress_tts_task.cancel()
            if greeting_task and not greeting_task.done():
                greeting_task.cancel()

    async def on_tool_progress(tool_name: str, turn_id: Optional[int] = None):
        nonlocal stream_sid, session_active, playback_cancel_event, progress_tts_task, progress_first_chunk_sent
        if turn_id is None:
            turn_id = current_turn_id
        if not session_active or playback_cancel_event.is_set() or not stream_sid:
            return

        progress_info = progress_manager.get_progress_for_tool(tool_name)
        if not progress_info:
            return

        stage_id, progress_msg = progress_info
        progress_manager.mark_stage_announced(stage_id)
        logger.info(
            "PROGRESS START: %s | stage=%s | text='%s' (turn %s)",
            tool_name,
            stage_id,
            progress_msg,
            turn_id,
        )
        progress_first_chunk_sent = False
        progress_tts_task = asyncio.create_task(
            play_tts_response(progress_msg, stream_sid, turn_id, is_progress=True)
        )

    attach_strands_telemetry(
        call_agent,
        call_telemetry,
        lambda: current_turn_id,
        before_tool_callback=on_tool_progress,
    )
    set_active_progress_callback(on_tool_progress)
    logger.info("Initialized per-call Saarthi agent | session_id=%s", call_agent.session_id)

    async def play_tts_response(response_text: str, sid: str, turn_id: int, is_progress: bool = False):
        nonlocal exotel_chunk_counter, playback_active, progress_first_chunk_sent
        if not session_active:
            return

        if turn_id != current_turn_id or playback_cancel_event.is_set():
            logger.info("Discarding stale Saarthi response for turn %s", turn_id)
            return

        try:
            logger.info("SAARTHI TTS INPUT%s: %s", " (PROGRESS)" if is_progress else "", response_text)
            logger.info("Generating TTS response...")
            if not is_progress:
                call_telemetry.on_tts_start(turn_id)

            playback_active = True
            interrupted = False
            first_chunk_sent = False
            total_chunks = 0
            chunk_size = 1600  # 100 ms of 8000 Hz, 16-bit mono PCM (multiple of 320)
            buffer = bytearray()
            total_pcm_bytes = 0
            stream_failed = False
            target_lang = detect_response_language(response_text)

            # Primary path: Sarvam Streaming TTS
            try:
                logger.info("Starting Sarvam Streaming TTS (turn %s, lang=%s)...", turn_id, target_lang)
                async for pcm_chunk in streaming_tts_service.stream_pcm_chunks(
                    response_text,
                    cancel_event=playback_cancel_event,
                    language_code=target_lang,
                ):
                    if not session_active or playback_cancel_event.is_set() or turn_id != current_turn_id:
                        interrupted = True
                        break

                    if not first_chunk_sent and len(pcm_chunk) > 0 and not is_progress:
                        call_telemetry.on_tts_audio_ready(turn_id, len(pcm_chunk))

                    buffer.extend(pcm_chunk)
                    total_pcm_bytes += len(pcm_chunk)

                    # Progressive forward to Exotel
                    while len(buffer) >= chunk_size:
                        if not session_active or playback_cancel_event.is_set() or turn_id != current_turn_id:
                            interrupted = True
                            break

                        chunk = bytes(buffer[:chunk_size])
                        del buffer[:chunk_size]

                        exotel_chunk_counter += 1
                        total_chunks += 1
                        timestamp_ms = int(total_chunks * 100)

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
                            if session_active and not playback_cancel_event.is_set() and turn_id == current_turn_id:
                                await websocket.send_text(json.dumps(media_msg))
                                if not first_chunk_sent:
                                    first_chunk_sent = True
                                    if is_progress:
                                        progress_first_chunk_sent = True
                                        logger.info("PROGRESS TTS FIRST AUDIO (turn %s)", turn_id)
                                    else:
                                        logger.info("TTS playback started (streaming)")
                                        call_telemetry.on_first_chunk_sent(turn_id)
                            else:
                                interrupted = True
                                break

                        # Real-time pacing (~100 ms per 1600 bytes)
                        await asyncio.sleep(len(chunk) / 16000.0)

                    if interrupted:
                        break

                # Stream completed naturally; flush remaining buffered audio
                if not interrupted and session_active and not playback_cancel_event.is_set() and turn_id == current_turn_id:
                    call_telemetry.on_tts_stream_complete(turn_id, total_pcm_bytes)
                    while len(buffer) > 0:
                        if not session_active or playback_cancel_event.is_set() or turn_id != current_turn_id:
                            interrupted = True
                            break

                        chunk = bytes(buffer[:chunk_size])
                        del buffer[:chunk_size]

                        exotel_chunk_counter += 1
                        total_chunks += 1
                        timestamp_ms = int(total_chunks * 100)

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
                            if session_active and not playback_cancel_event.is_set() and turn_id == current_turn_id:
                                await websocket.send_text(json.dumps(media_msg))
                                if not first_chunk_sent:
                                    first_chunk_sent = True
                                    if is_progress:
                                        progress_first_chunk_sent = True
                                        logger.info("PROGRESS TTS FIRST AUDIO (turn %s)", turn_id)
                                    else:
                                        logger.info("TTS playback started (streaming)")
                                        call_telemetry.on_first_chunk_sent(turn_id)
                            else:
                                interrupted = True
                                break

                        await asyncio.sleep(len(chunk) / 16000.0)

            except Exception as stream_err:
                if not first_chunk_sent:
                    logger.warning(
                        "Streaming TTS failed before sending audio, falling back to REST TTS: %s",
                        stream_err,
                    )
                    stream_failed = True
                else:
                    logger.error("Streaming TTS error during playback: %s", stream_err)
                    interrupted = True

            # Fallback path: If streaming TTS failed before any chunk was sent to Exotel
            if (
                stream_failed
                and not interrupted
                and session_active
                and not playback_cancel_event.is_set()
                and turn_id == current_turn_id
            ):
                logger.info("Executing REST TTS fallback for turn %s (lang=%s)...", turn_id, target_lang)
                pcm_data = await tts_service.synthesize(response_text, language_code=target_lang)
                if not pcm_data:
                    return

                if not is_progress:
                    call_telemetry.on_tts_audio_ready(turn_id, len(pcm_data))

                if turn_id != current_turn_id or playback_cancel_event.is_set() or not session_active:
                    logger.info("Discarding stale Saarthi response for turn %s", turn_id)
                    return

                logger.info("TTS playback started (REST fallback)")
                rest_total_chunks = (len(pcm_data) + chunk_size - 1) // chunk_size
                for i in range(0, len(pcm_data), chunk_size):
                    if not session_active:
                        interrupted = True
                        break
                    if playback_cancel_event.is_set() or turn_id != current_turn_id:
                        interrupted = True
                        break

                    chunk = pcm_data[i : i + chunk_size]
                    exotel_chunk_counter += 1
                    total_chunks += 1
                    timestamp_ms = int(i / 16)
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
                        if session_active and not playback_cancel_event.is_set() and turn_id == current_turn_id:
                            await websocket.send_text(json.dumps(media_msg))
                            if not first_chunk_sent:
                                first_chunk_sent = True
                                if is_progress:
                                    progress_first_chunk_sent = True
                                    logger.info("PROGRESS TTS FIRST AUDIO (turn %s)", turn_id)
                                else:
                                    call_telemetry.on_first_chunk_sent(turn_id)
                        else:
                            interrupted = True
                            break

                    await asyncio.sleep(len(chunk) / 16000.0)

            if interrupted:
                logger.info("TTS playback interrupted (turn %s)", turn_id)
                if is_progress:
                    logger.info("PROGRESS CANCELLED (turn %s)", turn_id)
                else:
                    call_telemetry.on_turn_interrupted(turn_id, "barge-in")
            elif first_chunk_sent:
                logger.info("TTS playback completed | chunks=%d (turn %s)", total_chunks, turn_id)
                if is_progress:
                    logger.info("PROGRESS COMPLETE (turn %s)", turn_id)
                else:
                    call_telemetry.on_last_chunk_sent(turn_id, total_chunks)

        except asyncio.CancelledError:
            logger.info("TTS playback interrupted")
            if is_progress:
                logger.info("PROGRESS CANCELLED (turn %s)", turn_id)
            else:
                call_telemetry.on_turn_interrupted(turn_id, "barge-in")
        except Exception:
            logger.exception("Error during TTS generation or playback")
        finally:
            playback_active = False

    async def play_initial_greeting(sid: str, turn_id: int):
        nonlocal playback_active
        try:
            logger.info("Saarthi initial greeting starting...")
            logger.info("SAARTHI GREETING: %s", INITIAL_GREETING_TEXT)
            await play_tts_response(INITIAL_GREETING_TEXT, sid, turn_id)
            if session_active and not playback_cancel_event.is_set() and turn_id == current_turn_id:
                logger.info("Initial greeting playback completed")
        except asyncio.CancelledError:
            logger.info("TTS playback interrupted")
        except Exception:
            logger.exception("Error during initial greeting playback")

    async def handle_agent_and_tts(customer_text: str, sid: str, turn_id: int):
        nonlocal tts_task
        try:
            logger.info("Saarthi agent processing | turn=%s...", turn_id)
            call_telemetry.on_agent_start(turn_id)
            try:
                agent_result = await asyncio.wait_for(
                    call_agent.invoke_async(customer_text),
                    timeout=25.0,
                )
                if getattr(agent_result, "stop_reason", None) == "cancelled":
                    logger.info("Agent invocation cancelled for turn %s", turn_id)
                    return
                raw_response = extract_agent_response(agent_result)
                call_telemetry.on_agent_end(turn_id, raw_response)
            except asyncio.CancelledError:
                logger.info("Agent task cancelled for turn %s", turn_id)
                return
            except asyncio.TimeoutError:
                logger.warning("Agent invocation timed out for turn %s", turn_id)
                raw_response = "Sorry, I took a little too long to respond. Could you please say that again?"
            except Exception:
                logger.exception("Agent invocation failed for turn %s", turn_id)
                raw_response = "Sorry, I had trouble processing that. Could you please say that again?"

            if turn_id != current_turn_id or playback_cancel_event.is_set():
                logger.info("Discarding stale Saarthi response for turn %s", turn_id)
                return

            if not raw_response:
                raw_response = "Sorry, I didn't catch that. Could you please say that again?"

            logger.info("SAARTHI SAID: %s", raw_response)

            # If a pre-tool progress message is still actively streaming to the caller,
            # wait for it to conclude cleanly before starting the final answer.
            # If it hasn't sent any audio yet, cancel it so we speak the final response immediately.
            if progress_tts_task and not progress_tts_task.done():
                if progress_first_chunk_sent:
                    try:
                        await progress_tts_task
                    except asyncio.CancelledError:
                        pass
                    except Exception:
                        pass
                else:
                    logger.info("Cancelling un-started progress TTS in favor of immediate final response (turn %s)", turn_id)
                    progress_tts_task.cancel()

            if not session_active or turn_id != current_turn_id or playback_cancel_event.is_set():
                logger.info("Discarding stale Saarthi response for turn %s", turn_id)
                return

            tts_text = clean_text_for_tts(raw_response, announced_progress_stages=progress_manager.announced_stages)
            if not tts_text:
                return

            logger.info("FINAL RESPONSE: %s (turn %s)", tts_text, turn_id)

            if turn_id != current_turn_id or playback_cancel_event.is_set():
                logger.info("Discarding stale Saarthi response for turn %s", turn_id)
                return

            if tts_task and not tts_task.done():
                tts_task.cancel()

            playback_cancel_event.clear()
            tts_task = asyncio.create_task(play_tts_response(tts_text, sid, turn_id))
            await tts_task

        except asyncio.CancelledError:
            logger.info("Agent/TTS task cancelled for turn %s", turn_id)
        except Exception:
            logger.exception("Error in agent/TTS handler for turn %s", turn_id)

    async def sarvam_receiver(ws):
        nonlocal agent_task, current_turn_id, playback_cancel_event
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
                    call_telemetry.on_speech_start(data.get("utterance_idx"))
                    # Barge-in: immediate cancellation of active TTS playback
                    cancel_active_playback("vad.speech_start")
                    # Increment conversational turn ID so any in-flight response becomes stale
                    current_turn_id += 1
                    progress_manager.start_new_turn(current_turn_id)
                elif event == "transcript.partial":
                    text = data.get("text", "").strip()
                    if text:
                        logger.debug("Sarvam STT partial: %s", text)
                elif event == "vad.speech_end":
                    logger.info(
                        "Sarvam STT: Speech ended (utterance %s)",
                        data.get("utterance_idx"),
                    )
                    call_telemetry.on_speech_end(data.get("utterance_idx"))
                elif event == "transcript.final":
                    text = data.get("text", "").strip()
                    if text:
                        logger.info("CUSTOMER SAID: %s", text)
                        logger.info("CUSTOMER STT: %s", text)
                        # Process through Saarthi Strands agent -> TTS -> Exotel
                        if stream_sid and session_active:
                            # If audio was still playing, cancel immediately
                            cancel_active_playback("transcript.final")
                            current_turn_id += 1
                            progress_manager.start_new_turn(current_turn_id)

                            # Clear cancel event for the new turn
                            playback_cancel_event.clear()

                            # If a previous agent invocation is still running, cancel it
                            if agent_task and not agent_task.done():
                                logger.info("Cancelling previous agent invocation before starting new turn...")
                                call_agent.cancel()
                                agent_task.cancel()
                                await asyncio.sleep(0.01)

                            assigned_turn = current_turn_id
                            call_telemetry.on_transcript_final(assigned_turn, text)
                            agent_task = asyncio.create_task(
                                handle_agent_and_tts(text, stream_sid, assigned_turn)
                            )
                elif event == "error":
                    logger.error("Sarvam STT error: %s", data)
                    err_msg = str(data.get("message", "")).lower()
                    if any(term in err_msg for term in ["credit", "quota", "balance", "unauthorized", "forbidden", "insufficient", "payment"]):
                        active_k = sarvam_key_manager.get_current_key()
                        sarvam_key_manager.mark_key_exhausted(active_k, reason=f"STT error event: {err_msg[:80]}")
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
        total_keys = len(sarvam_key_manager.get_all_keys())
        for attempt in range(total_keys):
            active_key = sarvam_key_manager.get_current_key()
            headers = {"api-subscription-key": active_key}
            logger.info(
                "Connecting to Sarvam Realtime STT (key #%d/%d %s)...",
                sarvam_key_manager.get_current_index() + 1,
                total_keys,
                sarvam_key_manager.mask_key(active_key),
            )
            try:
                sarvam_ws = await websockets.connect(sarvam_url, additional_headers=headers)
                logger.info("Sarvam STT connected successfully")
                sarvam_recv_task = asyncio.create_task(sarvam_receiver(sarvam_ws))
                break
            except websockets.exceptions.InvalidStatusCode as e:
                logger.warning(
                    "Sarvam STT WebSocket handshake failed with HTTP %s (Key #%d %s)",
                    e.status_code,
                    sarvam_key_manager.get_current_index() + 1,
                    sarvam_key_manager.mask_key(active_key),
                )
                if e.status_code in (401, 402, 403, 429) and total_keys > 1:
                    sarvam_key_manager.mark_key_exhausted(active_key, reason=f"WS Handshake HTTP {e.status_code}")
                    continue
                else:
                    logger.exception("Failed to connect to Sarvam Realtime STT")
                    break
            except Exception:
                logger.exception("Failed to connect to Sarvam Realtime STT")
                if total_keys > 1 and attempt < total_keys - 1:
                    sarvam_key_manager.mark_key_exhausted(active_key, reason="WS Connection failed")
                    continue
                break

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
                stream_sid = data.get("stream_sid") or start_data.get("stream_sid") or data.get("streamSid") or start_data.get("streamSid")
                caller = start_data.get("from")
                call_sid = start_data.get("call_sid") or start_data.get("callSid")
                call_telemetry.stream_sid = stream_sid
                call_telemetry.call_sid = call_sid
                logger.info("Exotel media stream started | SID=%s | Caller=%s", stream_sid, caller)

                # Immediately trigger initial greeting (once per call)
                if not greeting_started and stream_sid and session_active:
                    greeting_started = True
                    current_turn_id += 1
                    greeting_turn = current_turn_id
                    playback_cancel_event.clear()
                    greeting_task = asyncio.create_task(play_initial_greeting(stream_sid, greeting_turn))

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
        set_active_progress_callback(None)
        session_active = False
        playback_cancel_event.set()
        call_telemetry.end_call()

        if progress_tts_task and not progress_tts_task.done():
            progress_tts_task.cancel()
            try:
                await progress_tts_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

        if tts_task and not tts_task.done():
            tts_task.cancel()
            try:
                await tts_task
            except asyncio.CancelledError:
                pass

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
