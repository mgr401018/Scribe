import re
from PIL import Image
import os

def clean_tag(tag):
    # Remove special characters and convert to lowercase
    return re.sub(r'[^a-zA-Z0-9\s-]', '', tag).strip().lower()

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def process_cover_image(file, story_id, app):
    """Process and save cover image with proper dimensions."""
    # Create uploads directory if it doesn't exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Generate filename using only story ID
    filename = f"{story_id}.jpg"  # Always save as jpg for consistency
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    # Open and process image
    img = Image.open(file)
    
    # Convert to RGB if necessary
    if img.mode in ('RGBA', 'P'):
        img = img.convert('RGB')
    
    # Calculate aspect ratios
    target_ratio = app.config['COVER_SIZE'][0] / app.config['COVER_SIZE'][1]
    img_ratio = img.width / img.height
    
    if img_ratio > target_ratio:
        # Image is wider than target ratio
        new_width = int(img.height * target_ratio)
        left = (img.width - new_width) // 2
        img = img.crop((left, 0, left + new_width, img.height))
    else:
        # Image is taller than target ratio
        new_height = int(img.width / target_ratio)
        top = (img.height - new_height) // 2
        img = img.crop((0, top, img.width, top + new_height))
    
    # Resize to target size
    img = img.resize(app.config['COVER_SIZE'], Image.Resampling.LANCZOS)
    
    # Save the processed image
    img.save(filepath, quality=95, optimize=True)
    
    return f"uploads/{filename}" 