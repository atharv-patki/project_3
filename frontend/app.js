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
    } else if (targetView === "view-reports") {
        fetchReportsData();
        populateReportVideoFilter();
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

// Global active video streaming & telemetry state
let activeVideoId = null;
let currentSessionId = null;
let currentQuality = "720p";
let telemetryHeartbeatTimer = null;
let totalTelemetryPings = 0;

// Persistent User ID for telemetry sessions
function getOrCreateUserId() {
    let uid = localStorage.getItem("aether_user_id");
    if (!uid) {
        uid = "usr_" + Math.random().toString(36).substring(2, 10);
        localStorage.setItem("aether_user_id", uid);
    }
    return uid;
}

// Calculate buffer health (seconds of video buffer ahead of current playhead)
function calculateBufferHealth(video) {
    if (!video || !video.buffered || video.buffered.length === 0) return 0.0;
    const curTime = video.currentTime;
    for (let i = 0; i < video.buffered.length; i++) {
        const start = video.buffered.start(i);
        const end = video.buffered.end(i);
        if (start <= curTime && curTime <= end) {
            return Math.max(0, +(end - curTime).toFixed(2));
        }
    }
    return 0.0;
}

// Update Telemetry HUD metrics
function updateTelemetryHUD(bufferHealth, state) {
    const bufferLabel = document.getElementById("telemetry-buffer-val");
    const stateLabel = document.getElementById("telemetry-state-val");
    const statusLabel = document.getElementById("telemetry-status-label");
    const pulseIndicator = document.querySelector(".telemetry-pulse");

    if (bufferLabel) bufferLabel.innerText = `${bufferHealth.toFixed(1)}s`;
    if (stateLabel) stateLabel.innerText = state.charAt(0).toUpperCase() + state.slice(1);
    
    if (pulseIndicator) {
        if (state === "playing" || state === "buffering") {
            pulseIndicator.classList.remove("paused");
            if (statusLabel) statusLabel.innerText = "Telemetry: Active (1s heartbeat)";
        } else {
            pulseIndicator.classList.add("paused");
            if (statusLabel) statusLabel.innerText = "Telemetry: Idle (Paused)";
        }
    }
}

// Emit Telemetry Heartbeat / State Change event
async function emitTelemetryEvent(overrideState = null) {
    const video = document.getElementById("video-player");
    if (!video || !activeVideoId || !currentSessionId) return;

    const bufferHealth = calculateBufferHealth(video);
    let state = overrideState;
    if (!state) {
        if (video.ended) state = "ended";
        else if (video.seeking) state = "seeking";
        else if (video.paused) state = "paused";
        else if (video.readyState < 3) state = "buffering";
        else state = "playing";
    }

    const payload = {
        user_id: getOrCreateUserId(),
        video_id: activeVideoId,
        session_id: currentSessionId,
        timestamp: Date.now() / 1000,
        watch_time_seconds: +video.currentTime.toFixed(2),
        playback_quality: currentQuality,
        buffer_health: bufferHealth,
        playback_state: state,
        device_type: "web",
        bitrate_kbps: currentQuality === "720p" ? 2500 : 1000
    };

    updateTelemetryHUD(bufferHealth, state);

    try {
        const response = await fetch(`${API_BASE_URL}/analytics/event`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        if (response.ok) {
            totalTelemetryPings++;
            const pingsLabel = document.getElementById("telemetry-pings-val");
            if (pingsLabel) pingsLabel.innerText = totalTelemetryPings;
        }
    } catch (err) {
        console.warn("[*] Telemetry emit failed:", err);
    }
}

function startTelemetryHeartbeat() {
    if (telemetryHeartbeatTimer) clearInterval(telemetryHeartbeatTimer);
    telemetryHeartbeatTimer = setInterval(() => {
        emitTelemetryEvent();
    }, 1000);
}

function stopTelemetryHeartbeat() {
    if (telemetryHeartbeatTimer) {
        clearInterval(telemetryHeartbeatTimer);
        telemetryHeartbeatTimer = null;
    }
}

// Video player controller function
window.playVideo = function(videoId, filename) {
    activeVideoId = videoId;
    currentSessionId = "sess_" + Math.random().toString(36).substring(2, 11);
    currentQuality = "720p";
    totalTelemetryPings = 0;
    
    const pingsLabel = document.getElementById("telemetry-pings-val");
    if (pingsLabel) pingsLabel.innerText = "0";

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

    // Start telemetry heartbeat timer
    startTelemetryHeartbeat();
    emitTelemetryEvent("playing");
    
    // Smooth scroll down to video player
    playerCard.scrollIntoView({ behavior: 'smooth' });
};

// Resolution Switch Controller
function switchResolution(quality) {
    if (!activeVideoId) return;
    currentQuality = quality;
    
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

    // Emit resolution switch telemetry event
    emitTelemetryEvent(isPaused ? "paused" : "playing");
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

// ========================================================
// Real-Time Analytics Dashboard & Trendline Chart Logic
// ========================================================

async function fetchRealtimeAnalytics() {
    const dashboardView = document.getElementById("view-dashboard");
    if (!dashboardView || !dashboardView.classList.contains("active")) {
        return;
    }

    try {
        const response = await fetch(`${API_BASE_URL}/analytics/realtime`);
        if (!response.ok) return;

        const data = await response.json();

        // 1. Update KPI Card Stat counters
        const viewersLabel = document.getElementById("stat-active-viewers");
        const bufferLabel = document.getElementById("stat-avg-buffer");
        const stallLabel = document.getElementById("stat-stall-rate");
        const pingsLabel = document.getElementById("stat-analytics-pings");

        if (viewersLabel) viewersLabel.innerText = data.active_concurrent_viewers || 0;
        if (bufferLabel) bufferLabel.innerText = `${(data.avg_buffer_health_seconds || 0).toFixed(1)}s`;
        if (stallLabel) stallLabel.innerText = `${(data.rebuffer_stall_rate_percent || 0).toFixed(1)}%`;
        if (pingsLabel) pingsLabel.innerText = `${Math.round(data.events_per_second || 0)}/s`;

        // 2. Update Quality Bars
        const totalActive = Math.max(1, data.active_concurrent_viewers || 0);
        const qDist = data.quality_distribution || {};
        const q1080 = qDist["1080p"] || 0;
        const q720 = qDist["720p"] || 0;
        const q480 = qDist["480p"] || 0;

        const p1080 = Math.round((q1080 / totalActive) * 100);
        const p720 = Math.round((q720 / totalActive) * 100);
        const p480 = Math.round((q480 / totalActive) * 100);

        const l1080 = document.getElementById("label-quality-1080p");
        const b1080 = document.getElementById("bar-quality-1080p");
        if (l1080 && b1080) {
            l1080.innerText = `${q1080} (${p1080}%)`;
            b1080.style.width = `${p1080}%`;
        }

        const l720 = document.getElementById("label-quality-720p");
        const b720 = document.getElementById("bar-quality-720p");
        if (l720 && b720) {
            l720.innerText = `${q720} (${p720}%)`;
            b720.style.width = `${p720}%`;
        }

        const l480 = document.getElementById("label-quality-480p");
        const b480 = document.getElementById("bar-quality-480p");
        if (l480 && b480) {
            l480.innerText = `${q480} (${p480}%)`;
            b480.style.width = `${p480}%`;
        }

        // 3. Update Device Chips
        const devDist = data.device_distribution || {};
        const chipWeb = document.getElementById("chip-dev-web");
        const chipMobile = document.getElementById("chip-dev-mobile");
        const chipTv = document.getElementById("chip-dev-tv");
        const chipDesktop = document.getElementById("chip-dev-desktop");

        if (chipWeb) chipWeb.innerText = devDist["web"] || 0;
        if (chipMobile) chipMobile.innerText = devDist["mobile"] || 0;
        if (chipTv) chipTv.innerText = devDist["smart_tv"] || 0;
        if (chipDesktop) chipDesktop.innerText = devDist["desktop"] || 0;

        // 4. Render Live Trendline Chart
        renderTelemetryTrendChart(data.time_series || []);

    } catch (err) {
        console.warn("[*] Realtime analytics query failed:", err);
    }
}

// Canvas-based Real-time Trendline Chart Renderer
function renderTelemetryTrendChart(timeSeries) {
    const canvas = document.getElementById("chart-telemetry-trend");
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    const container = canvas.parentElement;
    const width = container.clientWidth || 500;
    const height = 190;

    // Handle high DPI crisp rendering
    const dpr = window.devicePixelRatio || 1;
    if (canvas.width !== width * dpr || canvas.height !== height * dpr) {
        canvas.width = width * dpr;
        canvas.height = height * dpr;
    }
    ctx.resetTransform();
    ctx.scale(dpr, dpr);

    ctx.clearRect(0, 0, width, height);

    const padding = { top: 20, right: 20, bottom: 25, left: 35 };
    const chartW = width - padding.left - padding.right;
    const chartH = height - padding.top - padding.bottom;

    // Draw background grid lines
    ctx.strokeStyle = "rgba(255, 255, 255, 0.04)";
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
        const y = padding.top + (chartH / 4) * i;
        ctx.beginPath();
        ctx.moveTo(padding.left, y);
        ctx.lineTo(padding.left + chartW, y);
        ctx.stroke();
    }

    if (timeSeries.length < 2) {
        ctx.fillStyle = "rgba(255, 255, 255, 0.3)";
        ctx.font = "12px Inter, sans-serif";
        ctx.textAlign = "center";
        ctx.fillText("Awaiting streaming telemetry data points...", width / 2, height / 2);
        return;
    }

    // Determine max viewers & max buffer for scaling
    const maxViewers = Math.max(10, ...timeSeries.map(p => p.active_viewers || 0));
    const maxBuffer = Math.max(10, ...timeSeries.map(p => p.avg_buffer_health || 0));

    // Helper coordinate calculators
    const getX = (idx) => padding.left + (idx / (timeSeries.length - 1)) * chartW;
    const getYViewers = (val) => padding.top + chartH - (val / maxViewers) * chartH;
    const getYBuffer = (val) => padding.top + chartH - (val / maxBuffer) * chartH;

    // 1. Draw Viewers Fill & Line (Purple)
    const grad = ctx.createLinearGradient(0, padding.top, 0, padding.top + chartH);
    grad.addColorStop(0, "rgba(168, 85, 247, 0.35)");
    grad.addColorStop(1, "rgba(168, 85, 247, 0.0)");

    ctx.beginPath();
    ctx.moveTo(getX(0), getYViewers(timeSeries[0].active_viewers || 0));
    for (let i = 1; i < timeSeries.length; i++) {
        ctx.lineTo(getX(i), getYViewers(timeSeries[i].active_viewers || 0));
    }
    ctx.lineTo(getX(timeSeries.length - 1), padding.top + chartH);
    ctx.lineTo(getX(0), padding.top + chartH);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();

    ctx.beginPath();
    ctx.moveTo(getX(0), getYViewers(timeSeries[0].active_viewers || 0));
    for (let i = 1; i < timeSeries.length; i++) {
        ctx.lineTo(getX(i), getYViewers(timeSeries[i].active_viewers || 0));
    }
    ctx.strokeStyle = "#a855f7";
    ctx.lineWidth = 2.5;
    ctx.shadowColor = "rgba(168, 85, 247, 0.5)";
    ctx.shadowBlur = 8;
    ctx.stroke();
    ctx.shadowBlur = 0; // Reset shadow

    // 2. Draw Buffer Health Line (Cyan)
    ctx.beginPath();
    ctx.moveTo(getX(0), getYBuffer(timeSeries[0].avg_buffer_health || 0));
    for (let i = 1; i < timeSeries.length; i++) {
        ctx.lineTo(getX(i), getYBuffer(timeSeries[i].avg_buffer_health || 0));
    }
    ctx.strokeStyle = "#06b6d4";
    ctx.lineWidth = 1.8;
    ctx.stroke();

    // 3. Draw Axis Labels
    ctx.fillStyle = "rgba(255, 255, 255, 0.35)";
    ctx.font = "10px Inter, sans-serif";
    ctx.textAlign = "right";
    ctx.fillText(maxViewers.toString(), padding.left - 6, padding.top + 10);
    ctx.fillText("0", padding.left - 6, padding.top + chartH);

    ctx.textAlign = "center";
    ctx.fillText(timeSeries[0].time_label || "", padding.left, height - 6);
    ctx.fillText(timeSeries[timeSeries.length - 1].time_label || "", padding.left + chartW, height - 6);
}

// ========================================================
// Synthetic Traffic Simulator UI Handlers
// ========================================================

async function fetchSimulationStatus() {
    try {
        const res = await fetch(`${API_BASE_URL}/analytics/simulation/status`);
        if (!res.ok) return;
        const st = await res.json();
        updateSimulationUI(st);
    } catch (err) {
        console.warn("[*] Error fetching simulation status:", err);
    }
}

function updateSimulationUI(status) {
    const badge = document.getElementById("sim-status-badge");
    const btnStart = document.getElementById("btn-start-sim");
    const btnStop = document.getElementById("btn-stop-sim");

    if (status.running) {
        badge.className = "sim-badge active";
        badge.innerHTML = `<span class="badge-dot"></span> Simulating ${status.active_viewers} Viewers (${status.events_per_second} eps)`;
        btnStart.classList.add("hidden");
        btnStop.classList.remove("hidden");
    } else {
        badge.className = "sim-badge idle";
        badge.innerHTML = `<span class="badge-dot"></span> Simulator Idle`;
        btnStart.classList.remove("hidden");
        btnStop.classList.add("hidden");
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
    setInterval(checkSystemHealth, 10000);
    
    // Start real-time analytics polling (every 1s)
    fetchRealtimeAnalytics();
    fetchSimulationStatus();
    setInterval(fetchRealtimeAnalytics, 1000);
    setInterval(fetchSimulationStatus, 3000);

    // Video Player & Quality Switch Controls
    const playerVideo = document.getElementById("video-player");

    document.getElementById("btn-close-player").addEventListener("click", () => {
        stopTelemetryHeartbeat();
        emitTelemetryEvent("ended");
        playerVideo.pause();
        document.getElementById("video-player-card").classList.add("hidden");
    });
    
    document.getElementById("btn-quality-720p").addEventListener("click", () => {
        switchResolution("720p");
    });
    document.getElementById("btn-quality-480p").addEventListener("click", () => {
        switchResolution("480p");
    });

    // HTML5 Video Player Telemetry Event Listeners
    playerVideo.addEventListener("play", () => {
        startTelemetryHeartbeat();
        emitTelemetryEvent("playing");
    });

    playerVideo.addEventListener("pause", () => {
        emitTelemetryEvent("paused");
    });

    playerVideo.addEventListener("waiting", () => {
        emitTelemetryEvent("buffering");
    });

    playerVideo.addEventListener("seeking", () => {
        emitTelemetryEvent("seeking");
    });

    playerVideo.addEventListener("seeked", () => {
        emitTelemetryEvent(playerVideo.paused ? "paused" : "playing");
    });

    playerVideo.addEventListener("ended", () => {
        stopTelemetryHeartbeat();
        emitTelemetryEvent("ended");
    });

    // Simulation Preset buttons
    const presetButtons = document.querySelectorAll(".btn-preset");
    const simInput = document.getElementById("sim-viewer-input");
    presetButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            presetButtons.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            if (simInput) simInput.value = btn.getAttribute("data-viewers");
        });
    });

    // Start Simulation Button
    const btnStartSim = document.getElementById("btn-start-sim");
    if (btnStartSim) {
        btnStartSim.addEventListener("click", async () => {
            const viewers = parseInt(simInput ? simInput.value : 50, 10) || 50;
            btnStartSim.disabled = true;
            try {
                const res = await fetch(`${API_BASE_URL}/analytics/simulation/start`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ viewers: viewers, duration_seconds: 60 })
                });
                await res.json();
                fetchSimulationStatus();
                fetchRealtimeAnalytics();
            } catch (err) {
                console.error("Failed to start simulation:", err);
            } finally {
                btnStartSim.disabled = false;
            }
        });
    }

    // Stop Simulation Button
    const btnStopSim = document.getElementById("btn-stop-sim");
    if (btnStopSim) {
        btnStopSim.addEventListener("click", async () => {
            btnStopSim.disabled = true;
            try {
                await fetch(`${API_BASE_URL}/analytics/simulation/stop`, { method: "POST" });
                fetchSimulationStatus();
                fetchRealtimeAnalytics();
            } catch (err) {
                console.error("Failed to stop simulation:", err);
            } finally {
                btnStopSim.disabled = false;
            }
        });
    }

    // ========================================================
    // QoS Reports Event Listeners
    // ========================================================
    const timeRangeButtons = document.querySelectorAll(".btn-time-range");
    timeRangeButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            timeRangeButtons.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            fetchReportsData();
        });
    });

    const reportVideoSelect = document.getElementById("report-video-filter");
    if (reportVideoSelect) {
        reportVideoSelect.addEventListener("change", () => {
            fetchReportsData();
        });
    }

    const btnRefreshReports = document.getElementById("btn-refresh-reports");
    if (btnRefreshReports) {
        btnRefreshReports.addEventListener("click", () => {
            fetchReportsData();
        });
    }

    const btnExportCsv = document.getElementById("btn-export-csv");
    if (btnExportCsv) {
        btnExportCsv.addEventListener("click", () => {
            const { startTime, videoId } = getActiveReportTimeParams();
            const exportParams = new URLSearchParams();
            exportParams.append("format", "csv");
            if (startTime) exportParams.append("start_time", startTime);
            if (videoId) exportParams.append("video_id", videoId);
            window.open(`${API_BASE_URL}/analytics/historical/export?${exportParams.toString()}`, "_blank");
        });
    }
});

