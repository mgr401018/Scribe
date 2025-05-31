variable "web_port" {
  description = "Port for the web application"
  type        = number
  default     = 5000
}

variable "postgres_user" {
  description = "PostgreSQL username"
  type        = string
  default     = "postgres"
}

variable "postgres_password" {
  description = "PostgreSQL password"
  type        = string
  default     = "postgres"
}

variable "postgres_db" {
  description = "PostgreSQL database name"
  type        = string
  default     = "scribe"
}

variable "postgres_port" {
  description = "Port for PostgreSQL"
  type        = number
  default     = 5434
}
