import subprocess
from pathlib import Path
from config import Config

class TranscoderService:
    @classmethod
    def get_video_duration(cls, input_path: str) -> float:
        """Get the duration of a video file in seconds using ffprobe."""
        # Probe using ffprobe located in the same directory as ffmpeg
        ffprobe_path = Path(Config.FFMPEG_PATH).parent / "ffprobe.exe"
        if not ffprobe_path.exists():
            # Fallback to system command search if local binary is missing
            ffprobe_path = Path("ffprobe")
            
        cmd = [
            str(ffprobe_path),
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            str(input_path)
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except Exception as e:
            print(f"[-] Failed to query video duration via ffprobe: {e}")
            return 0.0

    @classmethod
    def _run_ffmpeg_command(cls, args: list, duration: float = 0.0, progress_callback = None) -> str:
        """
        Execute an FFmpeg command using the subprocess module.
        If progress_callback and duration are provided, executes via Popen and parses stdout progress.
        """
        if progress_callback and duration > 0:
            # Inject progress parameter to write updates to standard output stream
            cmd = [str(Config.FFMPEG_PATH), '-progress', '-'] + args
            print(f"[*] Running FFmpeg with progress tracking: {' '.join(cmd)}")
            
            log_lines = []
            try:
                # Redirect stderr to stdout to prevent OS pipe deadlock when buffer fills up
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )
                
                while True:
                    line = process.stdout.readline()
                    if not line:
                        break
                    log_lines.append(line)
                    if '=' in line:
                        parts = line.strip().split('=', 1)
                        if len(parts) == 2:
                            key, val = parts
                            if key == 'out_time_us':
                                try:
                                    current_us = int(val)
                                    current_seconds = current_us / 1_000_000.0
                                    # Compute current percentage, clamping at 100%
                                    percent = min(100.0, (current_seconds / duration) * 100.0)
                                    progress_callback(percent)
                                except ValueError:
                                    pass
                                    
                process.wait()
                if process.returncode != 0:
                    err_msg = "".join(log_lines)
                    print(f"[-] FFmpeg process failed with exit code {process.returncode}")
                    print(f"[-] FFmpeg Output:\n{err_msg}")
                    raise RuntimeError(f"FFmpeg transcoding command failed: {err_msg}")
                return "".join(log_lines)
            except subprocess.SubprocessError as e:
                raise RuntimeError(f"FFmpeg process execution failed: {e}")
            except FileNotFoundError:
                raise RuntimeError(
                    f"FFmpeg executable not found at '{Config.FFMPEG_PATH}'."
                )
        else:
            # Fallback to standard subprocess.run for static/non-streamable commands (e.g. thumbnails)
            cmd = [str(Config.FFMPEG_PATH)] + args
            print(f"[*] Running static FFmpeg command: {' '.join(cmd)}")
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                return result.stdout
            except subprocess.CalledProcessError as e:
                print(f"[-] FFmpeg static command failed with exit code {e.returncode}")
                print(f"[-] FFmpeg stderr output:\n{e.stderr}")
                raise RuntimeError(f"FFmpeg transcoding command failed: {e.stderr}")
            except FileNotFoundError:
                raise RuntimeError(
                    f"FFmpeg executable not found at '{Config.FFMPEG_PATH}'."
                )

    @classmethod
    def transcode_to_720p(cls, input_path: str, output_path: str, duration: float = 0.0, progress_callback = None) -> str:
        """Transcode video to 1280x720 H.264 @ 2.5 Mbps with AAC Audio @ 128 kbps."""
        args = [
            '-y', 
            '-i', str(input_path),
            '-vf', 'scale=1280:720',
            '-c:v', 'libx264',
            '-b:v', '2500k',
            '-c:a', 'aac',
            '-b:a', '128k',
            str(output_path)
        ]
        return cls._run_ffmpeg_command(args, duration, progress_callback)

    @classmethod
    def transcode_to_480p(cls, input_path: str, output_path: str, duration: float = 0.0, progress_callback = None) -> str:
        """Transcode video to 854x480 H.264 @ 1.0 Mbps with AAC Audio @ 96 kbps."""
        args = [
            '-y', 
            '-i', str(input_path),
            '-vf', 'scale=854:480',
            '-c:v', 'libx264',
            '-b:v', '1000k',
            '-c:a', 'aac',
            '-b:a', '96k',
            str(output_path)
        ]
        return cls._run_ffmpeg_command(args, duration, progress_callback)

    @classmethod
    def extract_thumbnail(cls, input_path: str, output_path: str, time_offset_seconds: float = 5.0) -> str:
        """Extract a single frame image (JPEG format) from the video."""
        duration = cls.get_video_duration(input_path)
        if duration > 0 and time_offset_seconds >= duration:
            time_offset_seconds = max(0.1, duration / 2.0)

        hrs = int(time_offset_seconds // 3600)
        mins = int((time_offset_seconds % 3600) // 60)
        secs = time_offset_seconds % 60
        ss_str = f"{hrs:02d}:{mins:02d}:{secs:06.3f}"

        args = [
            '-y',
            '-ss', ss_str,
            '-i', str(input_path),
            '-vframes', '1',
            '-q:v', '2',
            str(output_path)
        ]
        return cls._run_ffmpeg_command(args)
