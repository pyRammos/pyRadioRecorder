#!/usr/bin/env python3
"""
Resilient Stream Recorder Module

A robust stream recording solution that handles network interruptions gracefully.
Records in segments, monitors progress actively, and automatically restarts on failures.

Usage:
    from resilient_recorder import record_stream_resilient
    
    success = record_stream_resilient(
        stream_url="https://example.com/stream.mp3",
        duration_seconds=3600,
        output_file="/path/to/recording.mp3"
    )
"""

import subprocess
import time
import os
import logging
from pathlib import Path
from datetime import datetime, timedelta

# Module logger - will inherit configuration from root logger set by main application
logger = logging.getLogger(__name__)


class ResilientStreamRecorder:
    """
    Robust stream recorder that handles network interruptions gracefully.
    Records in segments and monitors progress continuously.
    """
    
    def __init__(self, stream_url, duration_seconds, output_file, 
                 stall_timeout=60, max_restart_attempts=100,
                 check_interval=5, min_segment_size=1000,
                 segment_max_duration=None, max_consecutive_failures=10):
        """
        Initialize the resilient recorder.
        
        Args:
            stream_url: URL of the stream to record
            duration_seconds: Target recording duration in seconds
            output_file: Path where final recording will be saved
            stall_timeout: Seconds without file growth before declaring stall (default: 60)
            max_restart_attempts: Maximum restart attempts (default: 100)
            check_interval: Seconds between file growth checks (default: 5)
            min_segment_size: Minimum valid segment size in bytes (default: 1000 = ~1KB)
            segment_max_duration: Max duration per segment in seconds (default: None = no limit)
            max_consecutive_failures: Give up after this many consecutive failures (default: 10)
        """
        self.stream_url = stream_url
        self.duration_seconds = duration_seconds
        self.output_file = Path(output_file)
        self.stall_timeout = stall_timeout
        self.max_restart_attempts = max_restart_attempts
        self.check_interval = check_interval
        self.min_segment_size = min_segment_size
        self.segment_max_duration = segment_max_duration
        self.max_consecutive_failures = max_consecutive_failures
        
        # Create segments directory
        self.segment_dir = self.output_file.parent / f".segments_{self.output_file.stem}"
        self.segment_dir.mkdir(exist_ok=True)
        
        self.segments = []
        self.start_time = None
        self.end_time = None
        
    def record(self):
        """
        Main recording loop with automatic restart on failure.
        
        Returns:
            True if recording completed successfully, False otherwise
        """
        self.start_time = datetime.now()
        self.end_time = self.start_time + timedelta(seconds=self.duration_seconds)
        
        logger.info(f"Starting resilient recording: {self.output_file}")
        logger.info(f"Stream: {self.stream_url}")
        logger.info(f"Duration: {self.duration_seconds}s (until {self.end_time.strftime('%H:%M:%S')})")
        
        attempt = 0
        consecutive_failures = 0
        total_recorded_duration = 0
        
        while datetime.now() < self.end_time and attempt < self.max_restart_attempts:
            attempt += 1
            remaining_time = (self.end_time - datetime.now()).total_seconds()
            
            if remaining_time <= 0:
                logger.info("Target duration reached")
                break
            
            segment_file = self.segment_dir / f"segment_{attempt:03d}.mp3"
            
            logger.info(f"[Attempt {attempt}] Recording segment: {segment_file.name}, "
                       f"remaining: {remaining_time:.0f}s")
            
            # Calculate timeout for this segment (remaining time + buffer)
            if self.segment_max_duration:
                segment_timeout = min(remaining_time + 60, self.segment_max_duration)
            else:
                segment_timeout = remaining_time + 60
            
            segment_duration = self._record_segment(
                segment_file, 
                duration=segment_timeout,
                timeout=segment_timeout + 30
            )
            
            if segment_duration > 0 and segment_file.exists() and segment_file.stat().st_size > self.min_segment_size:
                # Valid segment recorded
                self.segments.append(segment_file)
                total_recorded_duration += segment_duration
                consecutive_failures = 0
                logger.info(f"✓ Segment {attempt} completed: {segment_file.stat().st_size / 1024:.1f} KB, "
                          f"{segment_duration:.1f}s")
            else:
                consecutive_failures += 1
                logger.warning(f"✗ Segment {attempt} failed or too small")
                
                # Exponential backoff after failures
                if consecutive_failures > 0:
                    backoff = min(2 ** (consecutive_failures - 1), 30)  # Max 30s backoff
                    logger.info(f"  Waiting {backoff}s before retry...")
                    time.sleep(backoff)
                
                # Give up if too many consecutive failures
                if consecutive_failures >= self.max_consecutive_failures:
                    logger.error(f"ERROR: {consecutive_failures} consecutive failures. "
                               "Stream may be permanently unavailable.")
                    break
        
        # Log final statistics
        coverage = (total_recorded_duration / self.duration_seconds * 100) if self.duration_seconds > 0 else 0
        logger.info(f"\nRecording complete: {len(self.segments)} segments, "
                   f"{total_recorded_duration:.0f}s recorded ({coverage:.1f}% coverage)")
        
        # Merge all segments
        if self.segments:
            return self._merge_segments()
        else:
            logger.error("ERROR: No valid segments recorded")
            return False
    
    def _record_segment(self, output_file, duration, timeout):
        """
        Record a single segment with active monitoring.
        
        Args:
            output_file: Path where segment will be saved
            duration: Target duration for this segment
            timeout: Maximum time to wait for this segment
            
        Returns:
            Actual duration recorded in seconds (0 if failed)
        """
        ffmpeg_cmd = [
            'ffmpeg',
            '-hide_banner',
            '-loglevel', 'warning',
            '-i', self.stream_url,
            '-t', str(int(duration)),
            '-c', 'copy',
            '-y',  # Overwrite
            str(output_file)
        ]
        
        try:
            process = subprocess.Popen(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # Monitor the recording process
            segment_start = time.time()
            success = self._monitor_recording(process, output_file, timeout)
            actual_duration = time.time() - segment_start
            
            return actual_duration if success else 0
            
        except Exception as e:
            logger.error(f"  Exception starting FFmpeg: {e}")
            return 0
    
    def _monitor_recording(self, process, output_file, timeout):
        """
        Monitor FFmpeg process and file growth to detect stalls.
        Kills process if it stalls or times out.
        
        Args:
            process: subprocess.Popen object running FFmpeg
            output_file: Path to output file being written
            timeout: Maximum seconds to wait
            
        Returns:
            True if segment was recorded successfully, False otherwise
        """
        start = time.time()
        last_size = 0
        last_growth_time = time.time()
        
        while True:
            # Check if process is still running
            poll = process.poll()
            if poll is not None:
                # Process ended
                elapsed = time.time() - start
                stderr = process.stderr.read() if process.stderr else ""
                
                if poll == 0 or (output_file.exists() and output_file.stat().st_size > self.min_segment_size):
                    # Clean exit or valid file created
                    return True
                else:
                    logger.warning(f"  FFmpeg exited with code {poll} after {elapsed:.1f}s")
                    if stderr:
                        logger.debug(f"  Error: {stderr[:200]}")
                    return False
            
            # Check for timeout
            if time.time() - start > timeout:
                logger.info(f"  Timeout reached ({timeout}s), terminating...")
                process.terminate()
                time.sleep(2)
                if process.poll() is None:
                    process.kill()
                return output_file.exists() and output_file.stat().st_size > self.min_segment_size
            
            # Check file growth (indicates recording is active)
            if output_file.exists():
                current_size = output_file.stat().st_size
                
                if current_size > last_size:
                    # File is growing - recording is active
                    last_size = current_size
                    last_growth_time = time.time()
                else:
                    # File not growing - check if stalled
                    stall_duration = time.time() - last_growth_time
                    
                    if stall_duration > self.stall_timeout and current_size > 0:
                        # Recording has stalled
                        logger.warning(f"  Recording stalled (no growth for {stall_duration:.0f}s), restarting...")
                        process.terminate()
                        time.sleep(1)
                        if process.poll() is None:
                            process.kill()
                        return current_size > self.min_segment_size
            
            time.sleep(self.check_interval)
    
    def _merge_segments(self):
        """
        Merge all recorded segments into final output file.
        
        Returns:
            True if merge succeeded, False otherwise
        """
        logger.info(f"\nMerging {len(self.segments)} segments...")
        
        if len(self.segments) == 1:
            # Only one segment, just move it
            self.segments[0].replace(self.output_file)
            logger.info(f"✓ Recording saved: {self.output_file}")
            self._cleanup_segments()
            return True
        
        # Create concat file for FFmpeg
        concat_file = self.segment_dir / "concat.txt"
        with open(concat_file, 'w') as f:
            for segment in self.segments:
                # Use absolute path and escape special characters
                f.write(f"file '{segment.absolute()}'\n")
        
        # Merge using FFmpeg concat
        merge_cmd = [
            'ffmpeg',
            '-f', 'concat',
            '-safe', '0',
            '-i', str(concat_file),
            '-c', 'copy',
            '-y',
            str(self.output_file)
        ]
        
        try:
            result = subprocess.run(
                merge_cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0 and self.output_file.exists():
                final_size = self.output_file.stat().st_size
                logger.info(f"✓ Merged recording saved: {self.output_file} ({final_size / 1024 / 1024:.1f} MB)")
                self._cleanup_segments()
                return True
            else:
                logger.error(f"✗ Merge failed: {result.stderr[:200]}")
                logger.info(f"Segments preserved in: {self.segment_dir}")
                return False
                
        except Exception as e:
            logger.error(f"✗ Merge exception: {e}")
            logger.info(f"Segments preserved in: {self.segment_dir}")
            return False
    
    def _cleanup_segments(self):
        """Remove segment directory after successful merge."""
        try:
            import shutil
            shutil.rmtree(self.segment_dir)
            logger.debug(f"Cleaned up segment directory: {self.segment_dir}")
        except Exception as e:
            logger.warning(f"Could not clean up segments: {e}")


def record_stream_resilient(stream_url, duration_seconds, output_file, 
                            stall_timeout=60, max_restart_attempts=100,
                            check_interval=5, min_segment_size=1000,
                            segment_max_duration=None, max_consecutive_failures=10):
    """
    Convenience function to record a stream with resilience.
    
    This function provides automatic restart, stall detection, and segment-based
    recording to ensure maximum capture from unreliable streams.
    
    Args:
        stream_url: URL of the stream to record
        duration_seconds: How long to record (in seconds)
        output_file: Path to save the recording
        stall_timeout: Seconds without file growth before restarting (default: 60)
        max_restart_attempts: Maximum number of restart attempts (default: 100)
        check_interval: Seconds between file growth checks (default: 5)
        min_segment_size: Minimum valid segment size in bytes (default: 1000 = ~1KB)
        segment_max_duration: Max duration per segment in seconds (default: None = no limit)
        max_consecutive_failures: Give up after this many consecutive failures (default: 10)
    
    Returns:
        True if recording completed successfully, False otherwise
    
    Example:
        >>> success = record_stream_resilient(
        ...     stream_url="https://example.com/stream.mp3",
        ...     duration_seconds=3600,
        ...     output_file="/tmp/recording.mp3"
        ... )
        >>> if success:
        ...     print("Recording completed!")
    """
    recorder = ResilientStreamRecorder(
        stream_url=stream_url,
        duration_seconds=duration_seconds,
        output_file=output_file,
        stall_timeout=stall_timeout,
        max_restart_attempts=max_restart_attempts,
        check_interval=check_interval,
        min_segment_size=min_segment_size,
        segment_max_duration=segment_max_duration,
        max_consecutive_failures=max_consecutive_failures
    )
    
    return recorder.record()


if __name__ == "__main__":
    # Example usage and testing
    import argparse
    
    parser = argparse.ArgumentParser(description='Record a stream with resilience')
    parser.add_argument('url', help='Stream URL')
    parser.add_argument('duration', type=int, help='Duration in seconds')
    parser.add_argument('output', help='Output file path')
    parser.add_argument('--stall-timeout', type=int, default=30,
                       help='Seconds without growth before restart (default: 30)')
    parser.add_argument('--max-restarts', type=int, default=100,
                       help='Maximum restart attempts (default: 100)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    
    success = record_stream_resilient(
        stream_url=args.url,
        duration_seconds=args.duration,
        output_file=args.output,
        stall_timeout=args.stall_timeout,
        max_restart_attempts=args.max_restarts
    )
    
    exit(0 if success else 1)
