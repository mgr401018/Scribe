from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

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