import os
import yt_dlp
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import re
from urllib.parse import urlparse, parse_qs
import time
from datetime import datetime
import random
import uuid
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any
import threading


# Pydantic models for request bodies
class URLRequest(BaseModel):
    url: str


class DownloadRequest(BaseModel):
    session_id: str
    format_id: str


app = FastAPI(title="TikTok Downloader API")

# Setup templates and static files
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Create directories if not present
os.makedirs("uploads", exist_ok=True)
os.makedirs("outputs", exist_ok=True)
os.makedirs("static", exist_ok=True)
os.makedirs("templates", exist_ok=True)

# Video cache to store session data
video_cache = {}

# Job tracking for downloads
download_jobs: Dict[str, Dict[str, Any]] = {}
job_lock = threading.Lock()

# Thread pool for CPU-intensive operations
executor = ThreadPoolExecutor(max_workers=10)


def is_valid_tiktok_url(url):
    patterns = [
        r"https?://(?:www\.)?tiktok\.com/@[\w.-]+/video/\d+",
        r"https?://(?:vm|vt)\.tiktok\.com/[\w.-]+",
        r"https?://(?:www\.)?tiktok\.com/t/[\w.-]+",
        r"https?://vm\.tiktok\.com/v/\d+\.html",
    ]
    return any(re.match(pattern, url) for pattern in patterns)


def _get_video_info_sync(url):
    """Synchronous video info extraction - runs in thread pool"""
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "best",
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        video_data = {
            "id": info.get("id", ""),
            "title": info.get("title", "Unknown Title"),
            "thumbnail": info.get("thumbnail", ""),
            "duration": info.get("duration", 0),
            "uploader": info.get("uploader", "Unknown"),
            "view_count": info.get("view_count", 0),
            "like_count": info.get("like_count", 0),
            "formats": [],
        }

        seen = set()
        for fmt in info.get("formats", []):
            if fmt.get("vcodec") != "none":
                quality = fmt.get("height", 0)
                if quality and quality not in seen:
                    video_data["formats"].append(
                        {
                            "format_id": fmt["format_id"],
                            "quality": f"{quality}p",
                            "ext": fmt.get("ext", "mp4"),
                            "filesize": fmt.get("filesize", 0),
                        }
                    )
                    seen.add(quality)

        video_data["formats"].sort(key=lambda x: int(x["quality"][:-1]), reverse=True)

        # Add mp3 format manually (audio conversion)
        video_data["formats"].append(
            {
                "format_id": "extractaudio",
                "quality": "Audio Only (mp3)",
                "ext": "mp3",
                "filesize": 0,
            }
        )

        return video_data


