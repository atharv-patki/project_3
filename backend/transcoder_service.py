import subprocess
from pathlib import Path
from config import Config

class TranscoderService:
    @classmethod
    def _run_ffmpeg_command(cls, args: list) -> str:
        """
        Execute an FFmpeg command using the subprocess module.
        Captures stderr diagnostic data in case of execution errors.
        """
        # Build command array using configured FFMPEG_PATH
        cmd = [str(Config.FFMPEG_PATH)] + args
        print(f"[*] Running FFmpeg CLI: {' '.join(cmd)}")
        
        try:
            # Execute command, capture standard outputs, throw exception on non-zero exit codes
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return result.stdout
        except subprocess.CalledProcessError as e:
            print(f"[-] FFmpeg command failed with exit code {e.returncode}")
            print(f"[-] FFmpeg stderr stream:\n{e.stderr}")
            raise RuntimeError(f"FFmpeg transcoding command failed: {e.stderr}")
        except FileNotFoundError:
            raise RuntimeError(
                f"FFmpeg executable not found at '{Config.FFMPEG_PATH}'. "
                "Please verify that FFmpeg is installed and added to the environment PATH."
            )

    @classmethod
    def transcode_to_720p(cls, input_path: str, output_path: str) -> str:
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
        return cls._run_ffmpeg_command(args)

    @classmethod
    def transcode_to_480p(cls, input_path: str, output_path: str) -> str:
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
        return cls._run_ffmpeg_command(args)

    @classmethod
    def extract_thumbnail(cls, input_path: str, output_path: str) -> str:
        """Extract a single frame image (JPEG format) from the video's 5-second mark."""
        args = [
            '-y',
            '-ss', '00:00:05',
            '-i', str(input_path),
            '-vframes', '1',
            '-q:v', '2',
            str(output_path)
        ]
        return cls._run_ffmpeg_command(args)
