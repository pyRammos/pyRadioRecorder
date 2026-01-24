# pyRadioRecorder
# Internet radio recorder





































echo "==================================================================="echo "For unreliable streams, use: --use-resilient-recorder"echo ""ls -lh TestShow_*.mp3 2>/dev/null || echo "No test recordings found (check if stream URL is valid)"echo "Compare the two recordings:"echo ""echo "Testing complete!"echo "==================================================================="echo ""python pyRecorder.py "TestShow_Resilient" "$TEST_DURATION" --local-flat --use-resilient-recorder --log-level INFOecho "--- Test 2: Resilient Recorder ---"# Test 2: Resilient recordingecho ""python pyRecorder.py "TestShow_Standard" "$TEST_DURATION" --local-flat --log-level INFOecho "--- Test 1: Standard FFmpeg Recording ---"# Test 1: Standard recordingecho ""echo "  Duration: $TEST_DURATION"echo "  Stream: $TEST_STREAM"echo "Test configuration:"TEST_DURATION="30s"  # Short test durationTEST_STREAM="https://example.com/stream.mp3"# Example test stream (replace with actual stream)echo ""echo "Replace the test stream URL with a real stream for actual testing."echo "This script demonstrates both recording methods."echo ""echo "==================================================================="echo "Radio Recorder Testing Script"echo "==================================================================="
## Requires
 - ffmpeg libraries
 
## Recording Methods

This recorder offers two recording approaches:

### 1. Standard FFmpeg Recording (default)
Uses FFmpeg's built-in reconnect mechanism. Simple and straightforward.

### 2. Resilient Recorder (recommended for unreliable streams)
A robust recording solution that handles network interruptions gracefully:
- **Active monitoring**: Checks file growth every 5 seconds to detect stalls
- **Automatic restart**: Restarts FFmpeg when connection drops or stalls
- **Segment-based recording**: Records in segments and merges at the end
- **Intelligent retry**: Exponential backoff with up to 100 restart attempts
- **Maximum coverage**: Ensures you capture as much as possible even with poor connections

To use the resilient recorder:
```bash
python pyRecorder.py "Show Name" 1h30m --local --use-resilient-recorder
```

Optional resilient recorder parameters:
- `--stall-timeout N`: Seconds without file growth before restart (default: 30)

### When to use Resilient Recorder?
- Streams that frequently drop or stall
- Poor network connections
- Critical recordings where maximum coverage is essential
- When FFmpeg's reconnect alone isn't sufficient

## Usage Examples

```bash
# Standard recording
python pyRecorder.py "Morning Show" 1h30m --local

# Resilient recording with custom stall timeout
python pyRecorder.py "Evening News" 2h --local --use-resilient-recorder --stall-timeout 45

# Multiple destinations with resilient recorder
python pyRecorder.py "SportsFM Live" 3h --owncloud --ssh --podcast --use-resilient-recorder
```
 
 ## Todo

  - Add flag for debug output to console

This is the next version of the sport-fm recorder. Removed dependencies to VLC and converted all to FFMPEG.
