// --- AetherStream Frontend Application Logic ---

const API_BASE_URL = "http://127.0.0.1:5000/api";
const STREAM_BASE_URL = "http://127.0.0.1:5000/stream";

// Page Views Navigation
const navItems = document.querySelectorAll(".nav-item");
const viewSections = document.querySelectorAll(".view-section");

function switchView(targetId) {
    const targetView = targetId.replace("nav-", "view-");
    
    // Toggle active class on nav links
    navItems.forEach(item => {
        if (item.id === targetId) {
            item.classList.add("active");
        } else {
            item.classList.remove("active");
        }
    });

    // Toggle active class on view sections
    viewSections.forEach(section => {
        if (section.id === targetView) {
            section.classList.add("active");
        } else {
            section.classList.remove("active");
        }
    });

    // If switching to videos library, refresh registry
    if (targetView === "view-videos") {
        fetchLibrary();
    }
}

// Attach Nav Event Listeners
navItems.forEach(item => {
    item.addEventListener("click", (e) => {
        e.preventDefault();
        switchView(item.id);
        
        // Update URL hash
        const hash = item.getAttribute("href");
        history.pushState(null, null, hash);
    });
});

// Handle browser navigation buttons
window.addEventListener("popstate", () => {
    const hash = window.location.hash || "#dashboard";
    const matchingNav = Array.from(navItems).find(item => item.getAttribute("href") === hash);
    if (matchingNav) {
        switchView(matchingNav.id);
    }
});

// API System Health Checker
async function checkSystemHealth() {
    const indicator = document.getElementById("system-status-indicator");
    const statusText = document.getElementById("system-status-text");
    const nodeStatus = document.getElementById("node-upload-api-status");
    const nodeTranscoder = document.getElementById("node-transcoder-status");

    try {
        const response = await fetch(`${API_BASE_URL}/health`);
        if (!response.ok) throw new Error("API responds with error status.");
        
        const data = await response.json();
        
        // System Online Status Update
        indicator.className = "status-indicator online";
        statusText.innerText = "Backend Online";
        
        // Node Status Details Update
        nodeStatus.innerHTML = `<span style="color: var(--accent-green)">Online</span> (${(data.max_file_size_bytes / (1024*1024)).toFixed(0)}MB limit)`;
        
        // Mark FFmpeg Transcoder status active in ecosystem view
        nodeTranscoder.innerHTML = `<span style="color: var(--accent-green)">Active Worker Pool</span>`;
        
        return true;
    } catch (error) {
        console.error("Health check error:", error);
        
        indicator.className = "status-indicator offline";
        statusText.innerText = "Backend Offline";
        nodeStatus.innerHTML = `<span style="color: var(--accent-red)">Offline</span> (Connection failed)`;
        nodeTranscoder.innerHTML = `<span style="color: var(--text-secondary)">Offline (No active worker)</span>`;
        
        return false;
    }
}

// Global Polling state to prevent overlapping intervals
let libraryPollingTimeout = null;

