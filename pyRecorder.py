import sys
import datetime
from time import sleep
import owncloud
import paramiko
import os
import http.client, urllib
import urllib.request
import configparser
import shutil
import ffmpy3
import ssl
import logging
import argparse
import re
import subprocess
import shlex
from functools import wraps

# Optional: resilient recorder for improved reconnect handling
try:
    from resilient_recorder import record_stream_resilient
    RESILIENT_RECORDER_AVAILABLE = True
except ImportError:
    RESILIENT_RECORDER_AVAILABLE = False

class RecordingConfig:
    """Handles configuration loading and validation"""
    
    def __init__(self, config_file='settings.cfg'):
        self.config_file = config_file
        self.config = None
        self._load_config()
    
    def _load_config(self):
        """Load configuration file once"""
        self.config = configparser.ConfigParser()
        try:
            files_read = self.config.read(self.config_file)
            if not files_read:
                raise FileNotFoundError(f"{self.config_file} not found or not readable")
        except Exception as e:
            raise Exception(f"Cannot read {self.config_file}: {e}")
    
    def get_section_config(self, section_name):
        """Get all configuration for a section (case-insensitive)"""
        actual_section = self._find_section(section_name)
        if not actual_section:
            available = list(self.config.sections())
            raise ValueError(f"Section '{section_name}' not found. Available: {available}")
        
        return dict(self.config[actual_section])
    
    def _find_section(self, section_name):
        """Find section case-insensitively"""
        for config_section in self.config.sections():
            if config_section.upper() == section_name.upper():
                return config_section
        return None
    
    def validate_recording_config(self, section_name, destinations):
        """Validate configuration for a recording session"""
        config = self.get_section_config(section_name)
        errors = []
        
        # Check required stream URL
        if 'stream' not in config or not config['stream']:
            errors.append("Missing 'stream' parameter")
        
        # Validate destination-specific requirements
        if destinations.get('owncloud'):
            required = ['ocuser', 'ocpass', 'ocurl', 'ocbasedir']
            missing = [key for key in required if not config.get(key)]
            if missing:
                errors.append(f"OwnCloud config missing: {missing}")
        
        if destinations.get('podcast'):
            required = ['sshuser', 'sshserver', 'sshpath', 'podcastrefreshurl']
            missing = [key for key in required if not config.get(key)]
            if missing:
                errors.append(f"Podcast config missing: {missing}")
            if not config.get('sshpassword') and not config.get('sshkeyfile'):
                errors.append("Podcast config missing: need either sshpassword or sshkeyfile")
        
        if destinations.get('local') and not config.get('saveto'):
            errors.append("Local storage missing: 'saveto' parameter")
        
        if destinations.get('local_flat') and not config.get('savetoflat'):
            errors.append("Local flat storage missing: 'savetoflat' parameter")
        
        if destinations.get('notify'):
            required = ['pushovertoken', 'pushoverkey']
            missing = [key for key in required if not config.get(key)]
            if missing:
                errors.append(f"Notification config missing: {missing}")
        
        if errors:
            raise ValueError("Configuration validation failed:\n" + "\n".join(f"  - {error}" for error in errors))
        
        return config

