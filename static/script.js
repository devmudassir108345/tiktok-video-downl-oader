// Global variables
let currentSessionId = null;
let selectedFormat = null;
let currentJobId = null;
let statusCheckInterval = null;

// DOM elements
const videoUrlInput = document.getElementById("videoUrl");
const extractBtn = document.getElementById("extractBtn");
const loadingSection = document.getElementById("loadingSection");
const videoInfoSection = document.getElementById("videoInfoSection");
const downloadSection = document.getElementById("downloadSection");
const downloadCompleteSection = document.getElementById(
  "downloadCompleteSection"
);
const errorSection = document.getElementById("errorSection");
const downloadBtn = document.getElementById("downloadBtn");
const formatList = document.getElementById("formatList");
const downloadLink = document.getElementById("downloadLink");
const downloadAnotherBtn = document.getElementById("downloadAnotherBtn");
const retryBtn = document.getElementById("retryBtn");
const errorMessage = document.getElementById("errorMessage");

// Job status elements
const jobStatus = document.getElementById("jobStatus");
const jobIdElement = document.getElementById("jobId");
const videoTitle2 = document.getElementById("videoTitle2");

// Event listeners
extractBtn.addEventListener("click", extractVideoInfo);
downloadBtn.addEventListener("click", downloadVideo);
downloadAnotherBtn.addEventListener("click", resetForm);
retryBtn.addEventListener("click", resetForm);
videoUrlInput.addEventListener("keypress", (e) => {
  if (e.key === "Enter") extractVideoInfo();
});

// Show section function
function showSection(section) {
  const sections = [
    loadingSection,
    videoInfoSection,
    downloadSection,
    downloadCompleteSection,
    errorSection,
  ];
  sections.forEach((s) => s.classList.add("hidden"));
  section.classList.remove("hidden");
}

// Show error function
function showError(message) {
  errorMessage.textContent = message;
  showSection(errorSection);
  clearStatusCheck();
}

// Clear status check interval
function clearStatusCheck() {
  if (statusCheckInterval) {
    clearInterval(statusCheckInterval);
    statusCheckInterval = null;
  }
}

// Format file size
function formatFileSize(bytes) {
  if (bytes === 0) return "Unknown size";
  const k = 1024;
  const sizes = ["Bytes", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
}

// Format duration
function formatDuration(seconds) {
  if (!seconds) return "0:00";
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

// Format number
function formatNumber(num) {
  if (num >= 1000000) return (num / 1000000).toFixed(1) + "M";
  if (num >= 1000) return (num / 1000).toFixed(1) + "K";
  return num.toString();
}

// Update job status badge
function updateJobStatus(status) {
  const statusConfig = {
    queued: { icon: "fa-clock", text: "Queued", class: "queued" },
    downloading: {
      icon: "fa-download",
      text: "Downloading",
      class: "downloading",
    },
    completed: { icon: "fa-check", text: "Completed", class: "completed" },
    failed: { icon: "fa-times", text: "Failed", class: "failed" },
  };

  const config = statusConfig[status] || statusConfig.queued;
  jobStatus.className = `job-status ${config.class}`;
  jobStatus.innerHTML = `<i class="fas ${config.icon}"></i><span>${config.text}</span>`;
}

// Extract video info
async function extractVideoInfo() {
  const url = videoUrlInput.value.trim();
  if (!url) {
    showError("Please enter a TikTok video URL");
    return;
  }

  // Validate TikTok URL
  const tiktokRegex =
    /^https?:\/\/(www\.)?(tiktok\.com|vm\.tiktok\.com|vt\.tiktok\.com|m\.tiktok\.com)/;
  if (!tiktokRegex.test(url)) {
    showError("Please enter a valid TikTok URL");
    return;
  }

  showSection(loadingSection);
  animateExtractProgress();
  extractBtn.disabled = true;

  try {
    const response = await fetch("/extract", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ url: url }),
    });

    const data = await response.json();

    if (response.ok && data.success) {
      currentSessionId = data.session_id;
      displayVideoInfo(data.video_info);
    } else {
      showError(
        data.error || data.detail || "Failed to extract video information"
      );
    }
  } catch (error) {
    console.error("Network error:", error);
    showError("Network error. Please check your connection and try again.");
  } finally {
    extractBtn.disabled = false;
  }
}

