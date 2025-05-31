terraform {
  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 3.0"
    }
  }
}

provider "docker" {}

# Create a Docker network
resource "docker_network" "private_network" {
  name = "scribe_network"
  check_duplicate = true
}

# Create a Docker volume for PostgreSQL data
resource "docker_volume" "postgres_data" {
  name = "postgres_data"
}

# Create the PostgreSQL container
resource "docker_container" "db" {
  name  = "db"
  image = docker_image.postgres.image_id
  ports {
    internal = 5432
    external = 5434
  }
  env = [
    "POSTGRES_PASSWORD=postgres",
    "POSTGRES_USER=postgres",
    "POSTGRES_DB=scribe"
  ]
  volumes {
    volume_name    = docker_volume.postgres_data.name
    container_path = "/var/lib/postgresql/data"
  }
  networks_advanced {
    name = docker_network.private_network.name
  }
  healthcheck {
    test         = ["CMD-SHELL", "pg_isready -U postgres"]
    interval     = "5s"
    timeout      = "5s"
    retries      = 5
  }
}

# Pull the PostgreSQL image
resource "docker_image" "postgres" {
  name = "postgres:15"
}

# Create the web application container
resource "docker_container" "web" {
  name  = "web"
  image = docker_image.web.name
  ports {
    internal = 5000
    external = 5000
  }
  env = [
    "FLASK_APP=app.py",
    "FLASK_ENV=development",
    "DATABASE_URL=postgresql://postgres:postgres@db:5432/scribe"
  ]
  volumes {
    host_path      = abspath(path.root)
    container_path = "/app"
  }
  networks_advanced {
    name = docker_network.private_network.name
  }
  depends_on = [docker_container.db]
}

# Use the locally built web application image
resource "docker_image" "web" {
  name = "scribe-web:latest"
}
