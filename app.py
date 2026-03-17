import os
import json
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
import requests
from PIL import Image
from io import BytesIO
import base64

app = Flask(__name__)

# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# Create uploads folder
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Hugging Face API
HF_API_TOKEN = os.getenv('HF_API_TOKEN', '')
HF_API_URL = "https://api-inference.huggingface.co/models/Salesforce/blip-image-captioning-base"

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_image_caption(image_path):
    """Call Hugging Face API to generate image caption"""
    try:
        with open(image_path, 'rb') as img_file:
            headers = {"Authorization": f"Bearer {HF_API_TOKEN}"}
            files = {"data": img_file}
            response = requests.post(HF_API_URL, headers=headers, files=files)
            
            if response.status_code == 200:
                result = response.json()
                # API returns list of captions, get the first one
                if isinstance(result, list) and len(result) > 0:
                    return result[0].get('generated_text', 'No caption generated')
                return 'Unable to generate caption'
            else:
                return f'Error: {response.status_code}'
    except Exception as e:
        return f'Error generating caption: {str(e)}'

@app.route('/')
def index():
    """Main gallery page"""
    return render_template('index.html')

@app.route('/api/albums', methods=['GET'])
def get_albums():
    """Get all albums"""
    albums = {}
    for folder in os.listdir(UPLOAD_FOLDER):
        folder_path = os.path.join(UPLOAD_FOLDER, folder)
        if os.path.isdir(folder_path):
            images = [f for f in os.listdir(folder_path) if allowed_file(f)]
            albums[folder] = {
                'name': folder,
                'image_count': len(images),
                'images': images[:1]  # Show first image as thumbnail
            }
    return jsonify(albums)

@app.route('/api/albums/<album_name>', methods=['GET'])
def get_album_images(album_name):
    """Get all images in an album"""
    album_path = os.path.join(UPLOAD_FOLDER, secure_filename(album_name))
    
    if not os.path.exists(album_path):
        return jsonify({'error': 'Album not found'}), 404
    
    images = []
    for filename in os.listdir(album_path):
        if allowed_file(filename):
            img_data = {
                'filename': filename,
                'url': f'/uploads/{album_name}/{filename}'
            }
            images.append(img_data)
    
    return jsonify({'album': album_name, 'images': images})

@app.route('/api/caption', methods=['POST'])
def generate_caption():
    """Generate caption for an image"""
    data = request.json
    image_url = data.get('image_url')
    
    if not image_url:
        return jsonify({'error': 'No image URL provided'}), 400
    
    try:
        # Handle local file paths
        if image_url.startswith('/uploads/'):
            file_path = image_url.lstrip('/')
            caption = get_image_caption(file_path)
        else:
            # Handle external URLs
            response = requests.get(image_url, timeout=10)
            img = Image.open(BytesIO(response.content))
            
            # Save temporarily
            temp_path = 'temp_image.jpg'
            img.save(temp_path)
            caption = get_image_caption(temp_path)
            os.remove(temp_path)
        
        return jsonify({'caption': caption})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/upload', methods=['POST'])
def upload_images():
    """Upload images to an album"""
    album_name = request.form.get('album')
    
    if not album_name:
        return jsonify({'error': 'Album name required'}), 400
    
    album_name = secure_filename(album_name)
    album_path = os.path.join(UPLOAD_FOLDER, album_name)
    os.makedirs(album_path, exist_ok=True)
    
    uploaded_files = []
    
    if 'files' not in request.files:
        return jsonify({'error': 'No files provided'}), 400
    
    files = request.files.getlist('files')
    
    for file in files:
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(album_path, filename)
            
            # Avoid duplicates
            if os.path.exists(filepath):
                base, ext = os.path.splitext(filename)
                counter = 1
                while os.path.exists(os.path.join(album_path, f"{base}_{counter}{ext}")):
                    counter += 1
                filename = f"{base}_{counter}{ext}"
                filepath = os.path.join(album_path, filename)
            
            file.save(filepath)
            uploaded_files.append(filename)
    
    return jsonify({
        'success': True,
        'album': album_name,
        'uploaded': uploaded_files
    })

@app.route('/uploads/<album>/<filename>')
def serve_image(album, filename):
    """Serve uploaded image"""
    album = secure_filename(album)
    filename = secure_filename(filename)
    filepath = os.path.join(UPLOAD_FOLDER, album, filename)
    
    if not os.path.exists(filepath):
        return 'Not found', 404
    
    return send_file(filepath)

if __name__ == '__main__':
    app.run(debug=True)