// Display video info
function displayVideoInfo(videoInfo) {
  // Update video details with error handling for thumbnail
  const thumbnailImg = document.getElementById("videoThumbnail");
  thumbnailImg.src =
    videoInfo.thumbnail ||
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='300' height='200' viewBox='0 0 300 200'%3E%3Crect width='300' height='200' fill='%23f0f0f0'/%3E%3Ctext x='50%25' y='50%25' font-size='14' text-anchor='middle' dy='.3em' fill='%23999'%3ENo Thumbnail%3C/text%3E%3C/svg%3E";
  thumbnailImg.onerror = function () {
    this.src =
      "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='300' height='200' viewBox='0 0 300 200'%3E%3Crect width='300' height='200' fill='%23f0f0f0'/%3E%3Ctext x='50%25' y='50%25' font-size='14' text-anchor='middle' dy='.3em' fill='%23999'%3ENo Thumbnail%3C/text%3E%3C/svg%3E";
  };

  document.getElementById("videoTitle").textContent =
    videoInfo.title || "TikTok Video";
  document.getElementById(
    "videoUploader"
  ).innerHTML = `<i class="fas fa-user"></i> ${
    videoInfo.uploader || "Unknown"
  }`;
  document.getElementById(
    "videoDuration"
  ).innerHTML = `<i class="fas fa-clock"></i> ${formatDuration(
    videoInfo.duration
  )}`;
  document.getElementById(
    "videoViews"
  ).innerHTML = `<i class="fas fa-eye"></i> ${formatNumber(
    videoInfo.view_count || 0
  )} views`;
  document.getElementById(
    "videoLikes"
  ).innerHTML = `<i class="fas fa-heart"></i> ${formatNumber(
    videoInfo.like_count || 0
  )} likes`;

  // Populate format list
  formatList.innerHTML = "";
  if (!videoInfo.formats || videoInfo.formats.length === 0) {
    formatList.innerHTML =
      '<p style="color: #666; text-align: center; padding: 20px;">No formats available for this video.</p>';
    return;
  }

  videoInfo.formats.forEach((format, index) => {
    const formatItem = document.createElement("div");
    formatItem.className = "format-item";

    // Special handling for audio format
    const isAudio =
      format.quality.includes("Audio Only") || format.ext === "mp3";
    const icon = isAudio ? "fa-music" : "fa-video";
    const qualityDisplay = format.quality;

    formatItem.innerHTML = `
            <div class="format-info">
              <span class="format-quality">${qualityDisplay}</span>
              <span class="format-type">${format.ext.toUpperCase()}</span>
              ${
                format.filesize
                  ? `<span class="format-size">${formatFileSize(
                      format.filesize
                    )}</span>`
                  : ""
              }
            </div>
            <div class="format-icon">
              <i class="fas ${icon}"></i>
            </div>
          `;

    formatItem.addEventListener("click", () =>
      selectFormat(format, formatItem)
    );
    formatList.appendChild(formatItem);
  });

  showSection(videoInfoSection);
}

// Select format
function selectFormat(format, element) {
  // Remove previous selection
  document.querySelectorAll(".format-item").forEach((item) => {
    item.classList.remove("selected");
  });

  // Add selection to clicked item
  element.classList.add("selected");
  selectedFormat = format;

  // Enable download button
  downloadBtn.classList.remove("disabled");
  downloadBtn.innerHTML = `
          <i class="fas fa-download"></i>
          <span>Download ${format.quality} (${format.ext.toUpperCase()})</span>
        `;
}

// Download video - Updated for new async backend
async function downloadVideo() {
  if (!selectedFormat || !currentSessionId) {
    showError("Please select a format first");
    return;
  }

  showSection(downloadSection);
  updateJobStatus("queued");

  try {
    // Start download (returns immediately with job ID)
    const response = await fetch("/download", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        session_id: currentSessionId,
        format_id: selectedFormat.format_id,
      }),
    });

    const data = await response.json();

    if (response.ok && data.success) {
      currentJobId = data.job_id;
      jobIdElement.textContent = `Job ID: ${currentJobId.substring(0, 8)}...`;

      // Start polling for status
      startStatusCheck();
    } else {
      showError(data.error || data.detail || "Failed to start download");
    }
  } catch (error) {
    console.error("Download error:", error);
    showError("Network error during download. Please try again.");
  }
}

// Start status checking
function startStatusCheck() {
  if (!currentJobId) return;

  statusCheckInterval = setInterval(async () => {
    try {
      const response = await fetch(`/status/${currentJobId}`);
      const data = await response.json();

      if (response.ok && data.success) {
        updateDownloadProgress(data);

        if (data.status === "completed") {
          clearStatusCheck();
          showDownloadComplete(data);
        } else if (data.status === "failed") {
          clearStatusCheck();
          showError(data.error || "Download failed");
        }
      } else {
        clearStatusCheck();
        showError("Failed to check download status");
      }
    } catch (error) {
      console.error("Status check error:", error);
      clearStatusCheck();
      showError("Network error while checking status");
    }
  }, 1000); // Check every second
}