def handle_errors(operation_name):
    """Decorator for consistent error handling and logging"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Try to find logger in kwargs first, then in args (usually 3rd arg for these functions)
            logger = kwargs.get('logger')
            if not logger and len(args) >= 3:
                logger = args[2]  # logger is typically 3rd argument
            
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if logger and hasattr(logger, 'error'):
                    logger.error("Failed to %s", operation_name, exc_info=True)
                else:
                    # Fallback to stderr if no logger available
                    import sys
                    print(f"Error: Failed to {operation_name}: {e}", file=sys.stderr)
                return False
        return wrapper
    return decorator

def get_audio_duration(filename, logger=None):
    """Get actual audio duration using ffprobe"""
    try:
        # Use ffprobe to get duration in seconds
        cmd = [
            'ffprobe', 
            '-v', 'quiet',
            '-show_entries', 'format=duration',
            '-of', 'csv=p=0',
            filename
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0 and result.stdout.strip():
            duration_seconds = float(result.stdout.strip())
            
            # Convert to human readable format
            hours = int(duration_seconds // 3600)
            minutes = int((duration_seconds % 3600) // 60)
            seconds = int(duration_seconds % 60)
            
            if hours > 0:
                duration_str = f"{hours}h {minutes}m {seconds}s"
            elif minutes > 0:
                duration_str = f"{minutes}m {seconds}s"
            else:
                duration_str = f"{seconds}s"
                
            return duration_seconds, duration_str
        else:
            if logger:
                logger.warning("ffprobe failed to get duration: %s", result.stderr)
            return None, "unknown"
            
    except subprocess.TimeoutExpired:
        if logger:
            logger.warning("ffprobe timed out getting duration")
        return None, "unknown"
    except Exception as e:
        if logger:
            logger.warning("Error getting audio duration: %s", str(e))
        return None, "unknown"

def parse_duration(duration_str):
    """Parse duration string like '1h30m', '90m', '3600s', or just '3600'"""
    duration_str = duration_str.lower().strip()
    
    # If it's just a number, assume seconds
    if duration_str.isdigit():
        return int(duration_str)
    
    # Parse formats like 1h30m, 90m, 3600s
    pattern = r'(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?'
    match = re.match(pattern, duration_str)
    
    if not match:
        raise argparse.ArgumentTypeError(f"Invalid duration format: {duration_str}")
    
    hours, minutes, seconds = match.groups()
    total_seconds = 0
    
    if hours:
        total_seconds += int(hours) * 3600
    if minutes:
        total_seconds += int(minutes) * 60
    if seconds:
        total_seconds += int(seconds)
    
    if total_seconds <= 0:
        raise argparse.ArgumentTypeError("Duration must be greater than 0")
    
    return total_seconds

def parse_arguments():
    parser = argparse.ArgumentParser(
        description='Record internet radio streams and distribute to various destinations',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  %(prog)s MyShow 1h30m --owncloud --local
  %(prog)s "Morning News" 45m --ssh --podcast --notify
  %(prog)s SportFM 2h --local-flat --log-level DEBUG
  %(prog)s RadioShow 3600 --all-destinations
  %(prog)s "Live Show" 1h --local --show-progress
  %(prog)s "Quiet Show" 30m --local --ffmpeg-log-level error
        '''
    )
    
    # Required arguments
    parser.add_argument('name', 
                       help='Name of the show/stream to record')
    
    parser.add_argument('duration', 
                       type=parse_duration,
                       help='Recording duration (e.g., "1h30m", "90m", "3600s", or "3600")')
    
    # Destination options
    dest_group = parser.add_argument_group('Destination Options')
    dest_group.add_argument('--owncloud', '--to-owncloud',
                           action='store_true',
                           help='Upload to OwnCloud/Nextcloud')
    
    dest_group.add_argument('--podcast', '--to-podcast',
                           action='store_true', 
                           help='Upload for podcast generation')
    
    dest_group.add_argument('--local', '--to-local',
                           action='store_true',
                           help='Save locally with folder structure')
    
    dest_group.add_argument('--local-flat', '--to-local-flat',
                           action='store_true',
                           help='Save locally without folder structure')
    
    dest_group.add_argument('--ssh', '--to-ssh',
                           action='store_true',
                           help='Upload via SSH/SFTP')
    
    dest_group.add_argument('--all-destinations',
                           action='store_true',
                           help='Enable all configured destinations')
    
    # Additional options
    parser.add_argument('--notify',
                       action='store_true',
                       help='Send notification when complete')
    
    parser.add_argument('--config', '-c',
                       default='settings.cfg',
                       help='Configuration file path (default: settings.cfg)')
    
    parser.add_argument('--log-level',
                       choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       default='INFO',
                       help='Set logging level (default: INFO)')
    
    parser.add_argument('--quiet', '-q',
                       action='store_true',
                       help='Suppress console output (log to file only)')
    
    parser.add_argument('--dry-run',
                       action='store_true',
                       help='Show what would be done without actually recording')
    
    parser.add_argument('--ffmpeg-log-level',
                       choices=['quiet', 'error', 'warning', 'info', 'verbose', 'debug'],
                       help='Set FFmpeg log level (default: auto-detected from --log-level)')
    
    parser.add_argument('--show-progress',
                       action='store_true',
                       help='Show recording progress (overrides quiet FFmpeg logging)')
    
    parser.add_argument('--enable-reconnect',
                       action='store_true',
                       default=True,
                       help='Enable FFmpeg reconnect on network errors (default: enabled)')
    
    parser.add_argument('--use-resilient-recorder',
                       action='store_true',
                       help='Use resilient recorder with automatic restart and stall detection')
    
    parser.add_argument('--stall-timeout',
                       type=int,
                       default=60,
                       help='Seconds without file growth before restart (resilient recorder only, default: 60)')
    
    parser.add_argument('--max-consecutive-failures',
                       type=int,
                       default=10,
                       help='Give up after this many consecutive failures (resilient recorder only, default: 10)')
    
    parser.add_argument('--disable-reconnect',
                       action='store_true',
                       help='Disable FFmpeg reconnect (for testing network failures)')
    
    parser.add_argument('--output-file',
                       help='Override output filename')
    
    args = parser.parse_args()
    
    # Validation
    destinations = [args.owncloud, args.podcast, args.local, args.local_flat, args.ssh]
    if args.all_destinations:
        args.owncloud = args.podcast = args.local = args.local_flat = args.ssh = True
    elif not any(destinations):
        parser.error("At least one destination must be specified")
    
    if args.podcast and not (args.local or args.ssh):
        parser.error("Podcast option requires either --local or --ssh")
    
    # Handle reconnect options
    if args.disable_reconnect:
        args.enable_reconnect = False
    
    return args

def get_ffmpeg_log_level(args, logger):
    """Determine appropriate FFmpeg log level based on user preferences"""
    if args.ffmpeg_log_level:
        return args.ffmpeg_log_level
    
    # Auto-detect based on our log level
    if args.log_level == 'DEBUG':
        return 'info'  # Show FFmpeg info but not too verbose
    elif args.log_level == 'INFO':
        return 'warning'  # Show warnings and errors
    elif args.log_level == 'WARNING':
        return 'error'  # Show only errors
    else:  # ERROR
        return 'quiet'  # Silent
    
def build_ffmpeg_command(stream, filename, duration, metadata, ffmpeg_log_level, show_progress=False, enable_reconnect=True):
    """Build FFmpeg command with appropriate logging and reconnect options"""
    
    cmd_parts = ['ffmpeg']
    
    # Add reconnect options if enabled (must come before -i)
    if enable_reconnect:
        cmd_parts.extend([
            '-reconnect', '1',                    # Enable reconnect
            '-reconnect_streamed', '1',           # Reconnect for live streams  
            '-reconnect_at_eof', '1',             # Treat EOF as error for live streams
            '-reconnect_on_network_error', '1',   # Reconnect on network errors
            '-reconnect_on_http_error', '1',       # Reconnect on any HTTP error
            '-reconnect_delay_max', '120',        # Max 120 seconds between retries (default)
            '-reconnect_max_retries', '10',       # Max 10 retry attempts
            '-reconnect_delay_total_max', '600'   # Give up after 10 minutes total
        ])
    
    # Add input
    cmd_parts.extend(['-i', stream])
    
    # Add output options
    cmd_parts.extend([
        '-y',  # Overwrite output file
        '-acodec', 'copy',  # Copy audio codec (no re-encoding)
        '-t', str(duration),  # Duration
    ])
    
    # Add metadata
    for key, value in metadata.items():
        cmd_parts.extend(['-metadata', f'{key}={value}'])
    
    # Add logging options
    if show_progress:
        # Show progress but limit other output
        cmd_parts.extend(['-loglevel', 'warning', '-stats'])
    else:
        # Use specified log level, no stats
        cmd_parts.extend(['-loglevel', ffmpeg_log_level, '-nostats'])
    
    # Add output filename
    cmd_parts.append(filename)
    
    # Create a simple object that has the cmd attribute and run method
    class FFmpegCommand:
        def __init__(self, cmd_list):
            self.cmd = ' '.join(cmd_list)
            self.cmd_list = cmd_list
        
        def run(self, timeout=None):
            import subprocess
            return subprocess.run(self.cmd_list, check=True, timeout=timeout)
    
    return FFmpegCommand(cmd_parts)

def setup_logging(log_level=logging.INFO, console_output=True):
    """
    Setup logging with configurable levels and output destinations.
    
    This configures the root logger, which means all module loggers
    (including resilient_recorder) will inherit this configuration.
    """
    # Clear any existing handlers from root logger
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    
    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Setup file handler - always logs everything at DEBUG level
    file_handler = logging.FileHandler('recorder.log')
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)
    
    # Setup console handler (optional) - respects user's log level
    if console_output:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(log_level)
        root_logger.addHandler(console_handler)
    
    # Set root logger level to DEBUG so all messages are processed
    # (handlers will filter based on their own levels)
    root_logger.setLevel(logging.DEBUG)
    
    # Return a logger for the main module
    return logging.getLogger(__name__)

def show_configuration(args, logger):
    """Display what the recorder would do (useful for dry-run)"""
    logger.info(f"Show: {args.name}")
    logger.info(f"Duration: {args.duration} seconds ({args.duration//3600}h {(args.duration%3600)//60}m)")
    logger.info(f"Config file: {args.config}")
    
    destinations = []
    if args.owncloud: destinations.append("OwnCloud")
    if args.podcast: destinations.append("Podcast")
    if args.local: destinations.append("Local (structured)")
    if args.local_flat: destinations.append("Local (flat)")
    if args.ssh: destinations.append("SSH")
    
    logger.info(f"Destinations: {', '.join(destinations)}")
    if args.notify: logger.info("Notifications: Enabled")
@handle_errors("upload to OwnCloud")
def upload_to_owncloud(filename, config, logger):
    """Upload file to OwnCloud/Nextcloud"""
    oc = owncloud.Client(config['ocurl'])
    oc.login(config['ocuser'], config['ocpass'])
    
    # Create directory structure
    now = datetime.datetime.now()
    streamName = filename.split('260')[0]  # Extract show name from filename
    targetdir = f"/{streamName}/{now.year}/{now.month} - {now.strftime('%b')}"
    oclocation = config['ocbasedir'] + targetdir + "/"
    
    dirs = oclocation.split("/")
    dirtocreate = ""
    for x in dirs:
        dirtocreate = dirtocreate + x + "/"
        try:
            oc.mkdir(dirtocreate)
        except:
            logger.debug("Cannot create OwnCloud dir %s, possibly exists", dirtocreate)
    
    oc.put_file(oclocation + filename, filename)
    logger.info("Successfully uploaded to OwnCloud: %s", oclocation + filename)
    return True

@handle_errors("upload via SSH")
def upload_via_ssh(filename, config, logger):
    """Upload file via SSH/SFTP"""
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    if config.get('sshkeyfile'):
        logger.info("Connecting via SSH using keyfile")
        ssh.connect(config['sshserver'], username=config['sshuser'], 
                   password=config.get('sshpassword'), key_filename=config['sshkeyfile'])
    else:
        logger.info("Connecting via SSH using password")
        ssh.connect(config['sshserver'], username=config['sshuser'], 
                   password=config['sshpassword'])
    
    sftp = ssh.open_sftp()
    remote_path = config['sshpath'] + filename
    logger.info("Uploading %s to %s", filename, remote_path)
    sftp.put(filename, remote_path)
    sftp.close()
    ssh.close()
    logger.info("Successfully uploaded via SSH")
    return True

@handle_errors("save to local storage")
def save_to_local(filename, config, logger, flat=False):
    """Save file to local storage with or without folder structure"""
    if flat:
        save_location = config['savetoflat']
        if save_location.endswith('/'):
            save_location = save_location[:-1]
        destination_path = f"{save_location}/{filename}"
        logger.info("Making local transfer to %s", destination_path)
        shutil.copyfile(filename, destination_path)
        logger.info("Successfully saved locally (flat)")
    else:
        save_location = config['saveto']
        if save_location.endswith('/'):
            save_location = save_location[:-1]
        
        # Create directory structure
        now = datetime.datetime.now()
        streamName = filename.split('260')[0]  # Extract show name from filename
        targetdir = f"/{streamName}/{now.year}/{now.month} - {now.strftime('%b')}"
        
        logger.debug("Will make directory: %s", save_location + targetdir)
        try:
            os.makedirs(save_location + targetdir)
        except Exception as e:
            logger.debug("Could not create local directory (possibly exists): %s", str(e))
        
        destination_path = f"{save_location}{targetdir}/{filename}"
        logger.info("Making local transfer to %s", destination_path)
        shutil.copyfile(filename, destination_path)
        logger.info("Successfully saved locally")
    return True

@handle_errors("refresh podcast generator")
def refresh_podcast(config, logger):
    """Refresh podcast generator"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    logger.info("Refreshing podcast generator at %s", config['podcastrefreshurl'])
    urllib.request.urlopen(config['podcastrefreshurl'], context=ctx).read()
    logger.info("Successfully refreshed podcast generator")
    return True

