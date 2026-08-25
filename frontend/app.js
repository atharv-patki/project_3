// --- AetherStream Frontend Application Logic ---

const API_BASE_URL = "http://127.0.0.1:5000/api";

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
}

// Attach Nav Event Listeners
navItems.forEach(item => {
    item.addEventListener("click", (e) => {
        e.preventDefault();
        switchView(item.id);
        
        // Update URL hash without jumping
        const hash = item.getAttribute("href");
        history.pushState(null, null, hash);
    });
});

// Handle browser back/forward buttons
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

    try {
        const response = await fetch(`${API_BASE_URL}/health`);
        if (!response.ok) throw new Error("API responds with error status.");
        
        const data = await response.json();
        
        // System Online Status Update
        indicator.className = "status-indicator online";
        statusText.innerText = "Backend Online";
        
        // Node Status Details Update
        nodeStatus.innerHTML = `<span style="color: var(--accent-green)">Online</span> (${(data.max_file_size_bytes / (1024*1024)).toFixed(0)}MB limit)`;
        
        return true;
    } catch (error) {
        console.error("Health check error:", error);
        
        indicator.className = "status-indicator offline";
        statusText.innerText = "Backend Offline";
        nodeStatus.innerHTML = `<span style="color: var(--accent-red)">Offline</span> (Connection failed)`;
        
        return false;
    }
}

// Drag & Drop Basic Interface Events
const dropZone = document.getElementById("drop-zone");
const fileInput = document.getElementById("file-input");
const filePanel = document.getElementById("file-panel");
const fileNameLabel = document.getElementById("file-name");
const fileSizeLabel = document.getElementById("file-size");
const btnCancelFile = document.getElementById("btn-cancel-file");

// Trigger file input open
dropZone.addEventListener("click", () => {
    fileInput.click();
});

// Drag Enter / Over
['dragenter', 'dragover'].forEach(eventName => {
    dropZone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropZone.classList.add('dragover');
    }, false);
});

// Drag Leave
['dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropZone.classList.remove('dragover');
    }, false);
});

// Handle File Drop
dropZone.addEventListener('drop', (e) => {
    const dt = e.dataTransfer;
    const files = dt.files;
    if (files.length > 0) {
        handleFileSelection(files[0]);
    }
});

// Handle File Browse Selection
fileInput.addEventListener('change', () => {
    if (fileInput.files.length > 0) {
        handleFileSelection(fileInput.files[0]);
    }
});

let selectedFile = null;

function handleFileSelection(file) {
    selectedFile = file;
    
    // Display file stats
    fileNameLabel.innerText = file.name;
    const sizeInMB = (file.size / (1024 * 1024)).toFixed(2);
    fileSizeLabel.innerText = `${sizeInMB} MB`;
    
    // Show panel, hide drop zone
    dropZone.classList.add("hidden");
    filePanel.classList.remove("hidden");
    
    // Reset any previous upload session UI state
    document.getElementById("progress-section").classList.add("hidden");
    document.getElementById("btn-start-upload").classList.remove("hidden");
    document.getElementById("btn-pause-upload").classList.add("hidden");
}

// Cancel selected file
btnCancelFile.addEventListener("click", () => {
    selectedFile = null;
    fileInput.value = "";
    
    // Reset panels
    dropZone.classList.remove("hidden");
    filePanel.classList.add("hidden");
});

// Initial Setup on Page Load
document.addEventListener("DOMContentLoaded", () => {
    // Navigate based on initial hash or fallback
    const hash = window.location.hash || "#dashboard";
    const matchingNav = Array.from(navItems).find(item => item.getAttribute("href") === hash);
    if (matchingNav) {
        switchView(matchingNav.id);
    }
    
    // Initialize Health checks and set poll interval (every 10 seconds)
    checkSystemHealth();
    setInterval(checkSystemHealth, 10000);
});
