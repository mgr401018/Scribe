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

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'postgresql://postgres:postgres@db:5432/scribe')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

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
    password_hash = db.Column(db.String(128))
    stories = db.relationship('Story', backref='author', lazy=True)

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    chapters = db.relationship('Chapter', backref='story', lazy=True, order_by='Chapter.chapter_number')

    @property
    def word_count(self):
        total_words = 0
        for chapter in self.chapters:
            total_words += len(chapter.content.split())
        return total_words

class Chapter(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    chapter_number = db.Column(db.Integer, nullable=False)
    story_id = db.Column(db.Integer, db.ForeignKey('story.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Create database tables
with app.app_context():
    db.create_all()

def clean_tag(tag):
    # Remove special characters and convert to lowercase
    return re.sub(r'[^a-zA-Z0-9\s-]', '', tag).strip().lower()

@app.route('/')
def index():
    search_query = request.args.get('search', '')
    if search_query:
        query = Story.query
        
        # Handle multiple search modifiers
        title_query = None
        author_query = None
        tag_queries = []
        
        # Extract title search if present
        if 'title:' in search_query:
            title_part = search_query.split('title:', 1)[1]
            # Find the next modifier or end of string
            next_modifier = min(
                [i for i in [title_part.find(' by:'), title_part.find(' tags:'), len(title_part)] if i != -1]
            )
            title_part = title_part[:next_modifier].strip()
            
            if title_part.startswith('"'):
                end_quote = title_part.find('"', 1)
                if end_quote != -1:
                    title_query = title_part[1:end_quote]
            else:
                title_query = title_part.split()[0]
        
        # Extract author search if present
        if 'by:' in search_query:
            author_part = search_query.split('by:', 1)[1]
            # Find the next modifier or end of string
            next_modifier = min(
                [i for i in [author_part.find(' title:'), author_part.find(' tags:'), len(author_part)] if i != -1]
            )
            author_part = author_part[:next_modifier].strip()
            
            if author_part.startswith('"'):
                end_quote = author_part.find('"', 1)
                if end_quote != -1:
                    author_query = author_part[1:end_quote]
            else:
                author_query = author_part.split()[0]
        
        # Extract tag search if present
        if 'tags:' in search_query:
            tag_part = search_query.split('tags:', 1)[1].strip()
            if tag_part.startswith('"'):
                end_quote = tag_part.find('"', 1)
                if end_quote != -1:
                    tag_part = tag_part[1:end_quote]
            
            # Split tags by comma and clean each tag
            tag_queries = [clean_tag(tag) for tag in tag_part.split(',') if tag.strip()]
        
        # Apply filters
        if title_query:
            query = query.filter(Story.title.ilike(f'%{title_query}%'))
        if author_query:
            query = query.join(User).filter(User.username.ilike(f'%{author_query}%'))
        if tag_queries:
            # For each tag, create a subquery to find stories with that tag
            for tag_query in tag_queries:
                # Create a subquery for stories with this tag - using exact match
                tag_subquery = db.session.query(story_tags.c.story_id).join(Tag).filter(Tag.name == tag_query).subquery()
                # Filter the main query to only include stories that have this tag
                query = query.filter(Story.id.in_(tag_subquery))
        
        # If no modifiers were used, search in both title and description
        if not title_query and not author_query and not tag_queries:
            query = query.filter(
                (Story.title.ilike(f'%{search_query}%')) |
                (Story.description.ilike(f'%{search_query}%'))
            )
        
        stories = query.order_by(Story.id.desc()).all()
    else:
        stories = Story.query.order_by(Story.id.desc()).all()
    return render_template('index.html', stories=stories)

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

@app.route('/write', methods=['GET', 'POST'])
@login_required
def write():
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        chapter_titles = request.form.getlist('chapter_title[]')
        chapter_contents = request.form.getlist('chapter_content[]')
        tags = request.form.get('tags', '').split(',')
        
        story = Story(title=title, description=description, user_id=current_user.id)
        db.session.add(story)
        db.session.flush()  # Get the story ID
        
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
        
        # Statistics
        content.append(Paragraph("Statistics:", styles['Heading2']))
        content.append(Paragraph(f"Chapters: {len(story.chapters)}", styles['Normal']))
        content.append(Paragraph(f"Word Count: {story.word_count}", styles['Normal']))
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
        
        # Add tags to metadata
        if story.tags:
            book.add_metadata('DC', 'subject', ', '.join(tag.name for tag in story.tags))
        
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
    return render_template('story.html', story=story)

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True) 