from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from ebooklib import epub
import io
import tempfile
import re
from datetime import datetime
from werkzeug.utils import secure_filename
from PIL import Image

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'postgresql://postgres:postgres@db:5432/scribe')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['COVER_SIZE'] = (512, 800)  # Width, Height
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Association table for Story-Tag many-to-many relationship
story_tags = db.Table('story_tags',
    db.Column('story_id', db.Integer, db.ForeignKey('story.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tag.id'), primary_key=True)
)

class Tag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    stories = db.relationship('Story', secondary=story_tags, backref=db.backref('tags', lazy=True))

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(512))
    about_me = db.Column(db.Text, nullable=True)
    stories = db.relationship('Story', backref='author', lazy=True)

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    cover_image = db.Column(db.String(255), nullable=True)  # Store image path
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    chapters = db.relationship('Chapter', backref='story', lazy=True, order_by='Chapter.chapter_number', cascade='all, delete-orphan')
    ratings = db.relationship('Rating', backref='story', lazy=True, cascade='all, delete-orphan')
    saved_by = db.relationship('SavedStory', backref=db.backref('story', lazy=True), lazy=True, cascade='all, delete-orphan')

    @property
    def word_count(self):
        total_words = 0
        for chapter in self.chapters:
            total_words += len(chapter.content.split())
        return total_words

    @property
    def average_rating(self):
        if not self.ratings:
            return 0
        return sum(rating.value for rating in self.ratings) / len(self.ratings)

class Chapter(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    chapter_number = db.Column(db.Integer, nullable=False)
    story_id = db.Column(db.Integer, db.ForeignKey('story.id'), nullable=False)

class Rating(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    story_id = db.Column(db.Integer, db.ForeignKey('story.id'), nullable=False)
    value = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref=db.backref('ratings', lazy=True))

    # Ensure a user can only rate a story once
    __table_args__ = (
        db.UniqueConstraint('user_id', 'story_id', name='unique_user_story_rating'),
    )

class SavedStory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    story_id = db.Column(db.Integer, db.ForeignKey('story.id'), nullable=False)
    saved_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref=db.backref('saved_stories', lazy=True))

    __table_args__ = (db.UniqueConstraint('user_id', 'story_id', name='unique_saved_story'),)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Create database tables
with app.app_context():
    db.create_all()

def clean_tag(tag):
    # Remove special characters and convert to lowercase
    return re.sub(r'[^a-zA-Z0-9\s-]', '', tag).strip().lower()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def process_cover_image(file, story_id):
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

