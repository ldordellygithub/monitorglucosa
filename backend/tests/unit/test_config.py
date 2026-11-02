"""`config.Settings`: variables obligatorias, prohibidas y errores sin valores."""

import pytest
from pydantic import SecretStr, ValidationError

from tests.unit.settings_env import (
    LOCAL_ONLY_VARIABLES,
    SHARED_ENV,
    build_settings,
    local_env,
    prod_env,
)

REQUIRED_EVERYWHERE = ["ENVIRONMENT", *SHARED_ENV]


def failure_of(env: dict[str, str]) -> str:
    """Mensaje de la validación que falla al construir `Settings` con `env`."""
    with pytest.raises(ValidationError) as caught:
        build_settings(env)
    return str(caught.value)


@pytest.mark.req("fase-1a:1.4")
@pytest.mark.parametrize("environment", ["local", "test"])
def test_settings_local_y_test_con_todas_las_variables_carga_valores_tipados(
    environment: str,
) -> None:
    settings = build_settings(local_env(environment))

    assert settings.environment == environment
    assert settings.database_port == 5432
    assert settings.database_connect_timeout_s == 20
    assert settings.log_level == "INFO"
    assert isinstance(settings.database_password, SecretStr)
    assert settings.local_jwt_client_ids == ["web", "collector"]
    assert (
        str(settings.local_jwks_url) == "http://jwt-issuer:9000/.well-known/jwks.json"
    )


@pytest.mark.req("fase-1a:1.4")
def test_settings_lista_de_clientes_ignora_espacios_y_elementos_vacios() -> None:
    env = {**local_env(), "LOCAL_JWT_CLIENT_IDS": " web , collector ,, "}

    assert build_settings(env).local_jwt_client_ids == ["web", "collector"]


@pytest.mark.req("fase-1a:1.4")
@pytest.mark.parametrize("variable", REQUIRED_EVERYWHERE)
@pytest.mark.parametrize("environment", ["local", "test", "prod"])
def test_settings_sin_variable_obligatoria_falla_nombrandola(
    variable: str, environment: str
) -> None:
    env = prod_env() if environment == "prod" else local_env(environment)
    del env[variable]

    message = failure_of(env)

    assert variable in message
    for name, value in env.items():
        if name != "ENVIRONMENT" and len(value) >= 4:
            assert value not in message


@pytest.mark.req("fase-1a:1.4")
@pytest.mark.parametrize("variable", LOCAL_ONLY_VARIABLES)
@pytest.mark.parametrize("environment", ["local", "test"])
def test_settings_sin_variable_local_fuera_de_prod_falla_nombrandola(
    variable: str, environment: str
) -> None:
    env = local_env(environment)
    del env[variable]

    message = failure_of(env)

    assert variable in message
    assert environment in message


@pytest.mark.req("fase-1a:1.4")
def test_settings_en_local_sin_ninguna_variable_local_las_nombra_todas() -> None:
    env = {"ENVIRONMENT": "local", **SHARED_ENV}

    message = failure_of(env)

    assert all(variable in message for variable in LOCAL_ONLY_VARIABLES)


@pytest.mark.req("fase-1a:1.4")
def test_settings_prod_valida_carga_sin_variables_locales() -> None:
    settings = build_settings(prod_env())

    assert settings.environment == "prod"
    assert settings.database_password is None
    assert settings.local_jwt_issuer is None
    assert settings.local_jwks_url is None
    assert settings.local_jwt_client_ids is None


@pytest.mark.req("fase-1a:1.4")
@pytest.mark.parametrize(
    ("variable", "invalid"),
    [
        ("ENVIRONMENT", "staging"),
        ("DATABASE_PORT", "0"),
        ("DATABASE_PORT", "65536"),
        ("DATABASE_PORT", "puerto-secreto"),
        ("DATABASE_HOST", ""),
        ("DATABASE_CONNECT_TIMEOUT_S", "0"),
        ("DATABASE_CONNECT_TIMEOUT_S", "26"),
        ("LOG_LEVEL", "TRACE"),
        ("LOCAL_JWKS_URL", "no-es-una-url"),
        ("LOCAL_JWT_ISSUER", ""),
        ("LOCAL_JWT_CLIENT_IDS", " , ,"),
        ("LOCAL_JWT_CLIENT_IDS", '["web","collector"]'),
        ("DATABASE_PASSWORD", ""),
    ],
)
def test_settings_valor_invalido_falla_nombrando_la_variable_sin_mostrar_el_valor(
    variable: str, invalid: str
) -> None:
    env = {**local_env(), variable: invalid}

    message = failure_of(env)

    assert variable in message
    if len(invalid) >= 4:  # un valor más corto podría coincidir con el texto del error
        assert invalid not in message


@pytest.mark.req("fase-1a:1.4")
@pytest.mark.parametrize(("timeout", "expected"), [("1", 1), ("25", 25)])
def test_settings_timeout_de_conexion_acepta_los_limites(
    timeout: str, expected: int
) -> None:
    env = {**local_env(), "DATABASE_CONNECT_TIMEOUT_S": timeout}

    assert build_settings(env).database_connect_timeout_s == expected


@pytest.mark.req("fase-1a:1.4")
def test_settings_nombres_en_minusculas_no_cuentan_como_variables() -> None:
    env = {name.lower(): value for name, value in local_env().items()}

    message = failure_of(env)

    assert "ENVIRONMENT" in message


@pytest.mark.req("fase-1a:1.4")
def test_settings_ignora_variables_ajenas_del_entorno() -> None:
    env = {**local_env(), "PATH": "/usr/bin", "HOME": "/root"}

    assert build_settings(env).environment == "local"


@pytest.mark.req("fase-1a:3.4")
@pytest.mark.parametrize("variable", LOCAL_ONLY_VARIABLES)
def test_settings_prod_con_variable_local_falla_nombrandola_sin_mostrar_el_valor(
    variable: str,
) -> None:
    marker = "valor~marcador-de-prueba"
    env = {**prod_env(), variable: marker}

    message = failure_of(env)

    assert variable in message
    assert marker not in message


@pytest.mark.req("fase-1a:3.4")
@pytest.mark.parametrize("variable", LOCAL_ONLY_VARIABLES)
def test_settings_prod_con_variable_local_vacia_tambien_falla(variable: str) -> None:
    env = {**prod_env(), variable: ""}

    assert variable in failure_of(env)


@pytest.mark.req("fase-1a:3.4")
def test_settings_prod_con_todas_las_variables_locales_las_nombra_todas() -> None:
    env = {**local_env(), "ENVIRONMENT": "prod"}

    message = failure_of(env)

    assert all(variable in message for variable in LOCAL_ONLY_VARIABLES)
