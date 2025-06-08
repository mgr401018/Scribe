from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, User, Story, Rating

profile = Blueprint('profile', __name__)

@profile.route('/profile')
@login_required
def view_profile():
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

@profile.route('/edit_bio', methods=['POST'])
@login_required
def edit_bio():
    about_me = request.form.get('about_me', '').strip()
    current_user.about_me = about_me
    db.session.commit()
    flash('Bio updated successfully!')
    return redirect(url_for('profile.view_profile'))

@profile.route('/author/<int:user_id>')
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