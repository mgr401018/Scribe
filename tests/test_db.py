import pytest
from app import create_app
from app.models import db, User, Story, Chapter, Tag, Rating
from datetime import datetime

@pytest.fixture
def app():
    """Create and configure a Flask app for testing."""
    app = create_app()
    app.config.update({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'WTF_CSRF_ENABLED': False,
    })
    
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    """Create a test client for the app."""
    return app.test_client()

@pytest.fixture
def test_user(app):
    """Create a test user."""
    with app.app_context():
        user = User(username='testuser', password_hash='testpass')
        db.session.add(user)
        db.session.commit()
        # Refresh user ->> session
        db.session.refresh(user)
        return user

def test_create_story(app, test_user):
    """Test creating a story with chapters."""
    with app.app_context():
        story = Story(
            title='Test Story',
            description='Test Description',
            user_id=test_user.id
        )
        db.session.add(story)
        db.session.flush()

        chapter = Chapter(
            title='Chapter 1',
            content='Test content',
            chapter_number=1,
            story_id=story.id
        )
        db.session.add(chapter)
        db.session.commit()

        saved_story = Story.query.first()
        assert saved_story.title == 'Test Story'
        assert saved_story.description == 'Test Description'
        assert len(saved_story.chapters) == 1
        assert saved_story.chapters[0].title == 'Chapter 1'

def test_story_rating(app, test_user):
    """Test rating a story."""
    with app.app_context():
        story = Story(
            title='Test Story',
            user_id=test_user.id
        )
        db.session.add(story)
        db.session.flush()

        rating = Rating(
            user_id=test_user.id,
            story_id=story.id,
            value=5
        )
        db.session.add(rating)
        db.session.commit()

        saved_rating = Rating.query.first()
        assert saved_rating.value == 5
        assert saved_rating.user_id == test_user.id
        assert saved_rating.story_id == story.id

def test_story_tags(app, test_user):
    """Test adding tags to a story."""
    with app.app_context():
        story = Story(
            title='Test Story',
            user_id=test_user.id
        )
        db.session.add(story)
        db.session.flush()

        tag1 = Tag(name='fantasy')
        tag2 = Tag(name='adventure')
        story.tags.append(tag1)
        story.tags.append(tag2)
        db.session.commit()

        saved_story = Story.query.first()
        assert len(saved_story.tags) == 2
        assert any(tag.name == 'fantasy' for tag in saved_story.tags)
        assert any(tag.name == 'adventure' for tag in saved_story.tags) 