@app.route('/')
def index():
    search_query = request.args.get('search', '')
    sort_option = request.args.get('sort')  # Remove default value
    page = request.args.get('page', 1, type=int)  # Get current page number
    per_page = 20  # Number of stories per page
    
    if search_query:
        query = Story.query
        
        # Handle multiple search modifiers
        title_query = None
        author_query = None
        tag_queries = []
        rating_query = None
        rating_more_than = None
        rating_less_than = None
        
        # Extract title search if present
        if 'title:' in search_query:
            title_part = search_query.split('title:', 1)[1]
            # Find the next modifier or end of string
            next_modifier = min(
                [i for i in [title_part.find(' by:'), title_part.find(' tags:'), 
                           title_part.find(' rating:'), title_part.find(' rating_more_than:'),
                           title_part.find(' rating_less_than:'), len(title_part)] if i != -1]
            )
            title_part = title_part[:next_modifier].strip()
            
            if title_part.startswith('"') and title_part.endswith('"'):
                title_query = title_part[1:-1]
        
        # Extract author search if present
        if 'by:' in search_query:
            author_part = search_query.split('by:', 1)[1]
            # Find the next modifier or end of string
            next_modifier = min(
                [i for i in [author_part.find(' title:'), author_part.find(' tags:'),
                           author_part.find(' rating:'), author_part.find(' rating_more_than:'),
                           author_part.find(' rating_less_than:'), len(author_part)] if i != -1]
            )
            author_part = author_part[:next_modifier].strip()
            
            if author_part.startswith('"') and author_part.endswith('"'):
                author_query = author_part[1:-1]
        
        # Extract tag search if present
        if 'tags:' in search_query:
            tag_part = search_query.split('tags:', 1)[1]
            # Find the next modifier or end of string
            next_modifier = min(
                [i for i in [tag_part.find(' title:'), tag_part.find(' by:'),
                           tag_part.find(' rating:'), tag_part.find(' rating_more_than:'),
                           tag_part.find(' rating_less_than:'), len(tag_part)] if i != -1]
            )
            tag_part = tag_part[:next_modifier].strip()
            
            if tag_part.startswith('"') and tag_part.endswith('"'):
                tag_queries = [clean_tag(tag) for tag in tag_part[1:-1].split(',') if tag.strip()]

        # Extract rating search if present
        if 'rating:' in search_query:
            rating_part = search_query.split('rating:', 1)[1]
            next_modifier = min(
                [i for i in [rating_part.find(' title:'), rating_part.find(' by:'),
                           rating_part.find(' tags:'), rating_part.find(' rating_more_than:'),
                           rating_part.find(' rating_less_than:'), len(rating_part)] if i != -1]
            )
            rating_part = rating_part[:next_modifier].strip()
            
            if rating_part.startswith('"') and rating_part.endswith('"'):
                try:
                    rating_query = float(rating_part[1:-1])
                except ValueError:
                    pass

        # Extract rating_more_than if present
        if 'rating_more_than:' in search_query:
            rating_part = search_query.split('rating_more_than:', 1)[1]
            next_modifier = min(
                [i for i in [rating_part.find(' title:'), rating_part.find(' by:'),
                           rating_part.find(' tags:'), rating_part.find(' rating:'),
                           rating_part.find(' rating_less_than:'), len(rating_part)] if i != -1]
            )
            rating_part = rating_part[:next_modifier].strip()
            
            if rating_part.startswith('"') and rating_part.endswith('"'):
                try:
                    rating_more_than = float(rating_part[1:-1])
                except ValueError:
                    pass

        # Extract rating_less_than if present
        if 'rating_less_than:' in search_query:
            rating_part = search_query.split('rating_less_than:', 1)[1]
            next_modifier = min(
                [i for i in [rating_part.find(' title:'), rating_part.find(' by:'),
                           rating_part.find(' tags:'), rating_part.find(' rating:'),
                           rating_part.find(' rating_more_than:'), len(rating_part)] if i != -1]
            )
            rating_part = rating_part[:next_modifier].strip()
            
            if rating_part.startswith('"') and rating_part.endswith('"'):
                try:
                    rating_less_than = float(rating_part[1:-1])
                except ValueError:
                    pass
        
        # Apply filters
        if title_query:
            query = query.filter(Story.title.ilike(f'%{title_query}%'))
        if author_query:
            query = query.join(User).filter(User.username.ilike(f'%{author_query}%'))
        if tag_queries:
            for tag_query in tag_queries:
                tag_subquery = db.session.query(story_tags.c.story_id).join(Tag).filter(Tag.name == tag_query).subquery()
                query = query.filter(Story.id.in_(tag_subquery))
        
        # Apply rating filters
        if rating_query is not None:
            rating_subquery = db.session.query(
                Rating.story_id,
                db.func.avg(Rating.value).label('avg_rating')
            ).group_by(Rating.story_id).having(db.func.avg(Rating.value) == rating_query).subquery()
            query = query.join(rating_subquery, Story.id == rating_subquery.c.story_id)
        
        if rating_more_than is not None:
            rating_subquery = db.session.query(
                Rating.story_id,
                db.func.avg(Rating.value).label('avg_rating')
            ).group_by(Rating.story_id).having(db.func.avg(Rating.value) > rating_more_than).subquery()
            query = query.join(rating_subquery, Story.id == rating_subquery.c.story_id)
        
        if rating_less_than is not None:
            rating_subquery = db.session.query(
                Rating.story_id,
                db.func.avg(Rating.value).label('avg_rating')
            ).group_by(Rating.story_id).having(db.func.avg(Rating.value) < rating_less_than).subquery()
            query = query.join(rating_subquery, Story.id == rating_subquery.c.story_id)
        
        # If no modifiers were used, search in both title and description
        if not title_query and not author_query and not tag_queries and rating_query is None and rating_more_than is None and rating_less_than is None:
            query = query.filter(
                (Story.title.ilike(f'%{search_query}%')) |
                (Story.description.ilike(f'%{search_query}%'))
            )
    else:
        query = Story.query
    
    # Apply sorting
    if sort_option == 'asc':
        # Sort by oldest first (id ascending)
        query = query.order_by(Story.id.asc())
    elif sort_option == 'words':
        # Sort by word count (requires a subquery to calculate word count)
        word_count_subquery = db.session.query(
            Story.id,
            db.func.sum(db.func.length(Chapter.content)).label('word_count')
        ).join(Chapter).group_by(Story.id).subquery()
        query = query.join(word_count_subquery, Story.id == word_count_subquery.c.id).order_by(word_count_subquery.c.word_count.desc())
    elif sort_option == 'chapters':
        # Sort by number of chapters
        chapter_count_subquery = db.session.query(
            Story.id,
            db.func.count(Chapter.id).label('chapter_count')
        ).join(Chapter).group_by(Story.id).subquery()
        query = query.join(chapter_count_subquery, Story.id == chapter_count_subquery.c.id).order_by(chapter_count_subquery.c.chapter_count.desc())
    elif sort_option == 'rating':
        # Sort by average rating
        rating_subquery = db.session.query(
            Rating.story_id,
            db.func.avg(Rating.value).label('avg_rating')
        ).group_by(Rating.story_id).subquery()
        query = query.outerjoin(rating_subquery, Story.id == rating_subquery.c.story_id).order_by(rating_subquery.c.avg_rating.desc().nullslast())
    elif sort_option == 'title':
        # Sort alphabetically by title
        query = query.order_by(Story.title.asc())
    elif sort_option == 'author':
        # Sort alphabetically by author username
        query = query.join(User).order_by(User.username.asc())
    else:  # No sort option specified
        # Default: sort by newest first (id descending)
        query = query.order_by(Story.id.desc())
    
    # Get total count for pagination
    total_stories = query.count()
    total_pages = (total_stories + per_page - 1) // per_page
    
    # Ensure page is within valid range
    page = max(1, min(page, total_pages)) if total_pages > 0 else 1
    
    # Get paginated stories
    stories = query.offset((page - 1) * per_page).limit(per_page).all()
    
    return render_template('index.html', 
                         stories=stories,
                         current_page=page,
                         total_pages=total_pages,
                         search_query=search_query,
                         sort_option=sort_option)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('index'))
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('register'))
        
        user = User(username=username, password_hash=generate_password_hash(password))
        db.session.add(user)
        db.session.commit()
        
        login_user(user)
        return redirect(url_for('index'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/profile')
@login_required
def profile():
    user = current_user
    page = request.args.get('page', 1, type=int)
    per_page = 10  # Number of stories per page
    
    # Get all stories for statistics
    all_stories = Story.query.filter_by(user_id=user.id).all()
    
    # Get paginated stories for display
    stories_query = Story.query.filter_by(user_id=user.id).order_by(Story.id.desc())
    total_stories = stories_query.count()
    total_pages = (total_stories + per_page - 1) // per_page
    
    # Ensure page is within valid range
    page = max(1, min(page, total_pages)) if total_pages > 0 else 1
    
    # Get paginated stories
    stories = stories_query.offset((page - 1) * per_page).limit(per_page).all()
    
    # Calculate statistics from all stories
    total_words = sum(story.word_count for story in all_stories)
    avg_words = total_words / total_stories if total_stories > 0 else 0
    
    # Calculate average rating across all stories
    total_ratings = 0
    rating_count = 0
    for story in all_stories:
        if story.ratings:
            total_ratings += sum(rating.value for rating in story.ratings)
            rating_count += len(story.ratings)
    avg_rating = total_ratings / rating_count if rating_count > 0 else 0
    
    # Calculate most used tag from all stories
    tag_counts = {}
    for story in all_stories:
        for tag in story.tags:
            tag_counts[tag.name] = tag_counts.get(tag.name, 0) + 1
    
    most_used_tag = None
    if tag_counts:
        most_used_tag_name = max(tag_counts.items(), key=lambda x: x[1])[0]
        most_used_tag = {'name': most_used_tag_name, 'count': tag_counts[most_used_tag_name]}
    
    return render_template('profile.html', 
                         user=user, 
                         stories=stories,
                         total_stories=total_stories,
                         total_words=total_words,
                         avg_words=round(avg_words),
                         avg_rating=round(avg_rating, 1),
                         rating_count=rating_count,
                         most_used_tag=most_used_tag,
                         current_page=page,
                         total_pages=total_pages)

@app.route('/edit_bio', methods=['POST'])
@login_required
def edit_bio():
    about_me = request.form.get('about_me', '').strip()
    current_user.about_me = about_me
    db.session.commit()
    flash('Bio updated successfully!')
    return redirect(url_for('profile'))

@app.route('/author/<int:user_id>')
def view_author(user_id):
    user = User.query.get_or_404(user_id)
    page = request.args.get('page', 1, type=int)
    per_page = 10  # Number of stories per page
    
    # Get all stories for statistics
    all_stories = Story.query.filter_by(user_id=user.id).all()
    
    # Get paginated stories for display
    stories_query = Story.query.filter_by(user_id=user.id).order_by(Story.id.desc())
    total_stories = stories_query.count()
    total_pages = (total_stories + per_page - 1) // per_page
    
    # Ensure page is within valid range
    page = max(1, min(page, total_pages)) if total_pages > 0 else 1
    
    # Get paginated stories
    stories = stories_query.offset((page - 1) * per_page).limit(per_page).all()
    
    # Calculate statistics from all stories
    total_words = sum(story.word_count for story in all_stories)
    avg_words = total_words / total_stories if total_stories > 0 else 0
    
    # Calculate average rating across all stories
    total_ratings = 0
    rating_count = 0
    for story in all_stories:
        if story.ratings:
            total_ratings += sum(rating.value for rating in story.ratings)
            rating_count += len(story.ratings)
    avg_rating = total_ratings / rating_count if rating_count > 0 else 0
    
    # Calculate most used tag from all stories
    tag_counts = {}
    for story in all_stories:
        for tag in story.tags:
            tag_counts[tag.name] = tag_counts.get(tag.name, 0) + 1
    
    most_used_tag = None
    if tag_counts:
        most_used_tag_name = max(tag_counts.items(), key=lambda x: x[1])[0]
        most_used_tag = {'name': most_used_tag_name, 'count': tag_counts[most_used_tag_name]}
    
    return render_template('profile.html', 
                         user=user, 
                         stories=stories,
                         total_stories=total_stories,
                         total_words=total_words,
                         avg_words=round(avg_words),
                         avg_rating=round(avg_rating, 1),
                         rating_count=rating_count,
                         most_used_tag=most_used_tag,
                         current_page=page,
                         total_pages=total_pages)

@app.route('/write', methods=['GET', 'POST'])
@login_required
def write():
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        chapter_titles = request.form.getlist('chapter_title[]')
        chapter_contents = request.form.getlist('chapter_content[]')
        tags = request.form.get('tags', '').split(',')
        
        story = Story(
            title=title, 
            description=description, 
            user_id=current_user.id,
            created_at=datetime.utcnow(),
            last_updated=datetime.utcnow()
        )
        db.session.add(story)
        db.session.flush()  # Get the story ID
        
        # Handle cover image upload
        if 'cover' in request.files:
            cover_file = request.files['cover']
            if cover_file and cover_file.filename and allowed_file(cover_file.filename):
                cover_path = process_cover_image(cover_file, story.id)
                story.cover_image = cover_path
        
        # Add tags (limited to 10)
        for tag_name in tags[:10]:
            tag_name = clean_tag(tag_name)
            if tag_name:
                tag = Tag.query.filter_by(name=tag_name).first()
                if not tag:
                    tag = Tag(name=tag_name)
                    db.session.add(tag)
                story.tags.append(tag)
        
        for i, (chapter_title, chapter_content) in enumerate(zip(chapter_titles, chapter_contents), 1):
            if chapter_title and chapter_content:  # Only add non-empty chapters
                chapter = Chapter(
                    title=chapter_title,
                    content=chapter_content,
                    chapter_number=i,
                    story_id=story.id
                )
                db.session.add(chapter)
        
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('write.html')

@app.route('/story/<int:story_id>/download/<format>')
@login_required
def download_story(story_id, format):
    story = Story.query.get_or_404(story_id)
    
    if format == 'pdf':
        # Create a PDF
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        
        # Create custom styles
        title_style = ParagraphStyle(
            'TitleStyle',
            parent=styles['Title'],
            fontSize=24,
            alignment=1,  # Center alignment
            spaceAfter=12
        )
        author_style = ParagraphStyle(
            'AuthorStyle',
            parent=styles['Normal'],
            fontSize=16,
            alignment=1,  # Center alignment
            spaceAfter=24
        )
        story_style = ParagraphStyle(
            'StoryStyle',
            parent=styles['Normal'],
            fontSize=12,
            spaceAfter=12
        )
        
        # Create the content
        content = []
        
        # Add cover image if available
        if story.cover_image:
            try:
                cover_path = os.path.join(app.static_folder, story.cover_image)
                if os.path.exists(cover_path):
                    img = Image.open(cover_path)
                    # Resize image to fit page width while maintaining aspect ratio
                    img_width, img_height = img.size
                    aspect = img_height / float(img_width)
                    max_width = letter[0] - 100  # Leave margins
                    max_height = letter[1] / 2   # Use half page height
                    
                    if img_width > max_width:
                        img_width = max_width
                        img_height = img_width * aspect
                    if img_height > max_height:
                        img_height = max_height
                        img_width = img_height / aspect
                    
                    img = img.resize((int(img_width), int(img_height)), Image.Resampling.LANCZOS)
                    img_buffer = io.BytesIO()
                    img.save(img_buffer, format='PNG')
                    img_buffer.seek(0)
                    
                    from reportlab.platypus import Image as RLImage
                    cover_img = RLImage(img_buffer, width=img_width, height=img_height)
                    content.append(cover_img)
                    content.append(Spacer(1, 24))
            except Exception as e:
                print(f"Error adding cover image: {str(e)}")
        
        # Add title page
        content.append(Paragraph(story.title, title_style))
        content.append(Paragraph(f"by {story.author.username}", author_style))
        content.append(Spacer(1, 48))  # Add extra space after title page
        
        # Add story information section
        content.append(Paragraph("Story Information", styles['Title']))
        content.append(Spacer(1, 24))
        
        # Tags
        if story.tags:
            content.append(Paragraph("Tags:", styles['Heading2']))
            content.append(Paragraph(", ".join(tag.name for tag in story.tags), styles['Normal']))
            content.append(Spacer(1, 12))
        
        # Description
        if story.description:
            content.append(Paragraph("Description:", styles['Heading2']))
            content.append(Paragraph(story.description, styles['Normal']))
            content.append(Spacer(1, 12))
        
        # Statistics and Rating
        content.append(Paragraph("Statistics:", styles['Heading2']))
        content.append(Paragraph(f"Chapters: {len(story.chapters)}", styles['Normal']))
        content.append(Paragraph(f"Word Count: {story.word_count}", styles['Normal']))
        if story.ratings:
            content.append(Paragraph(f"Average Rating: {story.average_rating:.1f} ({len(story.ratings)} ratings)", styles['Normal']))
        content.append(Paragraph(f"Upload Date: {story.created_at.strftime('%B %d, %Y at %I:%M %p UTC')}", styles['Normal']))
        content.append(Paragraph(f"Last Updated: {story.last_updated.strftime('%B %d, %Y at %I:%M %p UTC')}", styles['Normal']))
        content.append(Spacer(1, 24))
        
        # Add a page break
        content.append(Paragraph("Story Content", styles['Title']))
        content.append(Spacer(1, 24))
        
        # Add chapters
        for chapter in story.chapters:
            content.append(Paragraph(f"Chapter {chapter.chapter_number}: {chapter.title}", styles['Heading1']))
            content.append(Spacer(1, 12))
            content.append(Paragraph(chapter.content, story_style))
            content.append(Spacer(1, 24))
        
        # Build the PDF
        doc.build(content)
        buffer.seek(0)
        
        return send_file(
            buffer,
            as_attachment=True,
            download_name=f"{story.title}.pdf",
            mimetype='application/pdf'
        )
    
    elif format == 'epub':
        # Create an EPUB
        book = epub.EpubBook()
        
        # Set metadata
        book.set_identifier(f'story_{story.id}')
        book.set_title(story.title)
        book.set_language('en')
        book.add_author(story.author.username)
        
        # Add dates to metadata
        book.add_metadata('DC', 'date', story.created_at.strftime('%Y-%m-%dT%H:%M:%SZ'))
        book.add_metadata('DC', 'date.modified', story.last_updated.strftime('%Y-%m-%dT%H:%M:%SZ'))
        
        # Add cover image if available
        if story.cover_image:
            try:
                cover_path = os.path.join(app.static_folder, story.cover_image)
                if os.path.exists(cover_path):
                    with open(cover_path, 'rb') as f:
                        book.set_cover('cover.jpg', f.read())
            except Exception as e:
                print(f"Error adding cover image: {str(e)}")
        
        # Add tags to metadata
        if story.tags:
            book.add_metadata('DC', 'subject', ', '.join(tag.name for tag in story.tags))
        
        # Add rating to metadata
        if story.ratings:
            book.add_metadata('DC', 'rating', f"{story.average_rating:.1f}")
            book.add_metadata('DC', 'rating_count', str(len(story.ratings)))
        
        # Create title page
        title_page = epub.EpubHtml(
            title='Title Page',
            file_name='title.xhtml'
        )
        
        # Create title page content
        title_content = f'''
        <div class="title-page">
            <h1 class="title">{story.title}</h1>
            <h2 class="author">by {story.author.username}</h2>
        </div>
        '''
        title_page.content = title_content
        book.add_item(title_page)
        
        # Create metadata chapter
        metadata_chapter = epub.EpubHtml(
            title='Story Information',
            file_name='metadata.xhtml'
        )
        
        # Create metadata content
        metadata_content = f'''
        <h1>Story Information</h1>
        <div class="metadata">
            <h2>Tags</h2>
            <p>{", ".join(tag.name for tag in story.tags) if story.tags else "No tags"}</p>
            
            <h2>Description</h2>
            <p>{story.description if story.description else "No description"}</p>
            
            <h2>Statistics</h2>
            <p>Chapters: {len(story.chapters)}</p>
            <p>Word Count: {story.word_count}</p>
            {f'<p>Average Rating: {story.average_rating:.1f} ({len(story.ratings)} ratings)</p>' if story.ratings else ''}
            <p>Upload Date: {story.created_at.strftime('%B %d, %Y at %I:%M %p UTC')}</p>
            <p>Last Updated: {story.last_updated.strftime('%B %d, %Y at %I:%M %p UTC')}</p>
        </div>
        '''
        metadata_chapter.content = metadata_content
        book.add_item(metadata_chapter)
        
        # Create chapters
        chapters = []
        for chapter in story.chapters:
            chapter_file = epub.EpubHtml(
                title=chapter.title,
                file_name=f'chapter_{chapter.chapter_number}.xhtml'
            )
            chapter_file.content = f'<h1>Chapter {chapter.chapter_number}: {chapter.title}</h1><p>{chapter.content}</p>'
            book.add_item(chapter_file)
            chapters.append(chapter_file)
        
        # Create table of contents
        book.toc = [
            epub.Link('title.xhtml', 'Title Page', 'title'),
            epub.Link('metadata.xhtml', 'Story Information', 'metadata'),
            (epub.Section('Chapters'),
             [epub.Link(f'chapter_{i+1}.xhtml', chapter.title, f'chapter_{i+1}') 
              for i, chapter in enumerate(story.chapters)])
        ]
        
        # Add default NCX and Nav files
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        
        # Define CSS style
        style = '''
        body {
            font-family: Cambria, Liberation Serif, Bitstream Vera Serif, Georgia, Times, Times New Roman, serif;
        }
        .title-page {
            text-align: center;
            margin: 4em 0;
        }
        .title-page .title {
            font-size: 2em;
            margin-bottom: 0.5em;
        }
        .title-page .author {
            font-size: 1.5em;
            color: #666;
        }
        .metadata {
            margin: 2em 0;
        }
        .metadata h2 {
            color: #666;
            margin-top: 1em;
            margin-bottom: 0.5em;
        }
        .metadata p {
            margin: 0 0 1em 0;
        }
        '''
        nav_css = epub.EpubItem(uid="style_nav", file_name="style/nav.css", media_type="text/css", content=style)
        book.add_item(nav_css)
        
        # Create spine
        book.spine = ['nav', title_page, metadata_chapter] + chapters
        
        # Create EPUB file
        epub_path = os.path.join(tempfile.gettempdir(), f"{story.title}.epub")
        epub.write_epub(epub_path, book)
        
        return send_file(
            epub_path,
            as_attachment=True,
            download_name=f"{story.title}.epub",
            mimetype='application/epub+zip'
        )
    
    return redirect(url_for('index'))

@app.route('/story/<int:story_id>')
def view_story(story_id):
    story = Story.query.get_or_404(story_id)
    current_user_rating = None
    if current_user.is_authenticated:
        current_user_rating = Rating.query.filter_by(
            user_id=current_user.id,
            story_id=story.id
        ).first()
    return render_template('story.html', story=story, current_user_rating=current_user_rating)

@app.route('/story/<int:story_id>/rate', methods=['POST'])
@login_required
def rate_story(story_id):
    story = Story.query.get_or_404(story_id)
    rating_value = request.form.get('rating', type=int)
    
    if not rating_value or rating_value < 1 or rating_value > 5:
        flash('Invalid rating value')
        return redirect(url_for('view_story', story_id=story.id))
    
    # Check if user has already rated this story
    existing_rating = Rating.query.filter_by(
        user_id=current_user.id,
        story_id=story.id
    ).first()
    
    if existing_rating:
        existing_rating.value = rating_value
    else:
        new_rating = Rating(
            value=rating_value,
            user_id=current_user.id,
            story_id=story.id
        )
        db.session.add(new_rating)
    
    db.session.commit()
    flash('Rating saved successfully!')
    return redirect(url_for('view_story', story_id=story.id))

@app.route('/story/<int:story_id>/remove_rating', methods=['POST'])
@login_required
def remove_rating(story_id):
    story = Story.query.get_or_404(story_id)
    
    # Find and remove the user's rating
    rating = Rating.query.filter_by(
        user_id=current_user.id,
        story_id=story.id
    ).first()
    
    if rating:
        db.session.delete(rating)
        db.session.commit()
        flash('Rating removed successfully!')
    else:
        flash('No rating found to remove.')
    
    return redirect(url_for('view_story', story_id=story.id))

@app.route('/story/<int:story_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_story(story_id):
    story = Story.query.get_or_404(story_id)
    
    # Check if the current user is the author
    if current_user.id != story.user_id:
        flash('You can only edit your own stories.')
        return redirect(url_for('view_story', story_id=story.id))
    
    if request.method == 'POST':
        # Update story details
        story.title = request.form.get('title')
        story.description = request.form.get('description')
        story.last_updated = datetime.utcnow()  # Update the last_updated timestamp
        
        # Handle cover image removal
        if request.form.get('remove_cover') == '1':
            if story.cover_image:
                # Delete the file from the filesystem
                try:
                    file_path = os.path.join(app.static_folder, story.cover_image)
                    if os.path.exists(file_path):
                        os.remove(file_path)
                except Exception as e:
                    flash(f'Error removing old cover image: {str(e)}')
            story.cover_image = None
        
        # Handle cover image upload
        elif 'cover_image' in request.files:
            file = request.files['cover_image']
            if file and file.filename and allowed_file(file.filename):
                try:
                    # Remove old cover image if it exists
                    if story.cover_image:
                        try:
                            old_file_path = os.path.join(app.static_folder, story.cover_image)
                            if os.path.exists(old_file_path):
                                os.remove(old_file_path)
                        except Exception as e:
                            flash(f'Error removing old cover image: {str(e)}')
                    
                    cover_path = process_cover_image(file, story.id)
                    story.cover_image = cover_path
                except Exception as e:
                    flash(f'Error processing cover image: {str(e)}')
            elif file and file.filename:
                flash('Invalid file type. Allowed types: png, jpg, jpeg, gif')
        
        # Update tags
        story.tags = []  # Clear existing tags
        tags = request.form.get('tags', '').split(',')
        for tag_name in tags[:10]:  # Limit to 10 tags
            tag_name = clean_tag(tag_name)
            if tag_name:
                tag = Tag.query.filter_by(name=tag_name).first()
                if not tag:
                    tag = Tag(name=tag_name)
                    db.session.add(tag)
                story.tags.append(tag)
        
        # Get chapter data from form
        chapter_ids = request.form.getlist('chapter_id[]')
        chapter_titles = request.form.getlist('chapter_title[]')
        chapter_contents = request.form.getlist('chapter_content[]')
        
        # First, delete all existing chapters
        for chapter in story.chapters:
            db.session.delete(chapter)
        
        # Then create new chapters with the submitted data
        for i, (chapter_id, title, content) in enumerate(zip(chapter_ids, chapter_titles, chapter_contents), 1):
            if title and content:  # Only create chapter if both title and content are provided
                chapter = Chapter(
                    title=title,
                    content=content,
                    chapter_number=i,
                    story_id=story.id
                )
                db.session.add(chapter)
        
        db.session.commit()
        flash('Story updated successfully!')
        return redirect(url_for('view_story', story_id=story.id))
    
    return render_template('edit_story.html', story=story)

@app.route('/story/<int:story_id>/delete', methods=['POST'])
@login_required
def delete_story(story_id):
    story = Story.query.get_or_404(story_id)
    
    # Check if the current user is the author
    if current_user.id != story.user_id:
        flash('You can only delete your own stories.')
        return redirect(url_for('view_story', story_id=story.id))
    
    # Delete cover image if it exists
    if story.cover_image:
        try:
            file_path = os.path.join(app.static_folder, story.cover_image)
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            flash(f'Error removing cover image: {str(e)}')
    
    # Delete the story (this will cascade delete related records)
    db.session.delete(story)
    db.session.commit()
    
    flash('Story deleted successfully!')
    return redirect(url_for('index'))

@app.route('/library')
@login_required
def library():
    saved_stories = SavedStory.query.filter_by(user_id=current_user.id).order_by(SavedStory.saved_at.desc()).all()
    return render_template('library.html', saved_stories=saved_stories)

@app.route('/save_story/<int:story_id>', methods=['POST'])
@login_required
def save_story(story_id):
    story = Story.query.get_or_404(story_id)
    saved_story = SavedStory.query.filter_by(user_id=current_user.id, story_id=story_id).first()
    
    if saved_story:
        db.session.delete(saved_story)
        db.session.commit()
        flash('Story removed from your library', 'info')
    else:
        saved_story = SavedStory(user_id=current_user.id, story_id=story_id)
        db.session.add(saved_story)
        db.session.commit()
        flash('Story added to your library', 'success')
    
    return redirect(url_for('view_story', story_id=story_id))

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True) 