// Media Library Ingestion Display
async function fetchLibrary() {
    const tableBody = document.getElementById("library-table-body");
    const totalCompletedLabel = document.getElementById("stat-completed-uploads");
    const totalJobsLabel = document.getElementById("stat-transcoding-jobs");

    try {
        const response = await fetch(`${API_BASE_URL}/videos`);
        if (!response.ok) throw new Error("Failed to fetch library.");

        const videos = await response.json();
        
        // Update Dashboard Stats Counters (transcode metrics)
        const completedTranscodes = videos.filter(v => v.transcode_status === 'completed');
        const activeTranscodeJobs = videos.filter(v => v.transcode_status === 'pending' || v.transcode_status === 'processing');
        
        totalCompletedLabel.innerText = completedTranscodes.length;
        totalJobsLabel.innerText = activeTranscodeJobs.length;

        if (videos.length === 0) {
            tableBody.innerHTML = `<tr><td colspan="6" class="table-empty">No video assets found in registry.</td></tr>`;
            return;
        }

        // Render Table Rows
        tableBody.innerHTML = videos.map(video => {
            const date = new Date(video.created_at + 'Z').toLocaleString();
            const sizeInMB = (video.file_size / (1024 * 1024)).toFixed(2);
            
            // Upload progress cell
            let uploadHtml = "";
            if (video.status === 'completed') {
                uploadHtml = `<span class="badge badge-completed"><i class="fa-solid fa-circle-check"></i> Merged</span>`;
            } else if (video.status === 'failed') {
                uploadHtml = `<span class="badge badge-failed"><i class="fa-solid fa-circle-xmark"></i> Failed</span>`;
            } else {
                uploadHtml = `<span class="badge badge-uploading"><i class="fa-solid fa-spinner fa-spin"></i> Ingesting</span>`;
            }

            // Transcode status cell
            let transcodeHtml = "";
            const tStatus = video.transcode_status || 'none';
            const tProgress = video.transcode_progress || 0.0;

            if (tStatus === 'completed') {
                transcodeHtml = `<span class="badge-transcode completed"><i class="fa-solid fa-circle-check"></i> Ready</span>`;
            } else if (tStatus === 'processing') {
                transcodeHtml = `<span class="badge-transcode processing"><i class="fa-solid fa-gear fa-spin"></i> Processing (${tProgress.toFixed(1)}%)</span>`;
            } else if (tStatus === 'pending') {
                transcodeHtml = `<span class="badge-transcode pending"><i class="fa-solid fa-hourglass-start"></i> Queued</span>`;
            } else if (tStatus === 'failed') {
                transcodeHtml = `<span class="badge-transcode failed"><i class="fa-solid fa-circle-xmark"></i> Failed</span>`;
            } else {
                transcodeHtml = `<span class="badge-transcode none"><i class="fa-solid fa-clock-rotate-left"></i> Not Started</span>`;
            }

            // Action triggers
            let actionsHtml = "-";
            if (tStatus === 'completed') {
                // Escape filename characters
                const safeFilename = video.filename.replace(/'/g, "\\'");
                actionsHtml = `
                    <button class="btn-play" onclick="playVideo('${video.video_id}', '${safeFilename}')">
                        <i class="fa-solid fa-play"></i> Play Stream
                    </button>
                `;
            }

            return `
                <tr>
                    <td style="font-weight: 500;">
                        ${video.filename}
                        <div style="font-family: monospace; font-size: 0.75rem; color: var(--text-secondary); margin-top: 4px;">ID: ${video.video_id}</div>
                    </td>
                    <td>${sizeInMB} MB</td>
                    <td>${uploadHtml}</td>
                    <td>${transcodeHtml}</td>
                    <td style="color: var(--text-secondary);">${date}</td>
                    <td>${actionsHtml}</td>
                </tr>
            `;
        }).join("");

        // Active transcoding automatic polling loop setup
        if (activeTranscodeJobs.length > 0) {
            console.log("[*] Running jobs detected. Spawning transcoding status check...");
            if (libraryPollingTimeout) clearTimeout(libraryPollingTimeout);
            libraryPollingTimeout = setTimeout(fetchLibrary, 3000);
        }

    } catch (error) {
        console.error("Library load error:", error);
        tableBody.innerHTML = `<tr><td colspan="6" class="table-empty" style="color: var(--accent-red)">Error querying asset registry. Is the server running?</td></tr>`;
    }
}

// Global active video streaming state
let activeVideoId = null;

// Video player controller function
window.playVideo = function(videoId, filename) {
    activeVideoId = videoId;
    
    const playerCard = document.getElementById("video-player-card");
    const playerTitle = document.getElementById("player-video-title");
    const playerVideo = document.getElementById("video-player");
    
    // Unhide card and load title
    playerCard.classList.remove("hidden");
    playerTitle.innerText = `Stream Quality Player: ${filename}`;
    
    // Set poster thumbnail URL from static stream endpoint
    playerVideo.poster = `${STREAM_BASE_URL}/${videoId}_thumb.jpg`;
    
    // Reset quality controls active state (Default to 720p)
    document.getElementById("btn-quality-480p").classList.remove("active");
    document.getElementById("btn-quality-720p").classList.add("active");
    
    // Set source URL and load player
    playerVideo.src = `${STREAM_BASE_URL}/${videoId}_720p.mp4`;
    playerVideo.load();
    playerVideo.play().catch(err => {
        console.log("[*] Autoplay blocked, waiting for user click interaction: ", err);
    });
    
    // Smooth scroll down to video player
    playerCard.scrollIntoView({ behavior: 'smooth' });
};

// Resolution Switch Controller
function switchResolution(quality) {
    if (!activeVideoId) return;
    
    const playerVideo = document.getElementById("video-player");
    
    // 1. Capture current playback timestamp and state to allow seamless transitions
    const currentTime = playerVideo.currentTime;
    const isPaused = playerVideo.paused;
    
    // 2. Set active quality button selector classes
    if (quality === '720p') {
        document.getElementById("btn-quality-480p").classList.remove("active");
        document.getElementById("btn-quality-720p").classList.add("active");
    } else {
        document.getElementById("btn-quality-720p").classList.remove("active");
        document.getElementById("btn-quality-480p").classList.add("active");
    }
    
    // 3. Load the selected resolution stream
    playerVideo.src = `${STREAM_BASE_URL}/${activeVideoId}_${quality}.mp4`;
    playerVideo.load();
    
    // 4. Seek to the timestamp we captured
    playerVideo.currentTime = currentTime;
    
    // 5. Restore playback state
    if (!isPaused) {
        playerVideo.play().catch(e => console.log("Play interrupted during seek: ", e));
    }
}

// Drag & Drop / File Selection UI Elements
const dropZone = document.getElementById("drop-zone");
const fileInput = document.getElementById("file-input");
const filePanel = document.getElementById("file-panel");
const fileNameLabel = document.getElementById("file-name");
const fileSizeLabel = document.getElementById("file-size");
const btnCancelFile = document.getElementById("btn-cancel-file");

// Upload Execution States
let selectedFile = null;
let videoId = null;
let chunkSize = null;
let totalChunks = null;
let currentChunkIndex = 0;
let isPaused = false;
let uploadStartTime = null;

// Trigger file input click
dropZone.addEventListener("click", () => {
    fileInput.click();
});

// Drag highlights
['dragenter', 'dragover'].forEach(eventName => {
    dropZone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropZone.classList.add('dragover');
    }, false);
});

