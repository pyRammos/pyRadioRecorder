# pyRadioRecorder

Internet radio stream recorder with resilient connection handling for scheduled recordings.

## Features

- **Dual recording modes**: Standard FFmpeg vs. Resilient recorder with active monitoring
- **Multiple destinations**: Local, OwnCloud/Nextcloud, SSH/SFTP, podcast hosting
- **Robust error handling**: Automatic reconnection with exponential backoff
- **Segment-based recording**: Records in segments and merges seamlessly
- **Pushover notifications**: Get notified when recordings complete
- **Configurable logging**: Debug, info, warning, error levels
- **Automatic metadata**: Adds show name and date to MP3 files
- **Cron-friendly**: Designed for scheduled, unattended operation

## Requirements

- Python 3.x
- FFmpeg libraries
- Dependencies: `pyocclient`, `paramiko`, `ffmpy3` (see requirements.python3)
 
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
- `--stall-timeout N`: Seconds without file growth before restart (default: 60)
- `--max-consecutive-failures N`: Maximum consecutive failures before giving up (default: 10)

### When to use Resilient Recorder?
- Streams that frequently drop or stall
- Poor network connections
- Critical recordings where maximum coverage is essential
- When FFmpeg's reconnect alone isn't sufficient

## Installation

1. Clone the repository
2. Create virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.python3
   ```
4. Configure settings:
   ```bash
   cp "settings cfg.example" settings.cfg
   # Edit settings.cfg with your stream URLs and destinations
   ```

## Usage Examples

```bash
# Standard recording
python pyRecorder.py "Morning Show" 1h30m --local

# Resilient recording (recommended)
python pyRecorder.py "Evening News" 2h --local --use-resilient-recorder

# Custom stall timeout and max failures
python pyRecorder.py "SportsFM Live" 3h --local --use-resilient-recorder --stall-timeout 30 --max-consecutive-failures 15

# Multiple destinations with notifications
python pyRecorder.py "Talk Show" 90m --owncloud --ssh --podcast --use-resilient-recorder --notify

# Debug mode
python pyRecorder.py "Test" 5m --local-flat --use-resilient-recorder --log-level DEBUG
```

## Command-Line Options

- `--local`: Save with folder structure
- `--local-flat`: Save without folder structure
- `--owncloud`: Upload to OwnCloud/Nextcloud
- `--ssh`: Upload via SSH/SFTP
- `--podcast`: Upload for podcast generation
- `--notify`: Send Pushover notification on completion
- `--use-resilient-recorder`: Enable resilient recording mode
- `--stall-timeout N`: Stall detection timeout in seconds (default: 60)
- `--max-consecutive-failures N`: Max failures before giving up (default: 10)
- `--log-level LEVEL`: Set logging level (DEBUG, INFO, WARNING, ERROR)
- `--ffmpeg-log-level LEVEL`: Set FFmpeg logging level

## Cron Scheduling

For scheduled recordings, add to crontab:
```bash
# Record daily show at 10:00 AM for 2 hours
0 10 * * * cd /path/to/pyRadioRecorder && source venv/bin/activate && python pyRecorder.py "Morning Show" 2h --local --use-resilient-recorder --notify >> /tmp/recorder.log 2>&1
```

## License

See LICENSE file for details.