@handle_errors("send notification")
def send_notification(filename, config, logger):
    """Send Pushover notification with file analysis"""
    # Get file size and audio duration
    file_size_mb = os.stat(filename).st_size / 1000000
    duration_seconds, duration_str = get_audio_duration(filename, logger)
    
    # Build notification message
    message = f"Recording Completed. Audio file is {file_size_mb:.2f}MB"
    if duration_str != "unknown":
        message += f", duration: {duration_str}"
        if duration_seconds:
            bitrate_kbps = (os.stat(filename).st_size * 8) / (duration_seconds * 1000)
            message += f", avg bitrate: {bitrate_kbps:.0f}kbps"
    
    conn = http.client.HTTPSConnection("api.pushover.net:443")
    conn.request("POST", "/1/messages.json",
                urllib.parse.urlencode({
                    "token": config['pushovertoken'],
                    "user": config['pushoverkey'],
                    "message": message,
                }), {"Content-type": "application/x-www-form-urlencoded"})
    conn.getresponse()
    logger.info("Pushover notification sent successfully")
    return True

def record_audio_stream(stream_url, filename, duration, metadata, args, logger):
    """Record audio stream using FFmpeg"""
    ffmpeg_log_level = get_ffmpeg_log_level(args, logger)
    
    logger.info("Stream URL: %s", stream_url)
    logger.info("FFmpeg log level: %s", ffmpeg_log_level)
    logger.info("Network reconnect: %s", "enabled" if args.enable_reconnect else "disabled")
    
    if args.show_progress:
        logger.info("Progress display enabled")
    
    logger.info("Recording from %s for %d seconds", stream_url, duration)
    
    # Build FFmpeg command
    ff = build_ffmpeg_command(
        stream_url, filename, duration, metadata, 
        ffmpeg_log_level, args.show_progress, args.enable_reconnect
    )
    
    logger.debug("FFmpeg command: %s", ff.cmd)
    
    if args.show_progress:
        logger.info("Starting recording with progress display...")
    
    # Execute FFmpeg with appropriate logging
    if args.log_level == 'DEBUG' or args.ffmpeg_log_level in ['info', 'verbose', 'debug']:
        # Capture and log FFmpeg output for debugging
        try:
            result = subprocess.run(
                shlex.split(ff.cmd),
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=duration + 30
            )
            
            # Log FFmpeg output
            if result.stdout.strip():
                logger.debug("=== FFmpeg stdout ===")
                for line in result.stdout.strip().split('\n'):
                    if line.strip():
                        logger.debug("FFmpeg: %s", line.strip())
            
            if result.stderr.strip():
                logger.debug("=== FFmpeg stderr ===")
                for line in result.stderr.strip().split('\n'):
                    if line.strip():
                        if 'error' in line.lower() or 'failed' in line.lower():
                            logger.error("FFmpeg: %s", line.strip())
                        elif 'warning' in line.lower():
                            logger.warning("FFmpeg: %s", line.strip())
                        else:
                            logger.debug("FFmpeg: %s", line.strip())
            
            if result.returncode != 0:
                logger.error("FFmpeg exited with code %d", result.returncode)
                raise subprocess.CalledProcessError(result.returncode, ff.cmd)
                
        except subprocess.TimeoutExpired:
            logger.error("FFmpeg recording timed out after %d seconds", duration + 30)
            raise
        except subprocess.CalledProcessError as e:
            logger.error("FFmpeg failed with return code %d", e.returncode)
            raise
    else:
        # Use normal execution for real-time display with timeout
        try:
            ff.run(timeout=duration + 30)
        except subprocess.TimeoutExpired:
            logger.error("FFmpeg recording timed out after %d seconds", duration + 30)
            raise
        except subprocess.CalledProcessError as e:
            logger.error("FFmpeg failed with return code %d", e.returncode)
            raise
    
    logger.info("Recording completed successfully")
    
    # Analyze the recorded file
    duration_seconds, duration_str = get_audio_duration(filename, logger)
    file_size_mb = os.stat(filename).st_size / 1000000
    
    logger.info("Recorded file analysis:")
    logger.info("  File size: %.2f MB", file_size_mb)
    logger.info("  Audio duration: %s", duration_str)
    
    if duration_seconds:
        bitrate_kbps = (os.stat(filename).st_size * 8) / (duration_seconds * 1000)
        logger.info("  Average bitrate: %.0f kbps", bitrate_kbps)
        
        # Check if duration matches expected
        expected_duration = duration
        duration_diff = abs(duration_seconds - expected_duration)
        if duration_diff > 5:
            logger.warning("Duration mismatch: expected %ds, got %.1fs (diff: %.1fs)", 
                         expected_duration, duration_seconds, duration_diff)

