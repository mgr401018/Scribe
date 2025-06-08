FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy the entire project
COPY . .

# Create necessary directories if they don't exist
RUN mkdir -p templates static/uploads

ENV FLASK_APP=app.py
ENV PYTHONPATH=/app
ENV FLASK_DEBUG=1

CMD ["flask", "run", "--host=0.0.0.0"] 