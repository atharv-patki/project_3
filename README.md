# AetherStream - High-Throughput Video Pipeline & Streaming Analytics

AetherStream is a high-throughput, event-driven video transcoding and streaming analytics pipeline built for modern Media & Entertainment (OTT) platforms (simulating core architectures of Netflix and YouTube). 

This repository houses the **Week 1 & 2 Deliverables**: A robust, secure, microservice-based Flask backend supporting chunked uploads for large media files (500MB+), integrated SQLite database metadata persistence, magic byte file signature verification, a thread-safe asynchronous task queue, real-time FFmpeg transcoding (720p HD, 480p SD, and thumbnail posters), and a responsive glassmorphic web dashboard.

---

## Architecture Overview

```mermaid
flowchart TD
    subgraph Frontend Client
        UI[Glassmorphic Web Interface]
        Slicer[Chunk Slicing Utility]
        Player[HTML5 Multi-Res Player]
    end

    subgraph Backend Server (Flask)
        API[Flask Upload & Status API]
        SM[Storage Service Manager]
        DB[(SQLite Registry DB)]
        Sec[Security Validator]
        Sweep[Background Sweeper Thread]
        Worker[Background Transcode Thread]
        Trans[Transcoder Service - FFmpeg]
    end

    subgraph Simulated Cloud Storage
        Temp[storage/temp/ - Temp Chunks]
        Final[storage/mock_cloud/ - Merged & Transcoded Videos]
    end

    UI -->|1. Initiate| API
    API -->|1.1 Setup Session| DB
    API -->|1.2 Create Temp Folder| SM
    SM --> Temp
    
    UI -->|2. Upload Chunks| Slicer
    Slicer -->|2.1 Binary Chunk payload| API
    API -->|2.2 Magic Bytes Validation| Sec
    API -->|2.3 Save chunk file| SM
    SM -->|chunk_0, chunk_1...| Temp
    
    UI -->|3. Complete Upload| API
    API -->|3.1 Sequentially Merge Chunks| SM
    Temp -->|Copy & Append| SM
    SM -->|3.2 Write Merged Video| Final
    SM -->|3.3 Verify Size & Cleanup| Temp
    API -->|3.4 Update Status to Completed| DB
    API -->|3.5 Queue Job| Worker
    
    Worker -->|4. Probe Duration & Run FFmpeg| Trans
    Trans -->|4.1 Read Raw merged file| Final
    Trans -->|4.2 Parse -progress| Worker
    Worker -->|4.3 Update DB transcode_progress| DB
    Trans -->|4.4 Write 720p/480p/thumb| Final
    Worker -->|4.5 Mark Completed| DB
    
    Player -->|5. Get Video List| API
    Player -->|6. Fetch Stream URL & Play| Final
    
    Sweep -->|Clean Orphaned folders >2h| Temp
    Sweep -->|Mark Failed| DB
```

### Architectural Decisions & Rationale
1. **Flask Microservice Structure**: Designed as lightweight decoupled endpoints, facilitating separation between the ingestion API and downstream transcoding/analytics operations.
2. **Chunked Upload Protocol**: Large files are sliced on the client using `Blob.slice()` and sent sequentially to prevent memory overflow on the main web server.
3. **MIME/Magic Bytes Verification**: To secure the backend, the first chunk of every upload is scanned for magic signatures. This prevents malicious files from being uploaded under a disguised `.mp4` extension.
4. **SQLite Metadata Registry**: Persists upload states (`initiated`, `uploading`, `completed`, `failed`), transcoding metrics (`pending`, `processing`, `completed`, `failed`), and output assets paths.
5. **Thread-Safe Queue & Background Worker**: Implements Python's `queue.Queue` and a background daemon thread that processes transcoding tasks sequentially in a non-blocking fashion.
6. **Deadlock-Proof Popen Streaming**: Integrates combined `stderr=subprocess.STDOUT` output streams in `transcoder_service.py` to prevent OS pipe deadlock conditions when transcoding large media files.
7. **2-Pass Progress Tracking**: Translates real-time `-progress` output timestamps against video durations, allocating 0%–50% to the 720p HD pass, and 50%–100% to the 480p SD pass.
8. **Portable Asset Streaming**: Provides direct media routing via `/stream/<filename>` with custom content type headers for seamless browser streaming and poster thumbnail loading.

---

## Getting Started

### Prerequisites
- Python 3.10 or higher
- Git

