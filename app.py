from flask import Flask, render_template, request, jsonify, send_file, url_for
import yt_dlp
import os
import json
import uuid
from urllib.parse import urlparse
import re

app = Flask(__name__)

# Create necessary directories
os.makedirs('uploads', exist_ok=True)
os.makedirs('outputs', exist_ok=True)
os.makedirs('static', exist_ok=True)
os.makedirs('templates', exist_ok=True)

# Global variable to store video info
video_cache = {}

def is_valid_tiktok_url(url):
    """Validate if the URL is a valid TikTok URL"""
    tiktok_patterns = [
        r'https?://(?:www\.)?tiktok\.com/@[\w.-]+/video/\d+',
        r'https?://(?:vm|vt)\.tiktok\.com/[\w.-]+',
        r'https?://(?:www\.)?tiktok\.com/t/[\w.-]+',
        # r'https?://(?:www\.)?tiktok\.com/t/[\w.-]+',
        r'https?://vm\.tiktok\.com/v/\d+\.html'
    ]
    
    for pattern in tiktok_patterns:
        if re.match(pattern, url):
            return True
    return False

def get_video_info(url):
    """Extract video information using yt-dlp"""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extractaudio': False,
            'format': 'best',
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Extract relevant information
            video_data = {
                'id': info.get('id', ''),
                'title': info.get('title', 'Unknown Title'),
                'thumbnail': info.get('thumbnail', ''),
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader', 'Unknown'),
                'view_count': info.get('view_count', 0),
                'like_count': info.get('like_count', 0),
                'formats': []
            }
            
            # Process available formats
            if 'formats' in info:
                seen_qualities = set()
                for fmt in info['formats']:
                    if fmt.get('vcodec') != 'none':  # Video formats only
                        quality = fmt.get('height', 0)
                        if quality and quality not in seen_qualities:
                            video_data['formats'].append({
                                'format_id': fmt['format_id'],
                                'quality': f"{quality}p",
                                'ext': fmt.get('ext', 'mp4'),
                                'filesize': fmt.get('filesize', 0)
                            })
                            seen_qualities.add(quality)
                
                # Sort formats by quality (highest first)
                video_data['formats'].sort(key=lambda x: int(x['quality'][:-1]), reverse=True)
            
            # Add audio-only option
            video_data['formats'].append({
                'format_id': 'bestaudio',
                'quality': 'Audio Only',
                'ext': 'mp3',
                'filesize': 0
            })
            
            return video_data
            
    except Exception as e:
        raise Exception(f"Failed to extract video info: {str(e)}")

def download_video(url, format_id, video_id):
    """Download video with specified format"""
    try:
        output_path = os.path.join('outputs', f"{video_id}")
        
        ydl_opts = {
            'format': format_id,
            'outtmpl': f'{output_path}.%(ext)s',
            'quiet': True,
            'no_warnings': True,
        }
        
        # Special handling for audio-only downloads
        if format_id == 'bestaudio':
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
        # Find the downloaded file
        for file in os.listdir('outputs'):
            if file.startswith(video_id):
                return os.path.join('outputs', file)
                
        raise Exception("Downloaded file not found")
        
    except Exception as e:
        raise Exception(f"Download failed: {str(e)}")

@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')

@app.route('/extract', methods=['POST'])
def extract_video_info():
    """Extract video information from URL"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        
        if not url:
            return jsonify({'error': 'Please provide a URL'}), 400
            
        if not is_valid_tiktok_url(url):
            return jsonify({'error': 'Please provide a valid TikTok URL'}), 400
        
        # Extract video info
        video_info = get_video_info(url)
        
        # Generate unique session ID
        session_id = str(uuid.uuid4())
        video_cache[session_id] = {
            'url': url,
            'info': video_info
        }
        
        return jsonify({
            'success': True,
            'session_id': session_id,
            'video_info': video_info
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download', methods=['POST'])
def download():
    """Download video with selected format"""
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        format_id = data.get('format_id')
        
        if not session_id or session_id not in video_cache:
            return jsonify({'error': 'Invalid session'}), 400
            
        if not format_id:
            return jsonify({'error': 'Please select a format'}), 400
        
        cached_data = video_cache[session_id]
        url = cached_data['url']
        video_info = cached_data['info']
        
        # Generate unique filename
        video_id = f"{video_info['id']}_{uuid.uuid4().hex[:8]}"
        
        # Download the video
        file_path = download_video(url, format_id, video_id)
        
        if not os.path.exists(file_path):
            return jsonify({'error': 'Download failed - file not found'}), 500
        
        # Get file info
        file_size = os.path.getsize(file_path)
        filename = os.path.basename(file_path)
        
        return jsonify({
            'success': True,
            'download_url': url_for('serve_file', filename=filename),
            'filename': filename,
            'file_size': file_size
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download/<filename>')
def serve_file(filename):
    """Serve downloaded files"""
    try:
        file_path = os.path.join('outputs', filename)
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True)
        else:
            return "File not found", 404
    except Exception as e:
        return f"Error serving file: {str(e)}", 500

@app.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    print("🚀 TikTok Downloader Server Starting...")
    print("📱 Open your browser and go to: http://localhost:5000")
    print("⚡ Make sure you have yt-dlp installed: pip install yt-dlp")
    app.run(debug=True, host='0.0.0.0', port=5000)






