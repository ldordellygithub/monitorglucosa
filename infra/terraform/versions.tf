terraform {
  required_version = "~> 1.16.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.69.1"
    }
  }

  # Estado remoto en S3 cifrado con bloqueo nativo (sin DynamoDB; Requisito 8.1, D1).
  # El nombre del bucket se pasa por `-backend-config="bucket=$TF_STATE_BUCKET"` para no
  # publicar el ID de cuenta en el repositorio (ADR 0008, NFR-5).
  backend "s3" {
    region       = "us-east-1"
    key          = "prod/terraform.tfstate"
    encrypt      = true
    use_lockfile = true
  }
}
