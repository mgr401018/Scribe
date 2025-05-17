# Scribe ("Software Development" subject final project) NOTE: SUBJECT TO CHANGE

Scribe is a web-based story writing and sharing platform built with Flask. It allows users to create accounts, write stories, and share them with others.

## Features

- User authentication (register, login, logout)
- Create and publish stories
- View stories from all users
- Secure password hashing
- PostgreSQL database integration
- Docker support for easy deployment
- Download stories as PDF or EPUB
- Chapter support for stories & story editing
- Tags (up to 10 per story)
- Search and Advanced search
  - Search by title: `title:"your title"`
  - Search by author: `by:"author name"`
  - Search by tags: `tags:"tag1, tag2"`
  - Combine search modifiers: `title:"title1" by:"user1" tags:"fantasy, adventure"`
- User Profiles and Statistics
- Story Ratings
- Story Covers
- Search Filters
- "Uploaded" and "Last Updated" dates
- User Library and Story Saving

## Prerequisites

- Python 3.7+
- Docker and Docker Compose (for containerized deployment)
- PostgreSQL (if running without Docker)

## Installation

### Using Docker (Recommended)

1. Clone the repository:
```bash
git clone <repository-url>
cd scribe
```

2. Start the application using Docker Compose:
```bash
docker-compose up --build
```

The application will be available at `http://localhost:5000`

### Manual Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd scribe
```

2. Create a virtual environment and activate it:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
export SECRET_KEY='your-secret-key'
export DATABASE_URL='postgresql://username:password@localhost:5432/scribe'
```

5. Run the database migration:
```bash
flask db upgrade
```

6. Run the application:
```bash
python app.py
```

## Project Structure

```
scribe/
├── app.py              # Main application file
├── requirements.txt    # Python dependencies
├── Dockerfile         # Docker configuration
├── docker-compose.yml # Docker Compose configuration
├── templates/         # HTML templates
└── migrations/        # Database migrations
```

## Dependencies

- Flask - Web framework
- Flask-SQLAlchemy - Database ORM
- Flask-Login - User authentication
- Flask-WTF - Form handling
- psycopg2-binary - PostgreSQL adapter
- python-dotenv - Environment variable management
- Werkzeug - WSGI utilities
- SQLAlchemy - SQL toolkit