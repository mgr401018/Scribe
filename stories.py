from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, current_app
from flask_login import login_required, current_user
from datetime import datetime
import os
import io
import tempfile
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from ebooklib import epub
from PIL import Image
from models import db, Story, Chapter, Tag, Rating
from utils import clean_tag, allowed_file, process_cover_image

stories = Blueprint('stories', __name__)

@stories.route('/write', methods=['GET', 'POST'])
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
                cover_path = process_cover_image(cover_file, story.id, current_app)
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
        return redirect(url_for('search.index'))
    return render_template('write.html')

@stories.route('/story/<int:story_id>')
def view_story(story_id):
    story = Story.query.get_or_404(story_id)
    current_user_rating = None
    if current_user.is_authenticated:
        current_user_rating = Rating.query.filter_by(
            user_id=current_user.id,
            story_id=story.id
        ).first()
    return render_template('story.html', story=story, current_user_rating=current_user_rating)

@stories.route('/story/<int:story_id>/rate', methods=['POST'])
@login_required
def rate_story(story_id):
    story = Story.query.get_or_404(story_id)
    rating_value = request.form.get('rating', type=int)
    
    if not rating_value or rating_value < 1 or rating_value > 5:
        flash('Invalid rating value')
        return redirect(url_for('stories.view_story', story_id=story.id))
    
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
    return redirect(url_for('stories.view_story', story_id=story.id))

@stories.route('/story/<int:story_id>/remove_rating', methods=['POST'])
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
    
    return redirect(url_for('stories.view_story', story_id=story.id))

@stories.route('/story/<int:story_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_story(story_id):
    story = Story.query.get_or_404(story_id)
    
    # Check if the current user is the author
    if current_user.id != story.user_id:
        flash('You can only edit your own stories.')
        return redirect(url_for('stories.view_story', story_id=story.id))
    
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
                    file_path = os.path.join(current_app.static_folder, story.cover_image)
                    if os.path.exists(file_path):
                        os.remove(file_path)
                except Exception as e:
                    flash(f'Error removing old cover image: {str(e)}')
            story.cover_image = None
        
        # Handle cover image upload (independent of removal)
        if 'cover_image' in request.files:
            file = request.files['cover_image']
            if file and file.filename and allowed_file(file.filename):
                try:
                    # Remove old cover image if it exists
                    if story.cover_image:
                        try:
                            old_file_path = os.path.join(current_app.static_folder, story.cover_image)
                            if os.path.exists(old_file_path):
                                os.remove(old_file_path)
                        except Exception as e:
                            flash(f'Error removing old cover image: {str(e)}')
                    
                    cover_path = process_cover_image(file, story.id, current_app)
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
        
        # Then add the new chapters
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
        flash('Story updated successfully!')
        return redirect(url_for('stories.view_story', story_id=story.id))
    
    return render_template('edit_story.html', story=story)

@stories.route('/story/<int:story_id>/delete', methods=['POST'])
@login_required
def delete_story(story_id):
    story = Story.query.get_or_404(story_id)
    
    # Check if the current user is the author
    if current_user.id != story.user_id:
        flash('You can only delete your own stories.')
        return redirect(url_for('stories.view_story', story_id=story.id))
    
    # Delete cover image if it exists
    if story.cover_image:
        try:
            file_path = os.path.join(current_app.static_folder, story.cover_image)
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            flash(f'Error removing cover image: {str(e)}')
    
    # Delete the story (this will cascade delete related records)
    db.session.delete(story)
    db.session.commit()
    
    flash('Story deleted successfully!')
    return redirect(url_for('search.index'))

@stories.route('/story/<int:story_id>/download/<format>')
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
                cover_path = os.path.join(current_app.static_folder, story.cover_image)
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
                cover_path = os.path.join(current_app.static_folder, story.cover_image)
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
    
    return redirect(url_for('search.index')) 