// Update download progress
function updateDownloadProgress(jobData) {
  const { status, progress = 0, video_title } = jobData;

  // Update job status badge
  updateJobStatus(status);

  // Update progress displays
  const progressPercent = Math.floor(progress);

  // Update circular progress
  const circumference = 2 * Math.PI * 50;
  const offset = circumference - (progress / 100) * circumference;
  document.getElementById("downloadProgressCircle").style.strokeDashoffset =
    offset;
  document.getElementById("downloadCircularProgress").textContent =
    progressPercent + "%";

  // Update progress bar
  document.getElementById("downloadProgressFill").style.width = progress + "%";
  document.getElementById("downloadProgressPercentage").textContent =
    progressPercent + "%";

  // Update text based on status
  const statusTexts = {
    queued: "Queued for download",
    downloading: "Downloading video",
    completed: "Download complete",
  };

  const statusDetails = {
    queued: "Your download is in the queue...",
    downloading: "Your TikTok video is being downloaded...",
    completed: "Your video has been downloaded successfully!",
  };

  document.getElementById("downloadText").textContent =
    statusTexts[status] || "Processing";
  document.getElementById("downloadDetails").textContent =
    statusDetails[status] || "Processing your request...";
  document.getElementById("downloadProgressLabel").textContent =
    status.charAt(0).toUpperCase() + status.slice(1) + "...";

  // Update video title
  if (video_title) {
    videoTitle2.textContent = `Video: ${video_title.substring(0, 30)}...`;
  }
}

// Show download complete
function showDownloadComplete(jobData) {
  if (jobData.download_url) {
    downloadLink.href = jobData.download_url;
    downloadLink.download = jobData.filename || "tiktok_video";
  }
  showSection(downloadCompleteSection);
}

// Reset form
function resetForm() {
  videoUrlInput.value = "";
  currentSessionId = null;
  selectedFormat = null;
  currentJobId = null;
  clearStatusCheck();

  downloadBtn.classList.add("disabled");
  downloadBtn.innerHTML = `
          <i class="fas fa-download"></i>
          <span>Select a format to download</span>
        `;

  const sections = [
    loadingSection,
    videoInfoSection,
    downloadSection,
    downloadCompleteSection,
    errorSection,
  ];
  sections.forEach((s) => s.classList.add("hidden"));
}

// Auto-focus on URL input
videoUrlInput.focus();

// Enhanced progress animation for extraction
function animateExtractProgress() {
  const circularProgress = document.getElementById("circularProgress");
  const progressCircle = document.getElementById("progressCircle");
  const progressFill = document.getElementById("progressFill");
  const progressPercentage = document.getElementById("progressPercentage");
  const progressLabel = document.getElementById("progressLabel");
  const loadingDetails = document.getElementById("loadingDetails");

  let progress = 0;
  const duration = 2000; // 2 seconds for faster response
  const startTime = Date.now();

  // Progress stages with realistic timing
  const stages = [
    {
      progress: 20,
      label: "Connecting to TikTok...",
      details: "Establishing secure connection",
    },
    {
      progress: 50,
      label: "Fetching video data...",
      details: "Retrieving video information",
    },
    {
      progress: 80,
      label: "Processing formats...",
      details: "Analyzing available qualities",
    },
    {
      progress: 100,
      label: "Complete!",
      details: "Video information extracted successfully",
    },
  ];

  let currentStage = 0;

  const interval = setInterval(() => {
    const elapsed = Date.now() - startTime;
    progress = Math.min((elapsed / duration) * 100, 100);

    // Update stage based on progress
    while (
      currentStage < stages.length - 1 &&
      progress >= stages[currentStage + 1].progress
    ) {
      currentStage++;
      progressLabel.textContent = stages[currentStage].label;
      loadingDetails.textContent = stages[currentStage].details;
    }

    // Update circular progress
    const circumference = 2 * Math.PI * 50;
    const offset = circumference - (progress / 100) * circumference;
    progressCircle.style.strokeDashoffset = offset;
    circularProgress.textContent = Math.floor(progress) + "%";

    // Update progress bar
    progressFill.style.width = progress + "%";
    progressPercentage.textContent = Math.floor(progress) + "%";

    if (progress >= 100) {
      clearInterval(interval);
    }
  }, 50);
}

