// Drag cleanup
['dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropZone.classList.remove('dragover');
    }, false);
});

// Drop handler
dropZone.addEventListener('drop', (e) => {
    const dt = e.dataTransfer;
    const files = dt.files;
    if (files.length > 0) {
        handleFileSelection(files[0]);
    }
});

// File input browse handler
fileInput.addEventListener('change', () => {
    if (fileInput.files.length > 0) {
        handleFileSelection(fileInput.files[0]);
    }
});

function handleFileSelection(file) {
    selectedFile = file;
    fileNameLabel.innerText = file.name;
    const sizeInMB = (file.size / (1024 * 1024)).toFixed(2);
    fileSizeLabel.innerText = `${sizeInMB} MB`;
    
    // Switch Panels
    dropZone.classList.add("hidden");
    filePanel.classList.remove("hidden");
    
    // Reset Upload State variables
    videoId = null;
    chunkSize = null;
    totalChunks = null;
    currentChunkIndex = 0;
    isPaused = false;
    
    // Reset UI
    document.getElementById("progress-section").classList.add("hidden");
    document.getElementById("btn-start-upload").classList.remove("hidden");
    document.getElementById("btn-start-upload").innerHTML = `<i class="fa-solid fa-play"></i> Start Chunked Upload`;
    document.getElementById("btn-pause-upload").classList.add("hidden");
}

