# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Raspberry Pi voice-activated recorder application (`pi2-rec`) that:
- Continuously listens for audio input using voice activity detection (VAD)
- Records audio segments when sound is detected above a threshold
- Displays recording status on an SH1106 OLED display (128x64)
- Automatically saves recordings as WAV files with timestamps
- Sends completed recordings via webhook to an external service (n8n workflow)

The application runs as a single-file Python script with hardware integration for Raspberry Pi.

## Development Commands

### Environment Setup
```bash
# Install dependencies using uv (preferred) or pip
uv sync
# OR
pip install -e .

# Copy environment template and configure
cp .env.example .env
# Edit .env with your WEBHOOK_URL and WEBHOOK_ENABLED settings
```

### Running the Application
```bash
# Run the main recorder application directly
python recorder.py
# OR with uv
uv run python recorder.py

# Stop recording with Ctrl+C
```

### System Service Management
```bash
# Install as systemd service
make install

# Service control commands
make start     # Start the service
make stop      # Stop the service
make restart   # Restart the service
make status    # Check service status
make logs      # View live service logs
```

### Development Testing
```bash
# Test without webhook delivery
# Set WEBHOOK_ENABLED=false in .env file

# Check service logs for debugging
sudo journalctl -u pi2-rec.service -f
```

## Architecture

### Core Components

**Audio Processing Pipeline:**
- Voice Activity Detection (VAD) using RMS energy thresholding
- Continuous audio stream processing in 0.1s blocks (4410 samples at 44.1kHz)
- Silence detection with configurable timeout (1.5s default)
- Audio trimming to remove excessive silence from recording end

**Hardware Integration:**
- OLED Display (SH1106, 128x64, I2C address 0x3C): Custom pixel-level text rendering for "READY" and "REC" states with real-time timer
- Audio Input: Default system audio device (configurable via DEVICE constant)

**Recording Management:**
- Automatic file naming: `recordings/rec_YYYYMMDD_HHMM_XhYm.wav`
- Minimum recording duration filtering (0.7s default)
- Concurrent webhook delivery using background threads

### Configuration

**Environment Variables (`.env` file):**
- `WEBHOOK_URL`: External service endpoint for audio delivery
- `WEBHOOK_ENABLED`: Toggle for webhook functionality (`true`/`false`)

**Constants in `recorder.py`:**
- `SAMPLE_RATE = 44100`: Audio sample rate
- `CHANNELS = 4`: Number of audio input channels
- `DEVICE = 0`: Audio input device index
- `THRESHOLD = 900`: VAD sensitivity (lower = more sensitive)
- `SILENCE_SECONDS = 2.0`: Duration of silence before stopping recording
- `MIN_RECORD_SECONDS = 0.7`: Minimum recording length to save
- `BLOCK_DURATION = 0.1`: Audio processing block size (seconds)

### Threading Architecture

The application uses strategic threading to prevent audio dropouts:
- Main thread: Audio processing loop (never blocks)
- Background threads: OLED display updates, webhook delivery
- All I/O operations are non-blocking to maintain real-time audio processing

### File Structure
- `recorder.py`: Single-file application containing all functionality
- `pyproject.toml`: Python packaging and dependency configuration
- `pi2-rec.service`: Systemd service configuration for auto-start
- `Makefile`: Service management commands
- `.env.example`: Environment variables template
- `recordings/`: Auto-created directory for saved WAV files

### Deployment

The application can be deployed as a systemd service for automatic startup:

**Service Configuration:**
- User: `dietpi` (configurable in `pi2-rec.service`)
- Resource limits: 512MB RAM, 50% CPU
- Auto-restart on failure with 10s delay
- Depends on network and sound targets

**Installation Process:**
1. Install dependencies with `uv sync`
2. Configure `.env` file with webhook settings
3. Install service with `make install`
4. Start service with `make start`

## Hardware Requirements

- Raspberry Pi with I2C enabled
- SH1106 OLED display (128x64) connected via I2C
- Audio input device (USB microphone, HAT, etc.)
- Python 3.10+ environment

## Dependencies

- `sounddevice`: Real-time audio I/O
- `luma.oled`: OLED display control
- `Pillow`: Image processing for display graphics
- `requests`: HTTP webhook delivery
- `python-dotenv`: Environment variable management
- `pydub`: Audio processing utilities
- `ffmpeg-python`: Audio format conversion support