def process_destinations(filename, config, destinations, logger):
    """Process all enabled destinations"""
    errors = []
    
    if destinations.get('owncloud'):
        logger.info("Uploading to OwnCloud")
        if not upload_to_owncloud(filename, config, logger):
            errors.append("OwnCloud upload failed")
    
    if destinations.get('ssh'):
        logger.info("Uploading file via SSH")
        if not upload_via_ssh(filename, config, logger):
            errors.append("SSH upload failed")
    
    if destinations.get('local'):
        logger.info("Saving to local location")
        if not save_to_local(filename, config, logger, flat=False):
            errors.append("Local save failed")
    
    if destinations.get('local_flat'):
        logger.info("Saving to local location (without folder structure)")
        if not save_to_local(filename, config, logger, flat=True):
            errors.append("Local flat save failed")
    
    if destinations.get('podcast'):
        logger.info("Refreshing podcast generator")
        if not refresh_podcast(config, logger):
            errors.append("Podcast refresh failed")
    
    if destinations.get('notify'):
        if not send_notification(filename, config, logger):
            errors.append("Notification failed")
    
    return errors

def main():
    # Parse command line arguments
    args = parse_arguments()
    
    # Setup logging
    logger = setup_logging(
        getattr(logging, args.log_level),
        console_output=not args.quiet
    )
    
    logger.info("============ New Start ============")
    logger.info("Recording '%s' for %d seconds", args.name, args.duration)
    
    if args.dry_run:
        logger.info("DRY RUN MODE - No actual recording will occur")
        show_configuration(args, logger)
        return 0
    
    # Prepare destinations dictionary
    destinations = {
        'owncloud': args.owncloud,
        'podcast': args.podcast,
        'local': args.local,
        'ssh': args.ssh,
        'local_flat': args.local_flat,
        'notify': args.notify
    }
    
    # Log selected destinations
    for dest, enabled in destinations.items():
        if enabled:
            logger.info("Will %s", dest.replace('_', ' '))
    
    try:
        # Load and validate configuration early
        config_manager = RecordingConfig(args.config)
        config = config_manager.validate_recording_config(args.name, destinations)
        
        # Prepare recording metadata
        now = datetime.datetime.now()
        end = now + datetime.timedelta(seconds=args.duration)
        today = now.isoformat()
        today = str(today[:10]).replace("-", "")
        today = today[2:] + "-" + now.strftime('%a')
        streamName = args.name.replace(" ", "_")
        filename = streamName + today + ".mp3"
        
        logger.info("Starting at %s", str(now))
        logger.info("Will stop at %s", str(end))
        
        # Prepare metadata
        title = filename.replace(".mp3", "")
        metadata = {
            'title': title,
            'artist': streamName,
            'genre': 'radio',
            'album': streamName
        }
        
        # Record the audio stream using selected method
        if args.use_resilient_recorder:
            if not RESILIENT_RECORDER_AVAILABLE:
                logger.error("Resilient recorder requested but resilient_recorder.py not found")
                return 1
            
            logger.info("Using resilient recorder with stall timeout: %ds", args.stall_timeout)
            success = record_stream_resilient(
                stream_url=config['stream'],
                duration_seconds=args.duration,
                output_file=filename,
                stall_timeout=args.stall_timeout,
                max_restart_attempts=100,
                max_consecutive_failures=args.max_consecutive_failures
            )
            
            if not success:
                raise Exception("Resilient recorder failed to complete recording")
            
            # Add metadata to the recorded file (resilient recorder records without metadata)
            logger.info("Adding metadata to recorded file...")
            temp_file = filename.replace('.mp3', '_temp.mp3')  # Use .mp3 extension for temp file
            add_metadata_cmd = [
                'ffmpeg', '-i', filename,
                '-metadata', f'title={metadata["title"]}',
                '-metadata', f'artist={metadata["artist"]}',
                '-metadata', f'genre={metadata["genre"]}',
                '-metadata', f'album={metadata["album"]}',
                '-c', 'copy', '-y', temp_file
            ]
            result = subprocess.run(add_metadata_cmd, capture_output=True, text=True)
            if result.returncode == 0 and os.path.exists(temp_file):
                os.replace(temp_file, filename)
                logger.info("Metadata added successfully")
            else:
                logger.warning("Failed to add metadata, keeping file without metadata")
                if result.stderr:
                    logger.debug("FFmpeg metadata error: %s", result.stderr[:300])
                if os.path.exists(temp_file):
                    os.remove(temp_file)
        else:
            # Use standard FFmpeg recording
            record_audio_stream(config['stream'], filename, args.duration, metadata, args, logger)
        
        # Process all destinations
        errors = process_destinations(filename, config, destinations, logger)
        
        # Handle results
        if errors:
            logger.error("There have been non-terminal errors: %s", ", ".join(errors))
            logger.error("Will leave temporary file in place")
            return 1
        else:
            logger.info("Deleting local temporary file: %s", filename)
            os.remove(filename)
            return 0
            
    except ValueError as e:
        logger.error("Configuration error: %s", str(e))
        return 1
    except Exception as e:
        logger.error("Recording failed: %s", str(e), exc_info=True)
        
        # Check if we have a partial recording to save
        partial_file_saved = False
        try:
            # Check if filename exists in scope (it should if recording started)
            if 'filename' not in locals():
                logger.warning("Filename not available - exception occurred before recording started")
                return 1
            
            # Use the filename variable that was created before recording started
            # (it's already in scope from the try block above)
            if os.path.exists(filename) and os.path.getsize(filename) > 0:
                logger.info("Found partial recording (%d bytes), attempting to save to destinations", 
                           os.path.getsize(filename))
                
                # Try to get config for destinations
                try:
                    config_manager = RecordingConfig(args.config)
                    config = config_manager.get_section_config(args.name)
                    
                    # Process destinations for partial file
                    errors = process_destinations(filename, config, destinations, logger)
                    
                    if not errors:
                        logger.info("Successfully saved partial recording to all destinations")
                        partial_file_saved = True
                    else:
                        logger.warning("Some destinations failed for partial recording: %s", ", ".join(errors))
                        partial_file_saved = True  # At least some succeeded
                        
                except Exception as dest_error:
                    logger.error("Could not save partial recording to destinations: %s", str(dest_error))
                
                # Always try to send notification about partial recording
                if destinations.get('notify'):
                    try:
                        if 'config' in locals():
                            # Analyze the partial file
                            file_size_mb = os.path.getsize(filename) / 1000000
                            duration_seconds, duration_str = get_audio_duration(filename, logger)
                            
                            failure_message = f"Recording FAILED for {args.name} but saved partial recording: {file_size_mb:.2f}MB"
                            if duration_str != "unknown":
                                failure_message += f", duration: {duration_str}"
                            failure_message += f". Error: {str(e)}"
                            
                            conn = http.client.HTTPSConnection("api.pushover.net:443")
                            conn.request("POST", "/1/messages.json",
                                        urllib.parse.urlencode({
                                            "token": config['pushovertoken'],
                                            "user": config['pushoverkey'],
                                            "message": failure_message,
                                        }), {"Content-type": "application/x-www-form-urlencoded"})
                            conn.getresponse()
                            logger.info("Partial recording notification sent")
                    except Exception as notify_error:
                        logger.error("Could not send partial recording notification: %s", str(notify_error))
                
                # Clean up temp file only after saving to destinations
                if partial_file_saved:
                    logger.info("Deleting temporary file after saving partial recording: %s", filename)
                    os.remove(filename)
                else:
                    logger.warning("Leaving temporary file in place due to destination failures: %s", filename)
                    
            else:
                logger.info("No usable recording file found to save")
                
                # Send failure notification without partial recording info
                if destinations.get('notify'):
                    try:
                        config_manager = RecordingConfig(args.config)
                        config = config_manager.get_section_config(args.name)
                        if config.get('pushovertoken') and config.get('pushoverkey'):
                            failure_message = f"Recording FAILED for {args.name}: {str(e)}"
                            conn = http.client.HTTPSConnection("api.pushover.net:443")
                            conn.request("POST", "/1/messages.json",
                                        urllib.parse.urlencode({
                                            "token": config['pushovertoken'],
                                            "user": config['pushoverkey'],
                                            "message": failure_message,
                                        }), {"Content-type": "application/x-www-form-urlencoded"})
                            conn.getresponse()
                            logger.info("Failure notification sent")
                    except Exception as notify_error:
                        logger.error("Could not send failure notification: %s", str(notify_error))
                        
        except Exception as cleanup_error:
            logger.error("Error during partial recording cleanup: %s", str(cleanup_error))
        
        return 1

if __name__ == "__main__":
    exit(main())