// Cancel click
btnCancelFile.addEventListener("click", () => {
    selectedFile = null;
    fileInput.value = "";
    videoId = null;
    isPaused = false;
    
    dropZone.classList.remove("hidden");
    filePanel.classList.add("hidden");
});

// Start Upload Handler
const btnStartUpload = document.getElementById("btn-start-upload");
const btnPauseUpload = document.getElementById("btn-pause-upload");

btnStartUpload.addEventListener("click", async () => {
    if (!selectedFile) return;

    if (videoId && isPaused) {
        // Resuming paused upload
        isPaused = false;
        btnStartUpload.classList.add("hidden");
        btnPauseUpload.classList.remove("hidden");
        document.getElementById("upload-status-label").innerText = `Resuming upload...`;
        uploadStartTime = Date.now() - ((currentChunkIndex / totalChunks) * (Date.now() - uploadStartTime)); // Adjust start time for math
        uploadNextChunk();
        return;
    }

    try {
        btnStartUpload.disabled = true;
        document.getElementById("upload-status-label").innerText = "Initializing session on server...";
        document.getElementById("progress-section").classList.remove("hidden");
        
        // 1. Initiate Upload session
        const initResponse = await fetch(`${API_BASE_URL}/upload/initiate`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                filename: selectedFile.name,
                file_size: selectedFile.size
            })
        });

        const initData = await initResponse.json();
        if (!initResponse.ok) {
            throw new Error(initData.error || "Initialization failed.");
        }

        videoId = initData.video_id;
        chunkSize = initData.chunk_size;
        totalChunks = initData.total_chunks;
        currentChunkIndex = 0;
        isPaused = false;
        uploadStartTime = Date.now();

        console.log(`[+] Upload initiated. ID: ${videoId}, Chunks: ${totalChunks}`);

        // Update UI Button states
        btnStartUpload.disabled = false;
        btnStartUpload.classList.add("hidden");
        btnPauseUpload.classList.remove("hidden");

        // 2. Begin uploading chunks
        uploadNextChunk();

    } catch (error) {
        console.error("Initiate error:", error);
        alert(`Failed to initialize upload: ${error.message}`);
        document.getElementById("upload-status-label").innerText = `Error: ${error.message}`;
        btnStartUpload.disabled = false;
    }
});

// Pause Upload Handler
btnPauseUpload.addEventListener("click", () => {
    isPaused = true;
    btnPauseUpload.classList.add("hidden");
    btnStartUpload.classList.remove("hidden");
    btnStartUpload.innerHTML = `<i class="fa-solid fa-play"></i> Resume Upload`;
    document.getElementById("upload-status-label").innerText = "Upload paused.";
});

