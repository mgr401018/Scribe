"""Add chapters support

Revision ID: add_chapters
Revises: ef8c13044649
Create Date: 2024-03-19 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_chapters'
down_revision = 'ef8c13044649'
branch_labels = None
depends_on = None


def upgrade():
    # Create chapters table
    op.create_table('chapter',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=100), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('chapter_number', sa.Integer(), nullable=False),
        sa.Column('story_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['story_id'], ['story.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Add description column to story table
    op.add_column('story', sa.Column('description', sa.Text(), nullable=True))
    
    # Migrate existing content to first chapter
    connection = op.get_bind()
    stories = connection.execute('SELECT id, content FROM story').fetchall()
    
    for story_id, content in stories:
        connection.execute(
            'INSERT INTO chapter (title, content, chapter_number, story_id) VALUES (%s, %s, %s, %s)',
            ('Chapter 1', content, 1, story_id)
        )
    
    # Remove content column from story table
    op.drop_column('story', 'content')


def downgrade():
    # Add content column back to story table
    op.add_column('story', sa.Column('content', sa.Text(), nullable=True))
    
    # Migrate first chapter content back to story
    connection = op.get_bind()
    stories = connection.execute('SELECT story_id, content FROM chapter WHERE chapter_number = 1').fetchall()
    
    for story_id, content in stories:
        connection.execute(
            'UPDATE story SET content = %s WHERE id = %s',
            (content, story_id)
        )
    
    # Drop chapters table
    op.drop_table('chapter')
    
    # Remove description column from story table
    op.drop_column('story', 'description') 