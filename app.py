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

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'postgresql://postgres:postgres@db:5432/scribe')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

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

@app.route('/')
def index():
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
        
        story = Story(title=title, description=description, user_id=current_user.id)
        db.session.add(story)
        db.session.flush()  # Get the story ID
        
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
        story_style = ParagraphStyle(
            'StoryStyle',
            parent=styles['Normal'],
            fontSize=12,
            spaceAfter=12
        )
        
        # Create the content
        content = []
        content.append(Paragraph(story.title, styles['Title']))
        content.append(Spacer(1, 12))
        content.append(Paragraph(f"By {story.author.username}", styles['Normal']))
        if story.description:
            content.append(Spacer(1, 12))
            content.append(Paragraph(story.description, styles['Normal']))
        
        # Add chapters
        for chapter in story.chapters:
            content.append(Spacer(1, 24))
            content.append(Paragraph(f"Chapter {chapter.chapter_number}: {chapter.title}", styles['Heading1']))
            content.append(Spacer(1, 12))
            content.append(Paragraph(chapter.content, story_style))
        
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
        book.toc = [(epub.Link(f'chapter_{i+1}.xhtml', chapter.title, f'chapter_{i+1}')) 
                   for i, chapter in enumerate(story.chapters)]
        
        # Add default NCX and Nav files
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        
        # Define CSS style
        style = '''
        body {
            font-family: Cambria, Liberation Serif, Bitstream Vera Serif, Georgia, Times, Times New Roman, serif;
        }
        '''
        nav_css = epub.EpubItem(uid="style_nav", file_name="style/nav.css", media_type="text/css", content=style)
        book.add_item(nav_css)
        
        # Create spine
        book.spine = ['nav'] + chapters
        
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
        
        # Get chapter data from form
        chapter_ids = request.form.getlist('chapter_id[]')
        chapter_titles = request.form.getlist('chapter_title[]')
        chapter_contents = request.form.getlist('chapter_content[]')
        
        # Update existing chapters and collect IDs of chapters to keep
        chapters_to_keep = set()
        
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