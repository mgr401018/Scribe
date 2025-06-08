from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models import db, SavedStory, Story

library = Blueprint('library', __name__)

@library.route('/library')
@login_required
def view_library():
    saved_stories = SavedStory.query.filter_by(user_id=current_user.id).order_by(SavedStory.saved_at.desc()).all()
    return render_template('library.html', saved_stories=saved_stories)

@library.route('/save_story/<int:story_id>', methods=['POST'])
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
    
    return redirect(url_for('stories.view_story', story_id=story_id)) 