// Sequentially upload chunks
async function uploadNextChunk() {
    if (isPaused) return;

    const start = currentChunkIndex * chunkSize;
    const end = Math.min(start + chunkSize, selectedFile.size);
    const chunkBlob = selectedFile.slice(start, end);

    document.getElementById("upload-status-label").innerText = `Uploading chunk ${currentChunkIndex + 1} of ${totalChunks}...`;

    const formData = new FormData();
    formData.append("video_id", videoId);
    formData.append("chunk_index", currentChunkIndex);
    formData.append("file", chunkBlob, selectedFile.name);

    try {
        const response = await fetch(`${API_BASE_URL}/upload/chunk`, {
            method: "POST",
            body: formData
        });

        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || `Chunk ${currentChunkIndex} upload failed.`);
        }

        console.log(`[+] Chunk ${currentChunkIndex} uploaded.`);
        
        // Progress math
        currentChunkIndex++;
        const percent = Math.min(Math.round((currentChunkIndex / totalChunks) * 100), 100);
        document.getElementById("progress-bar-fill").style.width = `${percent}%`;
        document.getElementById("upload-percentage").innerText = `${percent}%`;

        // Calculate speed & ETA
        const timeElapsed = (Date.now() - uploadStartTime) / 1000;
        const bytesUploaded = Math.min(currentChunkIndex * chunkSize, selectedFile.size);
        const speedBytes = bytesUploaded / timeElapsed;
        const speedMB = (speedBytes / (1024 * 1024)).toFixed(2);
        
        document.getElementById("upload-speed").innerHTML = `<i class="fa-solid fa-gauge-high"></i> ${speedMB} MB/s`;

        const remainingBytes = selectedFile.size - bytesUploaded;
        const etaSeconds = speedBytes > 0 ? remainingBytes / speedBytes : 0;
        const etaMinutes = Math.floor(etaSeconds / 60);
        const etaRemainderSeconds = Math.floor(etaSeconds % 60);
        const etaFormatted = `${etaMinutes}:${etaRemainderSeconds.toString().padStart(2, '0')}`;

        document.getElementById("upload-time-remaining").innerHTML = `<i class="fa-solid fa-clock"></i> ${etaFormatted} remaining`;

        if (currentChunkIndex < totalChunks) {
            // Recurse next chunk
            uploadNextChunk();
        } else {
            // Complete upload
            completeUploadSession();
        }

    } catch (error) {
        console.error(`Upload error on chunk ${currentChunkIndex}:`, error);
        alert(`Upload interrupted: ${error.message}`);
        document.getElementById("upload-status-label").innerText = `Upload failed: ${error.message}`;
        
        isPaused = true;
        btnPauseUpload.classList.add("hidden");
        btnStartUpload.classList.remove("hidden");
        btnStartUpload.innerHTML = `<i class="fa-solid fa-rotate-left"></i> Retry Upload`;
    }
}

// Complete and merge session
async function completeUploadSession() {
    document.getElementById("upload-status-label").innerText = "Assembling chunks on server...";
    btnPauseUpload.classList.add("hidden");

    try {
        const response = await fetch(`${API_BASE_URL}/upload/complete`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ video_id: videoId })
        });

        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || "Merging failed.");
        }

        console.log("[+] Merge complete:", data);
        document.getElementById("upload-status-label").innerHTML = `<span style="color: var(--accent-green)">Upload complete and queued for transcoding!</span>`;
        
        // Reset file selection
        selectedFile = null;
        fileInput.value = "";
        
        // Transition back to play button as finished state
        btnStartUpload.classList.remove("hidden");
        btnStartUpload.innerHTML = `<i class="fa-solid fa-check"></i> Finished`;
        btnStartUpload.disabled = true;

        // Refresh stats/library registry
        fetchLibrary();

    } catch (error) {
        console.error("Complete error:", error);
        alert(`Merge error: ${error.message}`);
        document.getElementById("upload-status-label").innerText = `Merge error: ${error.message}`;
        
        btnStartUpload.classList.remove("hidden");
        btnStartUpload.innerHTML = `<i class="fa-solid fa-rotate-left"></i> Retry Complete`;
    }
}

// Registry Refresher button
document.getElementById("btn-refresh-library").addEventListener("click", () => {
    fetchLibrary();
});

// Initial Setup on Page Load
document.addEventListener("DOMContentLoaded", () => {
    // Navigate based on initial hash or fallback
    const hash = window.location.hash || "#dashboard";
    const matchingNav = Array.from(navItems).find(item => item.getAttribute("href") === hash);
    if (matchingNav) {
        switchView(matchingNav.id);
    }
    
    // Initialize health and library query
    checkSystemHealth();
    fetchLibrary();
    
    // Regular health check interval
    setInterval(checkSystemHealth, 10000);
    
    // Video player close event handler
    document.getElementById("btn-close-player").addEventListener("click", () => {
        const playerVideo = document.getElementById("video-player");
        playerVideo.pause();
        document.getElementById("video-player-card").classList.add("hidden");
    });
    
    // Quality selection switch events
    document.getElementById("btn-quality-720p").addEventListener("click", () => {
        switchResolution("720p");
    });
    document.getElementById("btn-quality-480p").addEventListener("click", () => {
        switchResolution("480p");
    });
});