// ========================================================
// QoS Reports & Historical Analytics Controller
// ========================================================

function getActiveReportTimeParams() {
    const activeRangeBtn = document.querySelector(".btn-time-range.active");
    const range = activeRangeBtn ? activeRangeBtn.getAttribute("data-range") : "15m";
    const now = Date.now() / 1000;
    
    let startTime = null;
    if (range === "15m") startTime = now - 900;
    else if (range === "1h") startTime = now - 3600;
    else if (range === "24h") startTime = now - 86400;
    
    const videoFilter = document.getElementById("report-video-filter");
    const videoId = videoFilter ? videoFilter.value : "";
    
    return { startTime, videoId };
}

async function fetchReportsData() {
    const reportsView = document.getElementById("view-reports");
    if (!reportsView || !reportsView.classList.contains("active")) {
        return;
    }

    const { startTime, videoId } = getActiveReportTimeParams();
    const queryParams = new URLSearchParams();
    if (startTime) queryParams.append("start_time", startTime);
    if (videoId) queryParams.append("video_id", videoId);

    try {
        // 1. Fetch Summary Scorecard
        const resSummary = await fetch(`${API_BASE_URL}/analytics/historical/summary?${queryParams.toString()}`);
        if (resSummary.ok) {
            const sumData = await resSummary.json();
            const wHours = document.getElementById("report-stat-watch-hours");
            const uViewers = document.getElementById("report-stat-unique-viewers");
            const sRate = document.getElementById("report-stat-stall-rate");
            const aBuffer = document.getElementById("report-stat-avg-buffer");

            if (wHours) wHours.innerText = `${(sumData.total_watch_time_hours || 0).toFixed(1)}h`;
            if (uViewers) uViewers.innerText = (sumData.unique_viewers || 0).toLocaleString();
            if (sRate) sRate.innerText = `${(sumData.rebuffer_stall_rate_percent || 0).toFixed(1)}%`;
            if (aBuffer) aBuffer.innerText = `${(sumData.avg_buffer_health_seconds || 0).toFixed(1)}s`;
        }

        // 2. Fetch Quality Breakdown
        const resQuality = await fetch(`${API_BASE_URL}/analytics/historical/breakdown?dimension=playback_quality&${queryParams.toString()}`);
        if (resQuality.ok) {
            const qList = await resQuality.json();
            const qBody = document.getElementById("report-quality-table-body");
            if (qBody) {
                if (qList.length === 0) {
                    qBody.innerHTML = `<tr><td colspan="5" class="empty-message">No telemetry records in selected window.</td></tr>`;
                } else {
                    qBody.innerHTML = qList.map(item => `
                        <tr>
                            <td><span class="badge-pill badge-purple">${item.dimension_value}</span></td>
                            <td>${item.event_count.toLocaleString()}</td>
                            <td><strong>${item.share_percentage}%</strong></td>
                            <td>${item.avg_buffer_health}s</td>
                            <td>${item.stall_rate_percent}%</td>
                        </tr>
                    `).join("");
                }
            }
        }

        // 3. Fetch Device Breakdown
        const resDevice = await fetch(`${API_BASE_URL}/analytics/historical/breakdown?dimension=device_type&${queryParams.toString()}`);
        if (resDevice.ok) {
            const dList = await resDevice.json();
            const dBody = document.getElementById("report-device-table-body");
            if (dBody) {
                if (dList.length === 0) {
                    dBody.innerHTML = `<tr><td colspan="5" class="empty-message">No device records in selected window.</td></tr>`;
                } else {
                    dBody.innerHTML = dList.map(item => `
                        <tr>
                            <td><span class="badge-pill badge-cyan">${item.dimension_value}</span></td>
                            <td>${item.event_count.toLocaleString()}</td>
                            <td>${item.unique_viewers.toLocaleString()}</td>
                            <td>${item.avg_buffer_health}s</td>
                            <td><strong>${item.share_percentage}%</strong></td>
                        </tr>
                    `).join("");
                }
            }
        }
    } catch (err) {
        console.error("Error fetching historical reports:", err);
    }
}

async function populateReportVideoFilter() {
    const select = document.getElementById("report-video-filter");
    if (!select) return;

    try {
        const res = await fetch(`${API_BASE_URL}/videos`);
        if (!res.ok) return;
        const videos = await res.json();
        
        const curVal = select.value;
        select.innerHTML = `<option value="">All Video Assets (${videos.length})</option>`;
        videos.forEach(v => {
            const opt = document.createElement("option");
            opt.value = v.video_id;
            opt.innerText = `${v.filename} (${v.video_id.substring(0, 8)})`;
            select.appendChild(opt);
        });
        select.value = curVal;
    } catch (err) {
        console.warn("Failed to populate report video filter:", err);
    }
}