### Installation & Local Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/atharv-patki/project_3.git
   cd project_3
   ```

2. **Set up the virtual environment**:
   ```bash
   python -m venv venv
   # On Windows (PowerShell):
   .\venv\Scripts\Activate.ps1
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r backend/requirements.txt
   ```

4. **Install Portable FFmpeg Binaries (Windows)**:
   We automate the download and configuration of static static releases of `ffmpeg` and `ffprobe`:
   ```bash
   # Run the portable downloader from your scratch space
   python .gemini/antigravity-ide/brain/71948f5d-9a62-4fca-9cdd-2693b0ab290f/scratch/download_ffmpeg.py
   ```
   *This extracts `ffmpeg.exe` and `ffprobe.exe` directly into `backend/bin/`.*

5. **Configure Environment Variables**:
   Create a `.env` file in the root directory (based on `.env.example`):
   ```ini
   FLASK_ENV=development
   PORT=5000
   HOST=127.0.0.1
   FFMPEG_PATH=backend/bin/ffmpeg.exe
   UPLOAD_TEMP_DIR=storage/temp
   UPLOAD_FINAL_DIR=storage/mock_cloud
   MAX_CONTENT_LENGTH=524288000
   CHUNK_SIZE=5242880
   ```

---

## Running the Ecosystem

### 1. Launch the Flask Backend API
Run the Flask server using the environment's python executable:
```bash
python backend/app.py
```
Upon startup, the system automatically initializes the storage directories (`storage/temp/`, `storage/mock_cloud/`) and runs SQLite migrations to add transcoding schema structures.

### 2. Launch the Static Frontend Dev Server
To serve the static web dashboard, start Python's built-in HTTP server from the root of the project:
```bash
python -m http.server 8080 --directory frontend
```
Now, open your browser and navigate to:
**`http://localhost:8080`**

---

## API Specification

All API routes are prefixed with `/api`.

### 1. System Health
* **Endpoint**: `GET /api/health`
* **Description**: Verifies API availability and checks write permissions of storage systems.

### 2. Initiate Upload Session
* **Endpoint**: `POST /api/upload/initiate`
* **Payload (JSON)**:
  ```json
  {
    "filename": "my_holiday_video.mp4",
    "file_size": 12582912
  }
  ```

### 3. Upload Binary Chunk
* **Endpoint**: `POST /api/upload/chunk`
* **Payload (Multipart Form-Data)**:
  - `video_id`: `23e5d97a-47d0-42a2-8bc9-1b196df7aed3`
  - `chunk_index`: `0`
  - `file`: `[Raw Binary Blob]`

### 4. Complete Upload
* **Endpoint**: `POST /api/upload/complete`
* **Description**: Triggers chunk merging on the server, verifies final file size integrity, cleans up transient chunk directories, marks the status as `completed`, and automatically enqueues a background transcoding task.

### 5. Get Upload Progress Status
* **Endpoint**: `GET /api/upload/status/<video_id>`

### 6. List Registered Video Assets
* **Endpoint**: `GET /api/videos`
* **Response (200 OK)**: Includes transcoding metrics fields:
  ```json
  [
    {
      "video_id": "23e5d97a-47d0-42a2-8bc9-1b196df7aed3",
      "filename": "my_holiday_video.mp4",
      "file_size": 12582912,
      "total_chunks": 3,
      "status": "completed",
      "transcode_status": "completed",
      "transcode_progress": 100.0,
      "path_720p": "storage/mock_cloud/23e5d97a-47d0-42a2-8bc9-1b196df7aed3_720p.mp4",
      "path_480p": "storage/mock_cloud/23e5d97a-47d0-42a2-8bc9-1b196df7aed3_480p.mp4",
      "path_thumbnail": "storage/mock_cloud/23e5d97a-47d0-42a2-8bc9-1b196df7aed3_thumb.jpg",
      "created_at": "2026-08-25 13:49:23"
    }
  ]
  ```

### 7. Get Video Transcoding Status
* **Endpoint**: `GET /api/transcode/status/<video_id>`
* **Description**: Returns detailed background job state variables for transcoding.
* **Response (200 OK)**:
  ```json
  {
    "video_id": "23e5d97a-47d0-42a2-8bc9-1b196df7aed3",
    "transcode_status": "processing",
    "transcode_progress": 34.67,
    "path_720p": "storage/mock_cloud/23e5d97a-47d0-42a2-8bc9-1b196df7aed3_720p.mp4",
    "path_480p": "storage/mock_cloud/23e5d97a-47d0-42a2-8bc9-1b196df7aed3_480p.mp4",
    "path_thumbnail": "storage/mock_cloud/23e5d97a-47d0-42a2-8bc9-1b196df7aed3_thumb.jpg"
  }
  ```

### 8. Stream Transcoded Media Asset
* **Endpoint**: `GET /stream/<filename>`
* **Description**: Serves static transcoded files and poster images from the mock cloud storage folder with correct content headers.
* **Stream URLs**:
  - 720p Stream: `/stream/<video_id>_720p.mp4`
  - 480p Stream: `/stream/<video_id>_480p.mp4`
  - Poster Thumbnail: `/stream/<video_id>_thumb.jpg`

---

## E2E Integration Testing
We ship a suite of verification test scripts inside the `.gemini/` scratch workspace:
- **`test_storage.py`**: Verifies `StorageService` chunk saving, ordered joining, and temp directory cleanup.
- **`test_api.py`**: Verifies HTTP status codes, chunk sequence validations, and API progress indicators for a 12MB file upload.
- **`test_security.py`**: Verifies magic bytes signature rejection and manual sweeper updates.
- **`test_large_upload.py`**: Performs an E2E 100MB chunked upload sequence and verifies that the output has matching SHA-256 hashes.
- **`test_worker.py`**: Validates SQLite migrations and background worker thread queue execution.
- **`test_transcoder.py`**: Verifies FFmpeg command construction and output asset creation on disk.
- **`test_progress_tracking.py`**: Tests real-time polling updates and 2-pass progress database logs.
- **`test_upload_to_transcode.py`**: Runs an integrated E2E upload-to-transcode flow, polling database stats dynamically via REST API.
