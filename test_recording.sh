#!/bin/bash
# Test script to compare standard vs resilient recording

# Activate virtual environment if available
if [ -d "venv" ]; then
    source venv/bin/activate
    echo "Using virtual environment"
else
    echo "Warning: Virtual environment not found. Install with: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.python3"
fi

echo "==================================================================="
echo "Radio Recorder Testing Script"
echo "==================================================================="
echo ""
echo "This script demonstrates both recording methods."
echo "Replace the test stream URL with a real stream for actual testing."
echo ""

# Example test stream (replace with actual stream)
TEST_STREAM="https://example.com/stream.mp3"
TEST_DURATION="30s"  # Short test duration

echo "Test configuration:"
echo "  Stream: $TEST_STREAM"
echo "  Duration: $TEST_DURATION"
echo ""

# Test 1: Standard recording
echo "--- Test 1: Standard FFmpeg Recording ---"
python pyRecorder.py "TestShow_Standard" "$TEST_DURATION" --local-flat --log-level INFO
echo ""

# Test 2: Resilient recording
echo "--- Test 2: Resilient Recorder ---"
python pyRecorder.py "TestShow_Resilient" "$TEST_DURATION" --local-flat --use-resilient-recorder --log-level INFO
echo ""

echo "==================================================================="
echo "Testing complete!"
echo ""
echo "Compare the two recordings:"
ls -lh TestShow_*.mp3 2>/dev/null || echo "No test recordings found (check if stream URL is valid)"
echo ""
echo "For unreliable streams, use: --use-resilient-recorder"
echo "==================================================================="
