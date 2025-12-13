# Raspberry Pi Voice Recorder (pi2-rec)

## Why This Project?

As a musician, I constantly forget to hit record when playing guitar, piano, or singing. Those perfect moments - a cool riff, beautiful melody, or spontaneous vocal idea - just disappear forever. This project solves that by automatically capturing everything from my instruments and keeping it all in Telegram, so I never lose another musical moment.

A voice-activated recording system for Raspberry Pi that automatically detects audio, records until silence, and sends recordings to a Telegram bot via webhook.

## Overview

This application continuously listens for audio input and:
- **Detects voice activity** - Starts recording when sound is detected above a threshold
- **Records automatically** - Continues recording until silence is detected for 1.5 seconds (configurable)
- **Displays status** - Shows "READY" or "REC" with timer on an OLED display
- **Saves recordings** - Creates timestamped WAV files in the `recordings/` directory
- **Sends to Telegram** - Delivers audio files via webhook to an n8n workflow that forwards them to a Telegram bot

Perfect for voice memos, meeting recordings, or remote audio monitoring with instant Telegram notifications.

## Hardware Requirements

- Raspberry Pi (any model with I2C support)
- Audio interface or USB microphone
- SH1106 OLED display (128x64, I2C)
- I2C connection between Pi and display

## Installation

1. Clone this repository
2. Install dependencies:
```bash
# Using uv (recommended)
uv sync

# Or using pip
pip install -e .
```

3. Enable I2C on your Raspberry Pi:
```bash
sudo raspi-config
# Navigate to: Interface Options > I2C > Enable
```

4. Create a `.env` file with your webhook URL:
```bash
WEBHOOK_URL=https://your-n8n-instance.com/webhook/rpi2-recorder
WEBHOOK_ENABLED=true
```

## Usage

Run the recorder:
```bash
uv run python recorder.py
```

The display will show "READY" when listening. When audio is detected, it switches to "REC" with a timer. Recording stops automatically after 1.5 seconds of silence.

Stop with `Ctrl+C`.

## Configuration

Key settings in `recorder.py`:
- `THRESHOLD = 0.01` - Voice detection sensitivity (lower = more sensitive)
- `SILENCE_SECONDS = 1.5` - Duration of silence before stopping recording
- `MIN_RECORD_SECONDS = 0.7` - Minimum recording length to save
- `WEBHOOK_ENABLED` - Set to `False` to disable webhook delivery

## File Output

Recordings are saved as:
```
recordings/rec_YYYYMMDD_HHMM_XhYm.wav
```

Example: `rec_20241207_1430_0h2m.wav` (recorded on Dec 7, 2024 at 2:30 PM, duration 2 minutes)

## Telegram Integration

The system works with an n8n workflow that:
1. Receives the WAV file via webhook
2. Processes it through a Telegram bot
3. Sends the audio to your specified chat

This enables remote voice memo collection with instant notifications.

## Architecture

- **Main thread**: Continuous audio processing (never blocks)
- **Background threads**: OLED display updates and webhook delivery
- **Voice Activity Detection**: RMS energy-based threshold detection
- **Hardware integration**: Custom pixel-level rendering for OLED display

## Troubleshooting

- **No audio detected**: Lower the `THRESHOLD` value
- **Too sensitive**: Raise the `THRESHOLD` value
- **Display not working**: Check I2C connections and address (default: 0x3C)
- **Webhook failures**: Check network connectivity and webhook URL