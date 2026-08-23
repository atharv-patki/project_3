import os
import shutil
import uuid
from pathlib import Path
from config import Config

class StorageService:
    @staticmethod
    def generate_video_id() -> str:
        """Generate a unique UUID v4 string for a new video asset."""
        return str(uuid.uuid4())

    @classmethod
    def get_upload_temp_dir(cls, video_id: str) -> Path:
        """Get the absolute path to the temporary folder containing chunks for a video_id."""
        return Config.UPLOAD_TEMP_DIR / video_id

    @classmethod
    def get_final_filepath(cls, video_id: str, original_filename: str) -> Path:
        """Get the final destination path for the merged file using its video_id and original extension."""
        suffix = Path(original_filename).suffix.lower()
        if not suffix:
            suffix = ".mp4"  # Default fallback extension
        return Config.UPLOAD_FINAL_DIR / f"{video_id}{suffix}"

    @classmethod
    def initiate_upload(cls, video_id: str = None) -> str:
        """
        Initializes an upload session by generating a video_id and creating its temporary directory.
        Returns the video_id.
        """
        if not video_id:
            video_id = cls.generate_video_id()
        
        temp_dir = cls.get_upload_temp_dir(video_id)
        temp_dir.mkdir(parents=True, exist_ok=True)
        return video_id

    @classmethod
    def save_chunk(cls, video_id: str, chunk_index: int, data: bytes) -> Path:
        """
        Saves a raw binary chunk for a given upload session.
        Chunks are stored as files named like 'chunk_0', 'chunk_1', etc.
        """
        temp_dir = cls.get_upload_temp_dir(video_id)
        if not temp_dir.exists():
            raise FileNotFoundError(f"Upload session '{video_id}' has not been initiated or is invalid.")

        chunk_path = temp_dir / f"chunk_{chunk_index}"
        
        # Write binary chunk to disk
        with open(chunk_path, "wb") as f:
            f.write(data)
            
        return chunk_path

    @classmethod
    def merge_chunks(cls, video_id: str, original_filename: str, total_chunks: int, expected_size: int = None) -> Path:
        """
        Merges all uploaded chunks for a session into a single file in the final directory.
        Removes the temporary chunk folder on completion.
        Validates final size if expected_size is provided.
        """
        temp_dir = cls.get_upload_temp_dir(video_id)
        if not temp_dir.exists():
            raise FileNotFoundError(f"Upload session directory not found for video '{video_id}'.")

        # Verify all chunk files exist before merging
        for i in range(total_chunks):
            chunk_file = temp_dir / f"chunk_{i}"
            if not chunk_file.exists():
                raise FileNotFoundError(f"Missing chunk {i} of {total_chunks} for video '{video_id}'.")

        final_path = cls.get_final_filepath(video_id, original_filename)
        
        # Merge all chunks sequentially
        try:
            with open(final_path, "wb") as target_file:
                for i in range(total_chunks):
                    chunk_file = temp_dir / f"chunk_{i}"
                    with open(chunk_file, "rb") as source_file:
                        shutil.copyfileobj(source_file, target_file)
        except Exception as e:
            # If writing fails, clean up target file if partially written
            if final_path.exists():
                final_path.unlink()
            raise RuntimeError(f"Error merging chunks for video '{video_id}': {e}")

        # Validate final merged file size
        actual_size = final_path.stat().st_size
        if expected_size is not None and actual_size != expected_size:
            # Clean up the invalid merged file
            final_path.unlink()
            raise ValueError(
                f"File size mismatch for video '{video_id}'. "
                f"Expected: {expected_size} bytes, Actual: {actual_size} bytes."
            )

        # Cleanup temporary chunks directory
        shutil.rmtree(temp_dir)
        
        return final_path
