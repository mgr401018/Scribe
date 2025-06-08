from flask import Blueprint, render_template, request
from models import Story, User, Chapter, Tag, Rating, db, story_tags
from utils import clean_tag

search = Blueprint('search', __name__)

@search.route('/')
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