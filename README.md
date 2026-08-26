# AetherStream - High-Throughput Video Pipeline & Streaming Analytics

AetherStream is a high-throughput, event-driven video transcoding and streaming analytics pipeline built for modern Media & Entertainment (OTT) platforms (simulating core architectures of Netflix and YouTube). 

This repository houses the **Week 1 Deliverables**: A robust, secure, microservice-based Flask backend supporting chunked uploads for large media files (500MB+), integrated SQLite database metadata persistence, magic byte file signature verification, automated transient folder sweeps, and a responsive glassmorphic web dashboard.

---

## Architecture Overview

```mermaid
flowchart TD
    subgraph Frontend Client
        UI[Glassmorphic Web Interface]
        Slicer[Chunk Slicing Utility]
    end

    subgraph Backend Server (Flask)
        API[Flask Upload API]
        SM[Storage Service Manager]
        DB[(SQLite Registry DB)]
        Sec[Security Validator]
        Sweep[Background Sweeper Thread]
    end

    subgraph Simulated Cloud Storage
        Temp[storage/temp/ - Temp Chunks]
        Final[storage/mock_cloud/ - Completed Videos]
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
    
    Sweep -->|Clean Orphaned folders >2h| Temp
    Sweep -->|Mark Failed| DB
```

### Architectural Decisions & Rationale
1. **Flask Microservice Structure**: Designed as lightweight decoupled endpoints, facilitating separation between the ingestion API and downstream transcoding/analytics operations.
2. **Chunked Upload Protocol**: Large files are sliced on the client using `Blob.slice()` and sent sequentially to prevent memory overflow on the main web server.
3. **MIME/Magic Bytes Verification**: To secure the backend, the first chunk of every upload is scanned for magic signatures. This prevents malicious files from being uploaded under a disguised `.mp4` extension.
4. **SQLite Metadata Registry**: Persists upload states (`initiated`, `uploading`, `completed`, `failed`) and metrics.
5. **Dynamic Sweeper Thread**: A background daemon thread sweeps `storage/temp` every 10 minutes, deleting temporary chunk folders older than 2 hours to prevent disk space exhaustion.

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

4. **Configure Environment Variables**:
   Create a `.env` file in the root directory (based on `.env.example`):
   ```ini
   FLASK_ENV=development
   PORT=5000
   HOST=127.0.0.1
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
Upon startup, the system automatically initializes the storage directories (`storage/temp/`, `storage/mock_cloud/`) and sets up the SQLite database registry at `storage/metadata.db`.

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
* **Response (200 OK)**:
  ```json
  {
    "status": "healthy",
    "environment": "development",
    "max_file_size_bytes": 524288000,
    "chunk_size_bytes": 5242880,
    "storage": {
      "temp_directory": "C:\\path\\to\\project\\storage\\temp",
      "temp_writable": true,
      "final_directory": "C:\\path\\to\\project\\storage\\mock_cloud",
      "final_writable": true
    }
  }
  ```

### 2. Initiate Upload Session
* **Endpoint**: `POST /api/upload/initiate`
* **Description**: Registers a new upload session, generates a unique UUID `video_id`, and calculates total chunks.
* **Payload (JSON)**:
  ```json
  {
    "filename": "my_holiday_video.mp4",
    "file_size": 12582912
  }
  ```
* **Response (210 Created)**:
  ```json
  {
    "video_id": "23e5d97a-47d0-42a2-8bc9-1b196df7aed3",
    "chunk_size": 5242880,
    "total_chunks": 3,
    "status": "initiated"
  }
  ```

### 3. Upload Binary Chunk
* **Endpoint**: `POST /api/upload/chunk`
* **Description**: Receives a binary chunk file and saves it in the temporary storage. For `chunk_index = 0`, it verifies magic byte signatures.
* **Payload (Multipart Form-Data)**:
  - `video_id`: `23e5d97a-47d0-42a2-8bc9-1b196df7aed3`
  - `chunk_index`: `0`
  - `file`: `[Raw Binary Blob]`
* **Response (200 OK)**:
  ```json
  {
    "video_id": "23e5d97a-47d0-42a2-8bc9-1b196df7aed3",
    "chunk_index": 0,
    "status": "success"
  }
  ```

### 4. Complete Upload
* **Endpoint**: `POST /api/upload/complete`
* **Description**: Triggers chunk merging on the server, verifies final file size integrity, cleans up transient chunk directories, and marks the status as `completed`.
* **Payload (JSON)**:
  ```json
  {
    "video_id": "23e5d97a-47d0-42a2-8bc9-1b196df7aed3"
  }
  ```
* **Response (200 OK)**:
  ```json
  {
    "video_id": "23e5d97a-47d0-42a2-8bc9-1b196df7aed3",
    "status": "completed",
    "filename": "my_holiday_video.mp4",
    "filepath": "C:\\path\\to\\project\\storage\\mock_cloud\\23e5d97a-47d0-42a2-8bc9-1b196df7aed3.mp4"
  }
  ```

### 5. Get Upload Progress Status
* **Endpoint**: `GET /api/upload/status/<video_id>`
* **Description**: Returns the real-time progress details of a given upload. Progress percentage is computed dynamically by counting matching chunk files on disk.
* **Response (200 OK)**:
  ```json
  {
    "video_id": "23e5d97a-47d0-42a2-8bc9-1b196df7aed3",
    "filename": "my_holiday_video.mp4",
    "file_size": 12582912,
    "total_chunks": 3,
    "status": "uploading",
    "progress_percent": 33.33
  }
  ```

### 6. List Registered Video Assets
* **Endpoint**: `GET /api/videos`
* **Description**: Retrieves a list of all registered video sessions in the database registry.
* **Response (200 OK)**:
  ```json
  [
    {
      "video_id": "23e5d97a-47d0-42a2-8bc9-1b196df7aed3",
      "filename": "my_holiday_video.mp4",
      "file_size": 12582912,
      "total_chunks": 3,
      "status": "completed",
      "created_at": "2026-08-25 13:49:23"
    }
  ]
  ```

---

## E2E Integration Testing
We ship a suite of verification test scripts inside the `.gemini/` scratch workspace. You can run them to manually verify the setup's robustness:
- **`test_storage.py`**: Verifies `StorageService` chunk saving, ordered joining, and temp directory cleanup.
- **`test_api.py`**: Verifies HTTP status codes, chunk sequence validations, and API progress indicators for a 12MB file upload.
- **`test_security.py`**: Verifies magic bytes signature rejection (returns 400 Bad Request) and manual sweep sweep sweep updates.
- **`test_large_upload.py`**: Performs an E2E 100MB chunked upload sequence and verifies that the output has matching SHA-256 hashes.
