"""Property 5: la configuración de `prod` es cerrada."""

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from tests.unit.settings_env import (
    LOCAL_ONLY_VARIABLES,
    SHARED_ENV,
    build_settings,
)

# El prefijo `valor~` no aparece en ningún mensaje de error: si lo hace, es que el
# mensaje repite lo recibido. El resto del valor es arbitrario, aunque no sea válido
# (una URL rota, un puerto absurdo): `prod` debe rechazar la variable igualmente.
VALUES = st.text(
    alphabet=st.characters(min_codepoint=32, max_codepoint=126),
    min_size=1,
    max_size=40,
).map(lambda text: f"valor~{text}")

# Variables locales: al menos una está siempre presente.
LOCAL_ONLY_SUBSETS = st.dictionaries(
    keys=st.sampled_from(LOCAL_ONLY_VARIABLES),
    values=VALUES,
    min_size=1,
)

# El resto de la configuración puede estar completa, incompleta, o con valores
# absurdos: «cualquier combinación» no deja nada fijo salvo ENVIRONMENT = prod.
OTHER_VARIABLES = st.dictionaries(
    keys=st.sampled_from(
        [*SHARED_ENV, "DATABASE_CONNECT_TIMEOUT_S", "LOG_LEVEL", "PATH", "HOME"]
    ),
    values=VALUES,
)


@pytest.mark.req("fase-1a:1.4", "fase-1a:3.4")
@given(local_only=LOCAL_ONLY_SUBSETS, others=OTHER_VARIABLES)
def test_settings_prod_con_cualquier_variable_local_falla_sin_revelar_valores(
    local_only: dict[str, str], others: dict[str, str]
) -> None:
    env = {**others, **local_only, "ENVIRONMENT": "prod"}

    with pytest.raises(ValidationError) as caught:
        build_settings(env)

    message = str(caught.value)
    assert all(variable in message for variable in local_only)
    values = [value for name, value in env.items() if name != "ENVIRONMENT"]
    assert not any(value in message for value in values)
