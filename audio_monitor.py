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

def get_gain_recommendation(peak_level):
    """Analyze peak level and provide gain recommendations"""
    if peak_level < 500:
        return "GAIN: TOO LOW"
    elif peak_level < 1500:
        return "GAIN: LOW"
    elif peak_level < 8000:
        return "GAIN: GOOD"
    elif peak_level < 20000:
        return "GAIN: HIGH"
    else:
        return "GAIN: TOO HIGH"

def get_signal_quality(peak_level, min_level):
    """Assess signal quality based on dynamic range"""
    if peak_level == 0:
        return "NO SIGNAL"

    dynamic_range = peak_level / max(min_level, 1)  # Avoid division by zero

    if dynamic_range < 2:
        return "POOR SNR"
    elif dynamic_range < 5:
        return "OK SNR"
    elif dynamic_range < 10:
        return "GOOD SNR"
    else:
        return "EXCELLENT SNR"

def get_level_indicator(level):
    """Get simple gain indicator for individual channel levels"""
    if level < 1500:
        return "L"  # Low
    elif level < 8000:
        return "G"  # Good
    else:
        return "H"  # High

def update_oled_display(device, channel_levels, max_level, peak_level, min_level, current_threshold=10000):
    """Update OLED display with current audio levels and gain analysis"""
    if device is None:
        return

    img = Image.new("1", (device.width, device.height))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()

    # Title
    draw.text((0, 0), "AUDIO MONITOR", fill=255, font=font)

    # All 4 channel levels with L/G/H indicators
    y = 12
    for i, level in enumerate(channel_levels):
        indicator = get_level_indicator(level)
        draw.text((0, y), f"Ch{i+1}:{level:4.0f} {indicator}", fill=255, font=font)
        # Compact level bar
        bar_width = min(35, int(level / 30))
        if bar_width > 0:
            draw.rectangle([85, y+1, 85+bar_width, y+6], fill=255)
        draw.rectangle([85, y+1, 120, y+6], outline=255)
        y += 10

    # Current, Max, Min levels
    draw.text((0, y), f"CUR: {max_level:4.0f}", fill=255, font=font)
    y += 8
    draw.text((0, y), f"MAX: {peak_level:4.0f}", fill=255, font=font)

    device.display(img)

# Removed print_levels function - no more terminal updates

def main():
    print("Audio Level Monitor for Pi2-Rec Threshold Calibration")
    print("=" * 60)
    print(f"Monitoring {CHANNELS} channels at {SAMPLE_RATE}Hz")
    print(f"Current threshold in recorder.py: 900")
    print("\nLevels shown on OLED display only")
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
            min_seen = float('inf')
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
                    min_seen = min(min_seen, max_level)
                    samples_count += 1

                    # Update OLED display (silent - no terminal output)
                    update_oled_display(device, channel_levels, max_level, max_seen, min_seen)

                except Exception as e:
                    print(f"\nError reading audio: {e}")
                    time.sleep(0.1)

    except KeyboardInterrupt:
        print(f"\n\nMonitoring stopped.")
        print(f"Maximum level recorded: {max_seen}")
        print(f"Minimum level recorded: {min_seen if min_seen != float('inf') else 0}")

        # Gain analysis
        gain_rec = get_gain_recommendation(max_seen)
        quality = get_signal_quality(max_seen, min_seen if min_seen != float('inf') else 0)

        print(f"\n=== GAIN ANALYSIS ===")
        print(f"Gain status: {gain_rec}")
        print(f"Signal quality: {quality}")

        if max_seen < 500:
            print(f"\n🔴 INCREASE GAIN on your audio interface!")
            print(f"   Your levels are too low for good recording quality.")
        elif max_seen < 1500:
            print(f"\n🟡 Consider increasing gain slightly")
            print(f"   You have headroom to increase input levels.")
        elif max_seen > 20000:
            print(f"\n🔴 DECREASE GAIN - risk of clipping!")
            print(f"   Your levels are too high and may distort.")
        else:
            print(f"\n✅ Gain levels look good!")

        print(f"\n=== THRESHOLD RECOMMENDATION ===")
        print(f"Choose threshold between {min_seen if min_seen != float('inf') else 0} and {max_seen}")
        print(f"Current recorder.py threshold: 900")
        print(f"\nTo change threshold, edit recorder.py and update:")
        print(f"  THRESHOLD = 900")
        print(f"to your preferred value")

    except Exception as e:
        print(f"Error initializing audio: {e}")
        print("\nTroubleshooting tips:")
        print("1. Check that your audio device is connected")
        print("2. Verify DEVICE = 0 is correct (try listing devices with: python -m sounddevice)")
        print("3. Make sure no other application is using the microphone")

if __name__ == "__main__":
    main()