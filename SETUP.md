# Quick Setup Guide

## Initial Setup

1. **Create virtual environment:**
   ```bash
   python3 -m venv venv
   ```

2. **Activate virtual environment:**
   ```bash
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.python3
   ```

4. **Copy and configure settings:**
   ```bash
   cp "settings cfg.example" settings.cfg
   # Edit settings.cfg with your stream URL and destination settings
   ```

## Usage

### Standard Recording (uses FFmpeg reconnect)
```bash
source venv/bin/activate
python pyRecorder.py "Show Name" 1h30m --local
```

### Resilient Recording (recommended for unreliable streams)
```bash
source venv/bin/activate
python pyRecorder.py "Show Name" 1h30m --local --use-resilient-recorder
```

### For Cron Jobs

Add to your crontab:
```bash
# Record daily show at 10:00 AM for 2 hours using resilient recorder
0 10 * * * cd /path/to/pyRadioRecorder && source venv/bin/activate && python pyRecorder.py "Morning Show" 2h --local --use-resilient-recorder >> /tmp/recorder.log 2>&1
```

## Key Options

- `--use-resilient-recorder`: Enable automatic restart on stalls/disconnects
- `--stall-timeout N`: Seconds without file growth before restart (default: 30)
- `--local`: Save with folder structure
- `--local-flat`: Save without folder structure  
- `--owncloud`: Upload to OwnCloud/Nextcloud
- `--ssh`: Upload via SSH/SFTP
- `--podcast`: Upload for podcast generation
- `--notify`: Send Pushover notification when complete
- `--log-level DEBUG`: Enable detailed logging

## Troubleshooting

### Stream keeps disconnecting
Use the resilient recorder with a shorter stall timeout:
```bash
python pyRecorder.py "Show" 2h --local --use-resilient-recorder --stall-timeout 30
```

Note: Default stall timeout is 60 seconds. Decrease for faster detection of stalls, increase for streams that occasionally pause.

### Check if recording is working
Enable debug logging:
```bash
python pyRecorder.py "Test" 30s --local-flat --use-resilient-recorder --log-level DEBUG
```

### Test the resilient recorder directly
```bash
python resilient_recorder.py "https://stream-url.com/stream.mp3" 60 test_output.mp3 --verbose
```

## What the Resilient Recorder Does

1. **Monitors file growth** every 5 seconds
2. **Detects stalls** when file stops growing for 60 seconds (configurable with `--stall-timeout`)
3. **Automatically restarts** FFmpeg when it detects a stall or disconnect
4. **Records in segments** and merges them at the end (no arbitrary segment limit)
5. **Retries with exponential backoff** (1s, 2s, 4s, 8s, up to 30s)
6. **Resets consecutive failure count** after each successful segment
7. **Preserves partial recordings** if merge fails (segments saved in `.segments_*` directory)
8. **Continues until target duration** is reached or max attempts exceeded (default: 100)

### Parameters:
- **min_segment_size**: 1KB (1000 bytes) - filters out tiny failed segments
- **stall_timeout**: 60 seconds default - how long to wait without file growth
- **check_interval**: 5 seconds - how often to check file growth
- **max_restart_attempts**: 100 - maximum restart attempts before giving up
- **segment_max_duration**: None (unlimited) - let segments run as long as needed

This approach is much more reliable than FFmpeg's built-in reconnect for streams that frequently drop or stall.
