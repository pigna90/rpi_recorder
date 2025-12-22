import sounddevice as sd
import wave
import time
import os
import audioop
import requests
import threading
import struct
import logging
import signal
import sys
from dotenv import load_dotenv

# Systemd watchdog support
try:
    import systemd.daemon
    SYSTEMD_AVAILABLE = True
except ImportError:
    SYSTEMD_AVAILABLE = False

# OLED imports
from luma.core.interface.serial import i2c
from luma.oled.device import sh1106
from PIL import Image, ImageDraw, ImageFont

load_dotenv()

# Configure logging - lightweight setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

SAMPLE_RATE = 44100
CHANNELS = 4
DEVICE = 0

BLOCK_DURATION = 0.1
BLOCK_SIZE = int(SAMPLE_RATE * BLOCK_DURATION)

THRESHOLD = 10000
SILENCE_SECONDS = 2.0
MIN_RECORD_SECONDS = 0.7

WEBHOOK_URL = os.getenv("WEBHOOK_URL")
if not WEBHOOK_URL and os.getenv("WEBHOOK_ENABLED", "false").lower() == "true":
    logger.error("WEBHOOK_URL not set but webhooks are enabled. Please set WEBHOOK_URL in .env file")
    exit(1)
WEBHOOK_ENABLED = os.getenv("WEBHOOK_ENABLED", "true").lower() == "true"

os.makedirs("recordings", exist_ok=True)


# ---------- MIXING: 4ch int16 -> stereo (full volume sum) ----------

def mix4_to_stereo_sum(raw_bytes):
    """
    Input: 4ch int16 interleaved frames [ch1,ch2,ch3,ch4,...]
    Output: stereo int16 frames [M,M,...] where M = sum of all channels (clamped).
    """
    samples = struct.iter_unpack("<hhhh", raw_bytes)  # ch1,ch2,ch3,ch4 per frame
    out = bytearray()

    for ch1, ch2, ch3, ch4 in samples:
        # Sum all channels (preserves full volume)
        m = ch1 + ch2 + ch3 + ch4

        # Clamp to int16 range to prevent overflow distortion
        m = max(-32768, min(32767, m))
        out.extend(struct.pack("<hh", m, m))  # L = m, R = m

    return bytes(out)


# ---------- OLED HELPERS (SAFE, ONLY ON STATE CHANGES) ----------

def init_display():
    try:
        serial = i2c(port=1, address=0x3C)
        device = sh1106(serial)
        device.clear()
        return device
    except Exception as e:
        logger.warning(f"OLED init failed: {e}")
        return None


