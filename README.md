# Saarthi AI — Production Conversational Voice Travel Agent

> **Enterprise-grade, real-time telephony AI voice agent for bus travel search, seat recommendation, transactional seat holding, booking, Razorpay payment link generation, and automated omnichannel WhatsApp & email e-ticket delivery.**

Saarthi AI integrates directly with **Exotel Telephony**, **Sarvam AI** (Realtime STT & Streaming TTS), **Amazon Bedrock** (LLM reasoning via Strands Agents SDK), and the **Snehith Travels Booking Platform**.

---

## Table of Contents

1. [Overview & Architecture](#overview--architecture)
2. [Key Capabilities & Features](#key-capabilities--features)
3. [Live Dial-in Lines & How to Test](#live-dial-in-lines--how-to-test)
4. [External Services & Requirements](#external-services--requirements)
5. [End-to-End Call Lifecycle](#end-to-end-call-lifecycle)
6. [Repository Structure](#repository-structure)
7. [Environment Variables Reference](#environment-variables-reference)
8. [Setup, Deployment & Testing](#setup-deployment--testing)
9. [Telemetry & Turn Observability](#telemetry--turn-observability)

---

## Overview & Architecture

Saarthi AI functions as an intelligent voice gateway over standard telephony (PSTN/mobile). When a customer calls the dedicated phone number and enters their access PIN, the call is bridged via an Exotel WebSocket media stream directly into Saarthi AI's FastAPI gateway running on port `8001`.

```
                        ┌───────────────────────────────┐
                        │      Customer Phone Call      │
                        └──────────────┬────────────────┘
                                       │ PSTN
                                       ▼
                        ┌───────────────────────────────┐
                        │     Exotel Telephony IVR      │
                        │    (PIN Verification Applet)  │
                        └──────────────┬────────────────┘
                                       │ 8kHz PCM WebSocket
                                       ▼
                        ┌───────────────────────────────┐
                        │    Cloudflare / Nginx (:80)   │
                        │    (wss://opsfusionn.online)  │
                        └──────────────┬────────────────┘
                                       │ Proxy /voice
                                       ▼
                        ┌───────────────────────────────┐
                        │    Saarthi Voice Gateway      │
                        │    (FastAPI WebSocket :8001)  │
                        └──────┬─────────────────▲──────┘
             Audio Chunks (PCM)│                 │ Streaming PCM Chunks
                               ▼                 │
     ┌────────────────────────────┐   ┌──────────┴──────────────────┐
     │    Sarvam Realtime STT     │   │   Sarvam Bulbul v3 TTS      │
     │   (saaras:v3-realtime)     │   │   (Streaming WebSocket)     │
     └─────────────┬──────────────┘   └──────────▲──────────────────┘
                   │ Transcribed Text            │ Natural Speech
                   ▼                             │
     ┌───────────────────────────────────────────┴──────────────────┐
     │               Strands Agents / Amazon Bedrock                │
     │                 (openai.gpt-oss-120b-1:0)                    │
     │            Isolated Session Context per Phone Call           │
     └─────────────────────────────┬────────────────────────────────┘
                                   │ Deterministic Tools
                                   ▼
     ┌──────────────────────────────────────────────────────────────┐
     │                 Snehith Travels REST API                     │
     │  - Bus Search & Availability      - Razorpay Payment Link    │
     │  - Seat Layout & Group Holds      - Webhook Verification     │
     │  - Booking Creation               - Digital Ticket Retrieval │
     └──────────────┬────────────────────────────┬──────────────────┘
                    │                            │
                    ▼                            ▼
     ┌────────────────────────────┐   ┌─────────────────────────────┐
     │ Meta WhatsApp Cloud API    │   │         SMTP Server         │
     │ - Payment Link Template    │   │ - Ticket PDF with QR Code   │
     │ - Digital Ticket PDF       │   │ - Delivered to Any Email    │
     └────────────────────────────┘   └─────────────────────────────┘
```

---

## Key Capabilities & Features

### 1. Sub-Second Real-Time Telephony Pipeline
- **Exotel WebSocket Audio Streaming**: Ingests and transmits 8,000 Hz, 16-bit linear PCM audio frames with ultra-low latency.
- **Sarvam Realtime Speech-to-Text (STT)**: Uses `saaras:v3-realtime` to deliver sub-second speech transcription with full support for Indian accents and mixed languages (code-switching).
- **Sarvam Bulbul v3 Streaming Text-to-Speech (TTS)**: Delivers chunk-by-chunk streaming PCM audio synthesis, reaching **first-audio playback in under 350ms**.

### 2. Turn-Level Concurrency & Barge-In Protection
- **Per-Call Audio Playback Coordinator**: Uses atomic `asyncio.Lock` coordination so that only one audio producer (progress TTS or final agent TTS) writes to the Exotel WebSocket media stream at any moment.
- **Hardware-Level Customer Barge-In**: Real-time Voice Activity Detection (VAD) immediately interrupts active TTS playback, halts streaming chunks, and releases audio locks the moment customer speech begins.
- **Turn Isolation**: Every turn and audio stream has a unique `turn_id` and `generation_id` ensuring stale or superseded audio frames are immediately discarded.

### 3. Tool Progress Speech
- Eliminates "dead air" when executing multi-step backend operations (e.g. generating payment links or creating bookings).
- While the background tool executes, Saarthi speaks an immediate reassuring update:
  > *"I'm generating your payment link and sending it to WhatsApp. Just a moment."*
- When the tool finishes, any remaining progress speech cleanly finishes before the final confirmation is played.

### 4. Multilingual & Cross-Lingual Guardrails
- Supports **English, Hindi, and Telugu**.
- Dynamic language detection ensures Saarthi responds in the language spoken by the customer.
- **Contamination Filtering**: Strips unwanted mixed-script artifacts (e.g. Telugu script leaking into an English sentence) before synthesis.
- **Spoken Time Formatting**: Converts 24-hour military timestamps (e.g. `21:30`) into natural spoken conversational time (e.g. `9:30 PM`).

### 5. Deterministic Bus Booking & Seat Hold Engine
- **Bus Search**: Filters by origin, destination, journey date, sleeper/seater types, and sorting.
- **Seat Recommendations**: Recommends optimal seats (lower berth, window, front, or adjacent group seats).
- **Transactional Seat Holds**: Prevents double-booking via temporary 10-minute pessimistic database holds.
- **Booking Creation**: Confirms passenger details, age, gender, and contact info.
- **Payment Link Delivery**: Dispatches single official Razorpay links directly to the customer's WhatsApp.
- **Authoritative Payment Verification**: Checks PostgreSQL database status—never trusts client claims.
- **Digital E-Ticket Dispatch**: Generates branded PDF tickets with embedded QR codes and sends them via WhatsApp and Email.

---

## Live Dial-in Lines & How to Test

To test the voice bot, dial either of the following numbers from any mobile phone:

| Line | Mobile Number | Dial-Pad PIN / Password | Role / Status |
|---|---|---|---|
| **Line 1 (Main)** | **`09513885656`** | **`7396959239#`** | 🟢 **Primary Line (Recommended)** |
| **Line 2 (Backup)** | **`09513886363`** | **`8712145983#`** | 🟡 **Trial Line (Backup)** |

### Calling Instructions
1. Call the mobile number from your phone.
2. When prompted by the automated IVR welcome menu, enter the **Dial-Pad PIN** followed by `#` on your phone's keypad.
3. Once connected, speak naturally in **English, Hindi, or Telugu**.
4. Saarthi will search available buses, check live seats, place a hold, book your seat, and text you the payment link.

> [!NOTE]
> **Testing Delivery Notice**:
> - **WhatsApp Restriction**: Due to Meta Cloud API sandbox mode in development, the WhatsApp payment link and ticket PDF will **only be delivered to `+91 8712145983`**. Test with this number when booking over the phone.
> - **Email Delivery for All**: **Any valid email address** provided during the call will receive the ticket PDF confirmation.

---

## External Services & Requirements

### 1. Exotel Telephony
- **Virtual Numbers (VN)**: Two active Exotel numbers (`09513885656` and `09513886363`).
- **Exotel Applet Flow**:
  1. **Greeting Applet**: Plays introductory prompt requesting the PIN.
  2. **Passthru / Gather Applet**: Validates PIN (`7396959239#` or `8712145983#`).
  3. **Media Stream Applet**: Initiates bi-directional WebSocket connection to:
     ```
     wss://opsfusionn.online/voice
     ```
- **Audio Specs**: 8,000 Hz, 16-bit linear PCM, mono, base64-encoded frames.

### 2. Sarvam AI
- **Realtime STT**:
  - Endpoint: `wss://api.sarvam.ai/speech-to-text-realtime/ws`
  - Model: `saaras:v3-realtime`
  - Languages: `en-IN`, `hi-IN`, `te-IN`
  - Sample Rate: `8000`
- **Streaming Bulbul v3 TTS**:
  - Endpoint: `wss://api.sarvam.ai/text-to-speech-streaming`
  - Model: `bulbul:v3`
  - Speakers: `kavya` / `ananya`
  - Streaming audio format: 8kHz PCM chunks
- **Key Manager**: Supports rotational API keys with automatic failover to prevent rate-limit interruptions.

### 3. Amazon Bedrock
- **Region**: `ap-south-1` (AWS Mumbai)
- **Model**: `openai.gpt-oss-120b-1:0`
- **SDK**: Strands Agents (`strands-agents`)
- **Credentials**: Standard AWS credentials via IAM role or `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` in environment.

### 4. Snehith Travels Backend REST API
- **Base URL**: `https://opsfusionn.online`
- **Key Endpoints**:
  - `GET /api/buses/search` — Search buses by date and route.
  - `GET /api/buses/{id}/seats` — Retrieve seat layout and availability.
  - `POST /api/seats/hold` — Place temporary 10-minute hold on seats.
  - `POST /api/bookings` — Create a pending booking with passenger data.
  - `POST /api/payments` — Generate Razorpay payment link.
  - `POST /api/payments/deliver-link` — Dispatch payment link via WhatsApp.
  - `GET /api/payments/{id}` — Authoritative payment status.
  - `GET /api/tickets/{booking_id}` — Retrieve confirmed ticket details.

### 5. Meta WhatsApp Cloud API
- **Graph API**: `v22.0`
- **Pre-Approved Template**: `snehith_travels_payment_link` (Language: `en`)
- **Digital Ticket PDF**: Dispatched as a document attachment with dynamic booking captions.

### 6. SMTP Email Gateway
- **Service**: Standard TLS/SSL SMTP server.
- **Attachment**: Generates and attaches high-resolution PDF tickets with QR verification codes.

---

## End-to-End Call Lifecycle

1. **Call Connected**: Exotel opens a WebSocket connection to `/voice`.
2. **Session Initialization**: Saarthi initializes an isolated agent instance and sends the initial greeting:
   > *"Hi! I'm Saarthi, your travel assistant. How can I help you today?"*
3. **Customer Speaks**: Customer says: *"I want a bus from Hyderabad to Vijayawada tomorrow."*
4. **Sarvam Realtime STT**: Converts speech to text chunk-by-chunk and triggers utterance completion.
5. **Agent Reasoning & Progress Speech**:
   - Agent invokes `search_buses(...)`.
   - Tool completes in ~200ms; agent suggests the best matching bus.
6. **Seat Recommendation & Hold**:
   - Customer requests a seat: *"Give me a window seat on the lower deck."*
   - Agent invokes `recommend_seats(...)` and immediately executes `hold_seats(...)` with a 10-minute hold token.
7. **Booking Details**:
   - Customer provides passenger name and age.
   - Agent creates the booking via `create_booking(...)`.
8. **WhatsApp Payment Delivery**:
   - Customer provides WhatsApp number: `8712145983`.
   - Progress Speech plays immediately: *"I'm generating your payment link and sending it to WhatsApp. Just a moment."*
   - Agent calls `deliver_payment_link(...)`.
   - Single approved WhatsApp template arrives on customer's phone with Razorpay checkout URL.
9. **Payment & Confirmation**:
   - Customer clicks the link and pays.
   - Customer says: *"I have paid."*
   - Agent calls `get_payment_status(...)`. The database confirms `PAID`.
10. **Ticket Delivery**:
    - Agent invokes `deliver_ticket_to_whatsapp(...)` and/or `deliver_ticket_to_email(...)`.
    - Ticket PDF with QR code is delivered instantly.

---

## Repository Structure

```
/home/ubuntu/saarthi-ai/
├── agent/
│   └── agent.py                 # Strands BedrockModel setup, system prompts, tool bindings
├── voice/
│   ├── gateway.py               # Exotel WebSocket server & full turn orchestrator
│   ├── streaming_tts.py         # Sarvam Bulbul v3 streaming WebSocket TTS client
│   ├── audio_coordinator.py     # Per-turn audio lock & barge-in cancellation coordinator
│   ├── key_manager.py           # Rotational Sarvam API key manager with fallback
│   ├── progress.py              # In-flight tool progress speech manager
│   ├── sanitizer.py             # Reasoning tag filters, multilingual cleaning, length limits
│   ├── time_formatter.py        # 24hr to spoken 12hr AM/PM converter
│   └── telemetry.py             # Turn-by-turn latency instrumentation
├── tools/
│   ├── bus_tools.py             # Deterministic tools invoked by the Bedrock agent
│   └── seat_optimizer.py       # Seat layout reasoning & adjacent group seat allocator
├── integrations/
│   ├── snehith_client.py        # Async HTTP client for Snehith Travels REST API
│   ├── whatsapp_client.py       # Meta WhatsApp Cloud API client (document uploads & messaging)
│   └── email_client.py          # SMTP client for ticket PDF email delivery
├── utils/
│   └── ticket_pdf.py            # ReportLab PDF ticket generator with QR code
├── config/
│   └── settings.py              # Environment variable loading & validation
├── tests/
│   ├── test_voice_audio_suite.py       # Concurrency, audio locking, and barge-in tests
│   ├── test_whatsapp_audit_suite.py   # WhatsApp normalization & dispatch tests
│   ├── test_multilingual_suite.py     # Hindi, Telugu, and English sanitization tests
│   ├── test_final_ux_suite.py         # Comprehensive voice UX and progress speech tests
│   └── ...                            # 23 comprehensive test suites
├── Dockerfile                   # Production container definition (Python 3.12-slim)
├── requirements.txt             # Python dependencies
└── pytest.ini                   # Pytest configuration
```

---

## Environment Variables Reference

Create a `.env` file in the root directory:

```ini
# Snehith Travels Backend REST API
SNEHITH_API_URL=https://opsfusionn.online
SNEHITH_ADMIN_EMAIL=admin@snehithtravels.com
SNEHITH_ADMIN_PASSWORD=your_secure_admin_password

# Sarvam AI (Realtime STT & Bulbul v3 Streaming TTS)
SARVAM_API_KEY=sk_primary_key_here
SARVAM_FALLBACK_API_KEYS=sk_backup_key_1,sk_backup_key_2
SARVAM_STT_MODEL=saaras:v3-realtime
SARVAM_LANGUAGE_CODE=en-IN
SARVAM_SAMPLE_RATE=8000
SARVAM_STREAM_TYPE=balanced

# Meta WhatsApp Cloud API
META_WHATSAPP_ACCESS_TOKEN=your_meta_system_user_token
META_WHATSAPP_PHONE_NUMBER_ID=1341186229071206
META_WHATSAPP_BUSINESS_ACCOUNT_ID=4062573757379650
META_WHATSAPP_TICKET_TEMPLATE_NAME=snehith_travels_ticket_pdf

# SMTP Email Ticket Delivery
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=notifications@snehithtravels.com
SMTP_PASSWORD=your_app_password
SMTP_FROM_EMAIL=tickets@snehithtravels.com

# AWS Bedrock Credentials (if not using IAM instance profile)
AWS_REGION=ap-south-1
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key
```

---

## Setup, Deployment & Testing

### Running via Docker (Production)

The voice service runs as the `saarthi_voice` container on port `8001`:

```bash
# Build the Docker image
docker build -t saarthi-voice:latest .

# Run the container
docker run -d \
  --name saarthi_voice \
  --restart always \
  --network snehith-travels_default \
  -p 8001:8001 \
  --env-file .env \
  saarthi-voice:latest
```

### Health Check

Verify that the voice gateway is running and connected to Sarvam:

```bash
curl -s http://localhost:8001/health | jq .
```

Expected output:
```json
{
  "status": "ok",
  "service": "saarthi-voice-gateway",
  "stt": "sarvam-realtime-websocket",
  "tts": "sarvam-bulbul-v3",
  "agent": "strands-bedrock",
  "model": "saaras:v3-realtime",
  "language_code": "en-IN",
  "sample_rate": 8000,
  "sarvam_keys_count": 3,
  "sarvam_active_key_index": 1
}
```

### Running the Test Suites

Run the full automated test suite covering all audio, agent, and integration behaviors:

```bash
pytest tests/ -v
```

Run specific test suites:
```bash
# Verify Audio Concurrency & Barge-In
pytest tests/test_voice_audio_suite.py -v

# Verify Multilingual Sanitization
pytest tests/test_multilingual_suite.py -v

# Verify WhatsApp Normalization & Document Delivery
pytest tests/test_whatsapp_audit_suite.py -v

# Verify End-to-End Voice UX
pytest tests/test_final_ux_suite.py -v
```

---

## Telemetry & Turn Observability

Saarthi AI logs detailed millisecond-level telemetry at the end of every voice turn:

```text
VOICE TURN 91
  STT_DURATION_MS=3621
  STT_FINAL_LATENCY_MS=142
  AGENT_START_DELAY_MS=0
  AGENT_TOTAL_MS=3999
  TTS_FIRST_AUDIO_MS=285
  TTS_TOTAL_MS=3240
  PLAYBACK_MS=3100
  RESPONSE_LATENCY_MS=780
  STATUS=COMPLETED
```

When a phone call concludes, a comprehensive call summary is recorded:

```text
CALL LATENCY SUMMARY
  turns=63
  avg_stt_final_latency_ms=134
  avg_agent_latency_ms=1156
  avg_tts_first_audio_ms=357
  avg_response_latency_ms=1937
  total_call_duration_ms=657984
  total_customer_speech_ms=180537
  total_saarthi_playback_ms=209184
```

---

## License

Proprietary — Developed for Snehith Travels Demo & Hackathon Platform.
All rights reserved.
