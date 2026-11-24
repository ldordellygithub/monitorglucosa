"""Configuración tipada (pydantic-settings). Solo la lee `main.py`.

Todo viene de variables de entorno en UPPER_SNAKE_CASE. Un error de validación nombra
la variable y el problema, nunca el valor recibido (`hide_input_in_errors`).

En `prod` la API se autentica con IAM y con el autorizador JWT de API Gateway, así que
`DATABASE_PASSWORD` y las variables `LOCAL_*` están prohibidas. En `local` y `test` son
obligatorias: sustituyen a IAM y a Cognito.
"""

from typing import Annotated, Any, Literal, Self

from pydantic import Field, HttpUrl, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Variable de entorno -> atributo de `Settings`.
# Prohibidas en `prod`, obligatorias en el resto de entornos.
LOCAL_ONLY_VARIABLES = {
    "DATABASE_PASSWORD": "database_password",
    "LOCAL_JWT_ISSUER": "local_jwt_issuer",
    "LOCAL_JWKS_URL": "local_jwks_url",
    "LOCAL_JWT_CLIENT_IDS": "local_jwt_client_ids",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=True, hide_input_in_errors=True)

    environment: Literal["local", "test", "prod"] = Field(
        validation_alias="ENVIRONMENT"
    )

    database_host: str = Field(min_length=1, validation_alias="DATABASE_HOST")
    database_port: int = Field(ge=1, le=65535, validation_alias="DATABASE_PORT")
    database_name: str = Field(min_length=1, validation_alias="DATABASE_NAME")
    database_user: str = Field(min_length=1, validation_alias="DATABASE_USER")
    database_connect_timeout_s: int = Field(
        default=20, ge=1, le=25, validation_alias="DATABASE_CONNECT_TIMEOUT_S"
    )

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO", validation_alias="LOG_LEVEL"
    )

    database_password: SecretStr | None = Field(
        default=None, validation_alias="DATABASE_PASSWORD"
    )
    local_jwt_issuer: str | None = Field(
        default=None, min_length=1, validation_alias="LOCAL_JWT_ISSUER"
    )
    local_jwks_url: HttpUrl | None = Field(
        default=None, validation_alias="LOCAL_JWKS_URL"
    )
    # Lista separada por comas (web,collector), no JSON: más cómoda en un .env.
    local_jwt_client_ids: Annotated[list[str] | None, NoDecode] = Field(
        default=None, min_length=1, validation_alias="LOCAL_JWT_CLIENT_IDS"
    )

    @field_validator("local_jwt_client_ids", mode="before")
    @classmethod
    def _split_client_ids(cls, value: object) -> object:
        if isinstance(value, str):
            if value.lstrip().startswith("["):
                raise ValueError("debe ser una lista separada por comas, no JSON")
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("database_password", mode="after")
    @classmethod
    def _password_not_empty(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not value.get_secret_value():
            raise ValueError("no puede estar vacía")
        return value

    @model_validator(mode="before")
    @classmethod
    def _reject_local_only_variables_in_prod(cls, data: Any) -> Any:
        """Falla en `prod` si hay alguna variable local, sea cual sea su valor."""
        if isinstance(data, dict) and data.get("ENVIRONMENT") == "prod":
            present = [name for name in LOCAL_ONLY_VARIABLES if name in data]
            if present:
                raise ValueError(f"No se admiten en prod: {', '.join(present)}")
        return data

    @model_validator(mode="after")
    def _require_local_only_variables_outside_prod(self) -> Self:
        if self.environment != "prod":
            missing = [
                name
                for name, attribute in LOCAL_ONLY_VARIABLES.items()
                if getattr(self, attribute) is None
            ]
            if missing:
                raise ValueError(
                    f"Obligatorias en {self.environment}: {', '.join(missing)}"
                )
        return self