def draw_large_ready(draw, device_width, device_height):
    """Draw large READY text manually using rectangles"""
    # Calculate letter dimensions - assume 128x64 display
    letter_width = 20
    letter_height = 30
    letter_spacing = 4
    stroke_width = 3

    # Calculate total width for "READY" (5 letters)
    total_width = 5 * letter_width + 4 * letter_spacing
    start_x = (device_width - total_width) // 2
    start_y = (device_height - letter_height) // 2

    # Draw R
    x = start_x
    y = start_y
    draw.rectangle([x, y, x + stroke_width, y + letter_height], fill=255)
    draw.rectangle([x, y, x + letter_width - stroke_width, y + stroke_width], fill=255)
    mid_y = y + letter_height//2 - stroke_width//2
    draw.rectangle([x, mid_y, x + letter_width - stroke_width, mid_y + stroke_width], fill=255)
    draw.rectangle([x + letter_width - stroke_width, y, x + letter_width, y + letter_height//2 + stroke_width//2], fill=255)
    # Simple diagonal for R
    for i in range(letter_height//2):
        leg_x = x + stroke_width + i//2
        leg_y = mid_y + stroke_width + i
        if leg_x < x + letter_width and leg_y < y + letter_height:
            draw.rectangle([leg_x, leg_y, leg_x + stroke_width, leg_y + 1], fill=255)

    # Draw E
    x += letter_width + letter_spacing
    draw.rectangle([x, y, x + stroke_width, y + letter_height], fill=255)
    draw.rectangle([x, y, x + letter_width, y + stroke_width], fill=255)
    draw.rectangle([x, mid_y, x + letter_width - 3, mid_y + stroke_width], fill=255)
    draw.rectangle([x, y + letter_height - stroke_width, x + letter_width, y + letter_height], fill=255)

    # Draw A - simple design
    x += letter_width + letter_spacing
    # Left vertical line (full height)
    draw.rectangle([x, y, x + stroke_width, y + letter_height], fill=255)
    # Right vertical line (full height)
    draw.rectangle([x + letter_width - stroke_width, y, x + letter_width, y + letter_height], fill=255)
    # Top horizontal (connecting the tops)
    draw.rectangle([x, y, x + letter_width, y + stroke_width], fill=255)
    # Middle horizontal bar
    draw.rectangle([x + stroke_width, y + letter_height//2, x + letter_width - stroke_width, y + letter_height//2 + stroke_width], fill=255)

    # Draw D
    x += letter_width + letter_spacing
    draw.rectangle([x, y, x + stroke_width, y + letter_height], fill=255)
    draw.rectangle([x, y, x + letter_width - 4, y + stroke_width], fill=255)
    draw.rectangle([x, y + letter_height - stroke_width, x + letter_width - 4, y + letter_height], fill=255)
    draw.rectangle([x + letter_width - stroke_width, y + stroke_width, x + letter_width, y + letter_height - stroke_width], fill=255)

    # Draw Y
    x += letter_width + letter_spacing
    draw.rectangle([x + letter_width//2 - stroke_width//2, y + letter_height//2, x + letter_width//2 + stroke_width//2, y + letter_height], fill=255)
    # Diagonal parts of Y
    for i in range(letter_height//2):
        left_x = x + i//2
        right_x = x + letter_width - i//2
        diag_y = y + i
        draw.rectangle([left_x, diag_y, left_x + 1, diag_y + 1], fill=255)
        draw.rectangle([right_x, diag_y, right_x + 1, diag_y + 1], fill=255)


def draw_large_rec(draw, device_width, device_height):
    """Draw large REC letters manually using rectangles"""
    # Calculate letter dimensions - assume 128x64 display
    letter_width = 24
    letter_height = 40
    letter_spacing = 8
    stroke_width = 4

    total_width = 3 * letter_width + 2 * letter_spacing
    start_x = (device_width - total_width) // 2
    start_y = (device_height - letter_height) // 2 - 6

    # Draw R
    x = start_x
    y = start_y
    # Main vertical line (left side)
    draw.rectangle([x, y, x + stroke_width, y + letter_height], fill=255)
    # Top horizontal bar
    draw.rectangle([x, y, x + letter_width - stroke_width, y + stroke_width], fill=255)
    # Middle horizontal bar
    mid_y = y + letter_height//2 - stroke_width//2
    draw.rectangle([x, mid_y, x + letter_width - stroke_width, mid_y + stroke_width], fill=255)
    # Right vertical bar (top half only)
    draw.rectangle([x + letter_width - stroke_width, y, x + letter_width, y + letter_height//2 + stroke_width//2], fill=255)
    # Diagonal leg - make it reach all the way to the bottom
    leg_start_x = x + stroke_width + 2
    leg_start_y = mid_y + stroke_width
    leg_end_y = y + letter_height
    leg_height = leg_end_y - leg_start_y
    for i in range(leg_height):
        leg_x = leg_start_x + (i * (letter_width - stroke_width - 6)) // leg_height
        leg_y = leg_start_y + i
        draw.rectangle([leg_x, leg_y, leg_x + stroke_width, leg_y + 1], fill=255)

    # Draw E
    x += letter_width + letter_spacing
    # Vertical line
    draw.rectangle([x, y, x + stroke_width, y + letter_height], fill=255)
    # Top horizontal
    draw.rectangle([x, y, x + letter_width, y + stroke_width], fill=255)
    # Middle horizontal
    draw.rectangle([x, y + letter_height//2 - stroke_width//2, x + letter_width - 4, y + letter_height//2 + stroke_width//2], fill=255)
    # Bottom horizontal
    draw.rectangle([x, y + letter_height - stroke_width, x + letter_width, y + letter_height], fill=255)

    # Draw C
    x += letter_width + letter_spacing
    # Left vertical
    draw.rectangle([x, y + stroke_width, x + stroke_width, y + letter_height - stroke_width], fill=255)
    # Top horizontal
    draw.rectangle([x, y, x + letter_width, y + stroke_width], fill=255)
    # Bottom horizontal
    draw.rectangle([x, y + letter_height - stroke_width, x + letter_width, y + letter_height], fill=255)


def render_text_center(device, text):
    if device is None:
        return
    img = Image.new("1", (device.width, device.height))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    x = (device.width - w) // 2
    y = (device.height - h) // 2
    draw.text((x, y), text, fill=255, font=font)

    device.display(img)


def show_ready(device):
    if device is None:
        return
    img = Image.new("1", (device.width, device.height))
    draw = ImageDraw.Draw(img)
    draw_large_ready(draw, device.width, device.height)
    device.display(img)


def show_rec(device):
    if device is None:
        return
    img = Image.new("1", (device.width, device.height))
    draw = ImageDraw.Draw(img)
    draw_large_rec(draw, device.width, device.height)
    device.display(img)


# ---------- AUDIO TIMEOUT HANDLER ----------

def audio_timeout_handler(signum, frame):
    """Handle audio stream timeout - exit cleanly for systemd restart"""
    logger.error("Audio stream timeout detected - audio hardware may be hung")
    logger.error("Exiting for systemd restart...")
    sys.exit(1)


# ---------- AUDIO + WEBHOOK ----------

def open_new_wav():
    ts = time.strftime("%Y%m%d_%H%M%S")
    filename = f"recordings/vad_{ts}_4ch.wav"
    wf = wave.open(filename, "wb")
    wf.setnchannels(4)       # 4-channel during recording (no processing)
    wf.setsampwidth(2)       # int16
    wf.setframerate(SAMPLE_RATE)
    return wf, filename


def send_webhook(file_path):
    try:
        with open(file_path, 'rb') as audio_file:
            file_data = audio_file.read()

        filename = file_path.split('/')[-1]
        logger.info(f"Sending webhook: {filename}")

        if filename.endswith('.opus'):
            content_type = 'audio/opus'
        elif filename.endswith('.mp3'):
            content_type = 'audio/mpeg'
        else:
            content_type = 'audio/wav'

        response = requests.post(
            WEBHOOK_URL,
            data=file_data,
            headers={
                'Content-Type': content_type,
                'Content-Disposition': f'attachment; filename="{filename}"',
                'X-Timestamp': time.strftime("%Y-%m-%d %H:%M:%S")
            },
            timeout=60,
            verify=True
        )

        if response.status_code == 200:
            logger.info(f"Webhook sent successfully: {filename}")
        else:
            logger.error(f"Webhook failed (status {response.status_code}): {filename}")

    except requests.exceptions.SSLError as e:
        logger.warning(f"SSL error, retrying without verification: {filename}")
        try:
            response = requests.post(
                WEBHOOK_URL,
                data=file_data,
                headers={
                    'Content-Type': content_type,
                    'Content-Disposition': f'attachment; filename="{filename}"',
                    'X-Timestamp': time.strftime("%Y-%m-%d %H:%M:%S")
                },
                timeout=60,
                verify=False
            )
            if response.status_code == 200:
                logger.info(f"Webhook sent (no SSL verify): {filename}")
            else:
                logger.error(f"Webhook failed (status {response.status_code}): {filename}")
        except Exception as retry_e:
            logger.error(f"Webhook retry failed: {filename} - {retry_e}")
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection error: {filename} - {e}")
    except requests.exceptions.Timeout:
        logger.warning(f"Webhook timeout: {filename}")
    except Exception as e:
        logger.error(f"Webhook error: {filename} - {e}")


def send_webhook_async(file_path):
    try:
        webhook_thread = threading.Thread(target=send_webhook, args=(file_path,), daemon=True)
        webhook_thread.start()
    except Exception as e:
        logger.error(f"Failed to start webhook thread: {e}")


def normalize_audio_file(file_path):
    """Normalize audio file to maximize volume without clipping"""
    try:
        # Read the original file
        with wave.open(file_path, 'rb') as wf:
            frames = wf.readframes(wf.getnframes())
            params = wf.getparams()

        # Find peak amplitude across all channels (4-channel int16)
        peak = audioop.max(frames, 2)  # 2 bytes per sample for int16

        if peak == 0:
            logger.warning(f"Normalization skipped: {file_path} (silent audio)")
            return

        # Calculate scaling factor (target 95% of max to leave headroom)
        target_level = int(32767 * 0.95)  # 95% of int16 max
        scale_factor = target_level / peak

        if scale_factor <= 1.0:
            logger.info(f"Normalization skipped: {file_path} (already at good level)")
            return

        # Scale the audio
        normalized_frames = audioop.mul(frames, 2, scale_factor)

        # Write normalized version (replace original)
        with wave.open(file_path, 'wb') as wf:
            wf.setparams(params)
            wf.writeframes(normalized_frames)

        logger.info(f"Normalized {file_path} (boost: {scale_factor:.1f}x)")

    except Exception as e:
        logger.error(f"Normalization error for {file_path}: {e}")


def convert_4ch_to_stereo(input_path):
    """Convert 4-channel file to stereo file using summing mix"""
    try:
        # Generate stereo filename
        stereo_path = input_path.replace("_4ch.wav", "_stereo.wav")

        # Read 4-channel file
        with wave.open(input_path, 'rb') as wf_in:
            frames = wf_in.readframes(wf_in.getnframes())
            params = wf_in.getparams()

        # Mix to stereo using our summing function
        stereo_frames = mix4_to_stereo_sum(frames)

        # Write stereo file
        with wave.open(stereo_path, 'wb') as wf_out:
            wf_out.setnchannels(2)  # stereo
            wf_out.setsampwidth(params.sampwidth)
            wf_out.setframerate(params.framerate)
            wf_out.writeframes(stereo_frames)

        logger.info(f"Converted to stereo: {stereo_path}")
        return stereo_path

    except Exception as e:
        logger.error(f"4ch to stereo conversion error: {e}")
        return input_path  # Return original if conversion fails


def normalize_audio_async(file_path):
    """Normalize audio in background thread"""
    try:
        normalize_thread = threading.Thread(target=normalize_audio_file, args=(file_path,), daemon=True)
        normalize_thread.start()
    except Exception as e:
        logger.error(f"Failed to start normalization thread: {e}")


def systemd_watchdog_loop():
    """Background thread to send systemd watchdog pings every 15 seconds"""
    while True:
        try:
            time.sleep(15)  # Send ping every 15 seconds (half of the 30s timeout)
            if SYSTEMD_AVAILABLE:
                systemd.daemon.notify("WATCHDOG=1")
        except Exception as e:
            logger.error(f"Systemd watchdog error: {e}")


def start_systemd_watchdog():
    """Start systemd watchdog background thread"""
    if SYSTEMD_AVAILABLE:
        try:
            watchdog_thread = threading.Thread(target=systemd_watchdog_loop, daemon=True)
            watchdog_thread.start()
            logger.info("Systemd watchdog thread started (15s interval)")
        except Exception as e:
            logger.error(f"Failed to start systemd watchdog thread: {e}")


def main():
    # try:
    #     os.nice(-10)
    #     logger.info("Set higher process priority for audio")
    # except (PermissionError, OSError):
    #     logger.warning("Could not change process priority (permission or OS limitation)")

    # Set up audio stream timeout handler
    signal.signal(signal.SIGALRM, audio_timeout_handler)
    logger.info("Audio stream timeout handler configured (10s timeout)")

    # Systemd setup
    if SYSTEMD_AVAILABLE:
        systemd.daemon.notify("READY=1")
        start_systemd_watchdog()
    else:
        logger.info("Systemd watchdog not available (running manually)")

    # Init OLED
    device = init_display()
    show_ready(device)

    recording = False
    wav_file = None
    current_filename = None
    record_start_time = None
    silence_time = 0.0

    logger.info("VAD recorder ready - listening for audio")
    logger.info(f"Threshold: {THRESHOLD}, Silence timeout: {SILENCE_SECONDS}s")
    logger.info(f"Webhook: {'enabled' if WEBHOOK_ENABLED else 'disabled'}")

    with sd.RawInputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="int16",
        device=DEVICE,
        blocksize=BLOCK_SIZE,
        latency=0.6,
    ) as stream:
        try:
            while True:
                # Set 10-second timeout for audio stream read
                signal.alarm(10)
                data_raw, overflowed = stream.read(BLOCK_SIZE)
                signal.alarm(0)  # Cancel timeout - read completed successfully

                if overflowed:
                    logger.warning("Audio overflow (XRUN) - system too slow for real-time audio")

                data = bytes(data_raw)

                # VAD uses all 4 channels as before
                channel_levels = []
                for ch in range(CHANNELS):
                    ch_bytes = data[ch * 2 :: CHANNELS * 2]
                    ch_level = audioop.rms(ch_bytes, 2)
                    channel_levels.append(ch_level)

                level = max(channel_levels)

                if not recording:
                    if level >= THRESHOLD:
                        wav_file, current_filename = open_new_wav()
                        record_start_time = time.time()
                        silence_time = 0.0
                        recording = True

                        wav_file.writeframes(data)

                        logger.info(f"Recording started (level={level})")
                        show_rec(device)
                else:
                    wav_file.writeframes(data)

                    if level < THRESHOLD:
                        silence_time += BLOCK_DURATION
                    else:
                        silence_time = 0.0

                    if silence_time >= SILENCE_SECONDS:
                        duration = time.time() - record_start_time
                        wav_file.close()

                        if duration < MIN_RECORD_SECONDS:
                            try:
                                os.remove(current_filename)
                                logger.info(f"Recording too short ({duration:.2f}s), deleted")
                            except OSError:
                                pass
                        else:
                            logger.info(f"Recording completed: {duration:.2f}s")
                            # Convert 4ch to stereo, then normalize
                            stereo_filename = convert_4ch_to_stereo(current_filename)
                            normalize_audio_file(stereo_filename)
                            if WEBHOOK_ENABLED:
                                send_webhook_async(stereo_filename)  # Send stereo normalized file
                            else:
                                logger.info("Webhook disabled - recording saved locally")
                            # Clean up 4ch file to save space
                            try:
                                os.remove(current_filename)
                                logger.info(f"Cleaned up 4ch file: {current_filename}")
                            except OSError:
                                pass

                        recording = False
                        wav_file = None
                        current_filename = None
                        record_start_time = None
                        silence_time = 0.0
                        logger.info("Ready for next recording")
                        show_ready(device)

        except KeyboardInterrupt:
            logger.info("Recording interrupted by user")
            if recording and wav_file is not None:
                duration = time.time() - record_start_time
                wav_file.close()

                if duration >= MIN_RECORD_SECONDS:
                    logger.info(f"Final recording saved: {duration:.2f}s")
                    # Convert 4ch to stereo, then normalize
                    stereo_filename = convert_4ch_to_stereo(current_filename)
                    normalize_audio_file(stereo_filename)
                    if WEBHOOK_ENABLED:
                        send_webhook_async(stereo_filename)  # Send stereo normalized file
                    else:
                        logger.info("Webhook disabled - recording saved locally")
                    # Clean up 4ch file to save space
                    try:
                        os.remove(current_filename)
                        logger.info(f"Cleaned up 4ch file: {current_filename}")
                    except OSError:
                        pass
                else:
                    try:
                        os.remove(current_filename)
                        logger.info(f"Final recording too short ({duration:.2f}s), deleted")
                    except OSError:
                        pass

            show_ready(device)


if __name__ == "__main__":
    main()