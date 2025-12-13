#!/usr/bin/env python3
"""
Audio Level Monitor for Pi2-Rec Threshold Calibration

This script continuously monitors audio levels from your 4-channel input
to help you determine the optimal THRESHOLD value for the recorder.

Shows both terminal output AND on-screen OLED display (if available).

Usage:
    python audio_monitor.py

Press Ctrl+C to stop monitoring.
"""

import sounddevice as sd
import audioop
import time

# OLED imports (same as recorder.py)
try:
    from luma.core.interface.serial import i2c
    from luma.oled.device import sh1106
    from PIL import Image, ImageDraw, ImageFont
    OLED_AVAILABLE = True
except ImportError:
    OLED_AVAILABLE = False
    print("OLED libraries not available - terminal output only")

# Use same audio configuration as recorder.py
SAMPLE_RATE = 44100
CHANNELS = 4
DEVICE = 0
BLOCK_DURATION = 0.1
BLOCK_SIZE = int(SAMPLE_RATE * BLOCK_DURATION)

def init_display():
    """Initialize OLED display (same as recorder.py)"""
    if not OLED_AVAILABLE:
        return None
    try:
        serial = i2c(port=1, address=0x3C)
        device = sh1106(serial)
        device.clear()
        return device
    except Exception as e:
        print(f"OLED init failed: {e}")
        return None

def update_oled_display(device, channel_levels, max_level, suggested_threshold, current_threshold=900):
    """Update OLED display with current audio levels and threshold info"""
    if device is None:
        return

    img = Image.new("1", (device.width, device.height))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()

    # Title
    draw.text((0, 0), "AUDIO MONITOR", fill=255, font=font)

    # Channel levels
    y = 12
    for i, level in enumerate(channel_levels):
        # Channel label and value
        draw.text((0, y), f"Ch{i+1}:", fill=255, font=font)
        draw.text((25, y), f"{level:4.0f}", fill=255, font=font)

        # Level bar (0-60 pixels wide)
        bar_width = min(60, int(level / 20))  # Scale: level/20 = pixels
        if bar_width > 0:
            draw.rectangle([60, y+1, 60+bar_width, y+7], fill=255)
        # Bar outline
        draw.rectangle([60, y+1, 120, y+7], outline=255)
        y += 10

    # Max level
    draw.text((0, y), f"MAX: {max_level:4.0f}", fill=255, font=font)
    y += 10

    # Current threshold
    draw.text((0, y), f"Threshold: {current_threshold}", fill=255, font=font)
    y += 10

    # Suggested threshold
    if suggested_threshold > 0:
        draw.text((0, y), f"Suggested: {suggested_threshold}", fill=255, font=font)
        y += 10

    # Recording status
    status = "RECORDING" if max_level >= current_threshold else "SILENT"
    draw.text((0, y), status, fill=255, font=font)

    device.display(img)

def print_levels(levels, max_level, current_threshold=900):
    """Print audio levels in a visual format"""
    # Clear line and move cursor to beginning
    print('\r', end='')

    # Show individual channel levels
    channel_bars = []
    for i, level in enumerate(levels):
        # Create a simple bar graph (0-50 characters)
        bar_length = min(50, int(level / 50))
        bar = '█' * bar_length + '░' * (50 - bar_length)
        channel_bars.append(f"Ch{i+1}: {level:4.0f} |{bar[:20]}|")

    # Show max level and threshold comparison
    max_bar_length = min(50, int(max_level / 50))
    max_bar = '█' * max_bar_length + '░' * (50 - max_bar_length)

    # Threshold indicator
    threshold_status = "🔴 RECORDING" if max_level >= current_threshold else "⚪ SILENT"

    output = (f"MAX: {max_level:4.0f} |{max_bar[:30]}| "
              f"Threshold: {current_threshold} {threshold_status}")

    print(output, end='', flush=True)

def main():
    print("Audio Level Monitor for Pi2-Rec Threshold Calibration")
    print("=" * 60)
    print(f"Monitoring {CHANNELS} channels at {SAMPLE_RATE}Hz")
    print(f"Current threshold in recorder.py: 900")
    print("\nShows levels on OLED display AND terminal")
    print("Press Ctrl+C to stop\n")

    # Initialize OLED display
    device = init_display()
    if device:
        print("OLED display initialized - levels will show on screen")
    else:
        print("OLED display not available - terminal output only")

    try:
        with sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            device=DEVICE,
            blocksize=BLOCK_SIZE,
            latency=0.1,
        ) as stream:

            max_seen = 0
            samples_count = 0

            while True:
                try:
                    data_raw, overflowed = stream.read(BLOCK_SIZE)
                    if overflowed:
                        print("\nAudio overflow detected!")

                    data = bytes(data_raw)

                    # Calculate RMS for each channel (same as recorder.py)
                    channel_levels = []
                    for ch in range(CHANNELS):
                        ch_bytes = data[ch * 2 :: CHANNELS * 2]
                        ch_level = audioop.rms(ch_bytes, 2)
                        channel_levels.append(ch_level)

                    max_level = max(channel_levels)
                    max_seen = max(max_seen, max_level)
                    samples_count += 1

                    # Calculate suggested threshold
                    suggested_threshold = int(max_seen * 0.3) if max_seen > 0 else 0

                    # Update OLED display
                    update_oled_display(device, channel_levels, max_level, suggested_threshold)

                    # Only show terminal statistics every 50 samples (~5 seconds)
                    if samples_count % 50 == 0:
                        print(f"Statistics after {samples_count * BLOCK_DURATION:.1f}s:")
                        print(f"  Current MAX: {max_level:4.0f}")
                        print(f"  Peak level seen: {max_seen}")
                        print(f"  Current threshold: 900")
                        if max_seen > 0:
                            print(f"  Suggested threshold: {suggested_threshold}")
                        status = "RECORDING" if max_level >= 900 else "SILENT"
                        print(f"  Status: {status}")
                        print("-" * 40)

                except Exception as e:
                    print(f"\nError reading audio: {e}")
                    time.sleep(0.1)

    except KeyboardInterrupt:
        print(f"\n\nMonitoring stopped.")
        print(f"Peak level recorded: {max_seen}")
        if max_seen > 0:
            suggested_threshold = int(max_seen * 0.3)
            print(f"Suggested threshold for recorder.py: {suggested_threshold}")
            print(f"\nTo use this threshold, edit recorder.py and change:")
            print(f"  THRESHOLD = 900")
            print(f"to:")
            print(f"  THRESHOLD = {suggested_threshold}")

    except Exception as e:
        print(f"Error initializing audio: {e}")
        print("\nTroubleshooting tips:")
        print("1. Check that your audio device is connected")
        print("2. Verify DEVICE = 0 is correct (try listing devices with: python -m sounddevice)")
        print("3. Make sure no other application is using the microphone")

if __name__ == "__main__":
    main()