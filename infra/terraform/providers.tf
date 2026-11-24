provider "aws" {
  region = "us-east-1"

  # Requisito 8.2: todos los recursos etiquetables heredan estas tres etiquetas.
  default_tags {
    tags = {
      Environment = "prod"
      Project     = "monitorglucosa"
      Owner       = "ldordellygithub"
    }
  }
}
