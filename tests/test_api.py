import pytest
from app import create_app
from app.models import db, User, Story, Chapter, SavedStory, Tag
from flask_login import login_user, current_user
from werkzeug.security import generate_password_hash

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
        user = User(
            username='testuser',
            password_hash=generate_password_hash('testpass')
        )
        db.session.add(user)
        db.session.commit()
        # Refresh user ->> session
        db.session.refresh(user)
        return user

@pytest.fixture
def auth_client(client, test_user):
    """Create an authenticated test client."""
    with client:
        with client.session_transaction() as session:
            session['_user_id'] = str(test_user.id)
    return client

# Authentication Tests
def test_register(client):
    """Test user registration."""
    response = client.post('/register', data={
        'username': 'newuser',
        'password': 'password123'
    }, follow_redirects=True)
    assert response.status_code == 200
    
    with client.application.app_context():
        user = User.query.filter_by(username='newuser').first()
        assert user is not None

def test_login_success(client, test_user):
    """Test successful user login."""
    response = client.post('/login', data={
        'username': 'testuser',
        'password': 'testpass'
    }, follow_redirects=True)
    assert response.status_code == 200
    
    with client.session_transaction() as session:
        assert '_user_id' in session
        assert session['_user_id'] == str(test_user.id)

def test_login_wrong_password(client, test_user):
    """Test login with wrong password."""
    response = client.post('/login', data={
        'username': 'testuser',
        'password': 'wrongpass'
    }, follow_redirects=True)
    assert response.status_code == 200
    
    with client.session_transaction() as session:
        assert '_user_id' not in session

def test_login_nonexistent_user(client):
    """Test login with non-existent user."""
    response = client.post('/login', data={
        'username': 'nonexistent',
        'password': 'password123'
    }, follow_redirects=True)
    assert response.status_code == 200
    
    with client.session_transaction() as session:
        assert '_user_id' not in session

def test_logout(auth_client):
    """Test user logout."""
    with auth_client.session_transaction() as session:
        assert '_user_id' in session
    
    response = auth_client.get('/logout', follow_redirects=True)
    assert response.status_code == 200
    
    with auth_client.session_transaction() as session:
        assert '_user_id' not in session

# Story Tests
def test_view_story(client, test_user):
    """Test viewing a story."""
    with client.application.app_context():
        story = Story(
            title='Test Story',
            description='Test Description',
            user_id=test_user.id
        )
        db.session.add(story)
        db.session.commit()

        response = client.get(f'/story/{story.id}')
        assert response.status_code == 200
        assert b'Test Story' in response.data
        assert b'Test Description' in response.data

def test_rate_story(auth_client, test_user):
    """Test rating a story."""
    with auth_client.application.app_context():
        story = Story(
            title='Test Story',
            user_id=test_user.id
        )
        db.session.add(story)
        db.session.commit()

        response = auth_client.post(
            f'/story/{story.id}/rate',
            data={'rating': 5},
            follow_redirects=True
        )
        assert response.status_code == 200

        saved_story = Story.query.first()
        assert len(saved_story.ratings) == 1
        assert saved_story.ratings[0].value == 5

def test_remove_rating(auth_client, test_user):
    """Test removing a story rating."""
    with auth_client.application.app_context():
        story = Story(
            title='Test Story',
            user_id=test_user.id
        )
        db.session.add(story)
        db.session.flush()

        from app.models import Rating
        rating = Rating(
            user_id=test_user.id,
            story_id=story.id,
            value=5
        )
        db.session.add(rating)
        db.session.commit()

        response = auth_client.post(
            f'/story/{story.id}/remove_rating',
            follow_redirects=True
        )
        assert response.status_code == 200

        saved_story = Story.query.first()
        assert len(saved_story.ratings) == 0

# Search Tests
def test_search_by_title(client, test_user):
    """Test searching stories by title."""
    with client.application.app_context():
        story1 = Story(title='Fantasy Story', user_id=test_user.id)
        story2 = Story(title='Adventure Story', user_id=test_user.id)
        db.session.add_all([story1, story2])
        db.session.commit()

        response = client.get('/?search=title:"Fantasy"')
        assert response.status_code == 200
        assert b'Fantasy Story' in response.data
        assert b'Adventure Story' not in response.data

def test_search_by_author(client, test_user):
    """Test searching stories by author."""
    with client.application.app_context():
        other_user = User(username='otheruser', password_hash='testpass')
        db.session.add(other_user)
        db.session.commit()

        story1 = Story(title='My Story', user_id=test_user.id)
        story2 = Story(title='Other Story', user_id=other_user.id)
        db.session.add_all([story1, story2])
        db.session.commit()

        response = client.get('/?search=by:"testuser"')
        assert response.status_code == 200
        assert b'My Story' in response.data
        assert b'Other Story' not in response.data

def test_search_by_tags(client, test_user):
    """Test searching stories by tags."""
    with client.application.app_context():
        story1 = Story(title='Fantasy Story', user_id=test_user.id)
        story2 = Story(title='Sci-Fi Story', user_id=test_user.id)
 
        fantasy_tag = Tag(name='fantasy')
        scifi_tag = Tag(name='scifi')
        story1.tags.append(fantasy_tag)
        story2.tags.append(scifi_tag)
        
        db.session.add_all([story1, story2])
        db.session.commit()

        response = client.get('/?search=tags:"fantasy"')
        assert response.status_code == 200
        assert b'Fantasy Story' in response.data
        assert b'Sci-Fi Story' not in response.data

def test_combined_search(client, test_user):
    """Test searching with multiple criteria."""
    with client.application.app_context():
        story1 = Story(title='Fantasy Adventure', user_id=test_user.id)
        story2 = Story(title='Sci-Fi Story', user_id=test_user.id)
        
        fantasy_tag = Tag(name='fantasy')
        adventure_tag = Tag(name='adventure')
        story1.tags.extend([fantasy_tag, adventure_tag])
        
        db.session.add_all([story1, story2])
        db.session.flush()

        from app.models import Rating
        rating = Rating(user_id=test_user.id, story_id=story1.id, value=5)
        db.session.add(rating)
        db.session.commit()

        response = client.get('/?search=title:"Fantasy" tags:"adventure" rating_more_than:4')
        assert response.status_code == 200
        assert b'Fantasy Adventure' in response.data
        assert b'Sci-Fi Story' not in response.data

# Profile Tests
def test_view_profile(auth_client):
    """Test viewing user profile."""
    response = auth_client.get('/profile')
    assert response.status_code == 200
    assert b'testuser' in response.data

def test_edit_bio(auth_client):
    """Test editing user bio."""
    response = auth_client.post('/edit_bio', data={
        'about_me': 'This is my new bio'
    }, follow_redirects=True)
    assert response.status_code == 200

    with auth_client.application.app_context():
        user = User.query.first()
        assert user.about_me == 'This is my new bio'

# Library Tests
def test_view_library(auth_client):
    """Test viewing user's library."""
    response = auth_client.get('/library')
    assert response.status_code == 200

def test_save_story(auth_client, test_user):
    """Test saving a story to library."""
    with auth_client.application.app_context():
        story = Story(
            title='Test Story',
            user_id=test_user.id
        )
        db.session.add(story)
        db.session.commit()

        response = auth_client.post(f'/save_story/{story.id}', follow_redirects=True)
        assert response.status_code == 200

        saved_story = SavedStory.query.filter_by(
            user_id=test_user.id,
            story_id=story.id
        ).first()
        assert saved_story is not None 