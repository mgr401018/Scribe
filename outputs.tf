output "web_app_url" {
  description = "URL for the web application"
  value       = "http://localhost:${var.web_port}"
}

output "database_url" {
  description = "Database connection URL"
  value       = "postgresql://${var.postgres_user}:${var.postgres_password}@localhost:${var.postgres_port}/${var.postgres_db}"
  sensitive   = true
}

output "container_info" {
  description = "Information about the containers"
  value = {
    web = {
      name = docker_container.web.name
      ip   = docker_container.web.network_data[0].ip_address
    }
    db = {
      name = docker_container.db.name
      ip   = docker_container.db.network_data[0].ip_address
    }
  }
}