async def get_video_info(url):
    """Async wrapper for video info extraction"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, _get_video_info_sync, url)


def _download_video_sync(url, format_id, video_id, job_id):
    """Synchronous video download - runs in background"""
    try:
        # Update job status
        with job_lock:
            download_jobs[job_id]["status"] = "downloading"
            download_jobs[job_id]["progress"] = 0

        output_path = os.path.join("outputs", f"{video_id}")
        ydl_opts = {
            "outtmpl": f"{output_path}.%(ext)s",
            "quiet": True,
            "no_warnings": True,
        }

        if format_id == "extractaudio":
            # Convert to mp3 using FFmpeg
            ydl_opts["format"] = "bestaudio/best"
            ydl_opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ]
        else:
            ydl_opts["format"] = format_id

        # Add progress hook
        def progress_hook(d):
            if d["status"] == "downloading":
                try:
                    percent = d.get("_percent_str", "0%").replace("%", "")
                    progress = float(percent)
                    with job_lock:
                        if job_id in download_jobs:
                            download_jobs[job_id]["progress"] = progress
                except:
                    pass

        ydl_opts["progress_hooks"] = [progress_hook]

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # Find the downloaded file
        for file in os.listdir("outputs"):
            if file.startswith(video_id):
                file_path = os.path.join("outputs", file)
                file_size = os.path.getsize(file_path)

                # Update job status
                with job_lock:
                    download_jobs[job_id].update(
                        {
                            "status": "completed",
                            "progress": 100,
                            "file_path": file_path,
                            "filename": file,
                            "file_size": file_size,
                            "download_url": f"/download/{file}",
                        }
                    )
                return

        # If no file found
        with job_lock:
            download_jobs[job_id].update(
                {"status": "failed", "error": "Downloaded file not found"}
            )

    except Exception as e:
        with job_lock:
            download_jobs[job_id].update({"status": "failed", "error": str(e)})


async def download_video_async(url, format_id, video_id, job_id):
    """Async wrapper for video download"""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        executor, _download_video_sync, url, format_id, video_id, job_id
    )


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main page"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/extract")
async def extract_video_info(request_data: URLRequest):
    """Extract video information from URL - Now async and non-blocking"""
    try:
        url = request_data.url.strip()

        if not url:
            raise HTTPException(status_code=400, detail="Please provide a URL")

        if not is_valid_tiktok_url(url):
            raise HTTPException(
                status_code=400, detail="Please provide a valid TikTok URL"
            )

        # Run video info extraction in thread pool (non-blocking)
        video_info = await get_video_info(url)

        session_id = str(uuid.uuid4())
        video_cache[session_id] = {"url": url, "info": video_info}

        return {"success": True, "session_id": session_id, "video_info": video_info}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/download")
async def download(request_data: DownloadRequest, background_tasks: BackgroundTasks):
    """Start download process - Returns immediately with job ID"""
    try:
        session_id = request_data.session_id
        format_id = request_data.format_id

        if not session_id or session_id not in video_cache:
            raise HTTPException(status_code=400, detail="Invalid session")

        if not format_id:
            raise HTTPException(status_code=400, detail="Please select a format")

        cached_data = video_cache[session_id]
        url = cached_data["url"]
        video_info = cached_data["info"]

        video_id = f"{video_info['id']}_{uuid.uuid4().hex[:8]}"
        job_id = str(uuid.uuid4())

        # Initialize job tracking
        with job_lock:
            download_jobs[job_id] = {
                "status": "queued",
                "progress": 0,
                "video_id": video_id,
                "video_title": video_info.get("title", "Unknown"),
                "created_at": datetime.now().isoformat(),
            }

        # Start download in background
        background_tasks.add_task(
            download_video_async, url, format_id, video_id, job_id
        )

        # Return immediately with job ID
        return {
            "success": True,
            "job_id": job_id,
            "message": "Download started. Use /status/{job_id} to check progress.",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/status/{job_id}")
async def get_download_status(job_id: str):
    """Check download status and progress"""
    with job_lock:
        if job_id not in download_jobs:
            raise HTTPException(status_code=404, detail="Job not found")

        job_data = download_jobs[job_id].copy()

    return {"success": True, "job_id": job_id, **job_data}


# @app.get("/download/{filename}")
# async def serve_file(filename: str):
#     """Serve downloaded files"""
#     try:
#         file_path = os.path.join('outputs', filename)
#         if os.path.exists(file_path):
#             return FileResponse(file_path, filename=filename)
#         else:
#             raise HTTPException(status_code=404, detail="File not found")
#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error serving file: {str(e)}")


@app.get("/download/{filename}")
async def serve_file(filename: str):
    """Serve downloaded file and delete it immediately after sending"""
    try:
        file_path = os.path.join("outputs", filename)
        if os.path.exists(file_path):
            response = FileResponse(file_path, filename=filename)

            # Background task to delete file after sending
            def delete_after_response():
                time.sleep(1)  # slight delay to ensure file is sent
                if os.path.exists(file_path):
                    os.remove(file_path)

            threading.Thread(target=delete_after_response).start()

            return response
        else:
            raise HTTPException(status_code=404, detail="File not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error serving file: {str(e)}")


@app.delete("/cleanup/{job_id}")
async def cleanup_job(job_id: str):
    """Clean up completed job data"""
    with job_lock:
        if job_id in download_jobs:
            job_data = download_jobs[job_id]
            if job_data.get("status") in ["completed", "failed"]:
                # Optionally delete the file
                if "file_path" in job_data and os.path.exists(job_data["file_path"]):
                    os.remove(job_data["file_path"])
                del download_jobs[job_id]
                return {"success": True, "message": "Job cleaned up"}
            else:
                raise HTTPException(status_code=400, detail="Job is still active")
        else:
            raise HTTPException(status_code=404, detail="Job not found")


@app.get("/jobs")
async def list_active_jobs():
    """List all active download jobs"""
    with job_lock:
        jobs = {job_id: job_data for job_id, job_data in download_jobs.items()}

    return {"success": True, "active_jobs": len(jobs), "jobs": jobs}


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "OK",
        "message": "TikTok Downloader API is running",
        "active_downloads": len(download_jobs),
        "thread_pool_size": executor._max_workers,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=5005, reload=True)
