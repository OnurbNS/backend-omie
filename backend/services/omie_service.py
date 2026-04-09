import logging
import os
from typing import Any
from uuid import uuid4

import requests
from dotenv import load_dotenv


load_dotenv()
logger = logging.getLogger(__name__)

OMIE_CONTA_PAGAR_URL = "https://app.omie.com.br/api/v1/financas/contapagar/"
OMIE_ANEXO_URL = "https://app.omie.com.br/api/v1/geral/anexo/"
OMIE_CATEGORIA_REEMBOLSO = "1.01.01"


def _get_credentials() -> tuple[str, str]:
    app_key = os.getenv("OMIE_APP_KEY")
    app_secret = os.getenv("OMIE_APP_SECRET")

    if not app_key or not app_secret:
        raise RuntimeError(
            "Credenciais da Omie ausentes. Defina OMIE_APP_KEY e OMIE_APP_SECRET."
        )

    return app_key, app_secret


def _post_omie(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        logger.exception("Erro HTTP ao chamar Omie.")
        raise RuntimeError(f"Erro HTTP na integracao com Omie: {exc}") from exc
    except ValueError as exc:
        logger.exception("Resposta invalida da Omie (nao JSON).")
        raise RuntimeError("Resposta invalida da Omie (JSON esperado).") from exc

    if isinstance(data, dict) and data.get("faultstring"):
        raise RuntimeError(f"Erro Omie: {data['faultstring']}")

    return data


def create_expense(funcionario: str, despesa: dict[str, Any]) -> dict[str, Any]:
    app_key, app_secret = _get_credentials()

    payload = {
        "call": "IncluirContaPagar",
        "app_key": app_key,
        "app_secret": app_secret,
        "param": [
            {
                "codigo_lancamento_integracao": str(uuid4()),
                "data_vencimento": despesa["data"],
                "valor_documento": float(despesa["valor"]),
                "codigo_categoria": OMIE_CATEGORIA_REEMBOLSO,
                "observacao": f"Reembolso - {funcionario}",
            }
        ],
    }

    data = _post_omie(OMIE_CONTA_PAGAR_URL, payload)

    codigo_lancamento = data.get("codigo_lancamento")
    if not codigo_lancamento:
        raise RuntimeError(
            "Resposta da Omie nao contem codigo_lancamento para a conta a pagar."
        )

    return {
        "codigo_lancamento": codigo_lancamento,
        "omie_response": data,
    }


def attach_file(codigo_lancamento: str, base64_file: str) -> dict[str, Any]:
    app_key, app_secret = _get_credentials()

    payload = {
        "call": "IncluirAnexo",
        "app_key": app_key,
        "app_secret": app_secret,
        "param": [
            {
                "cCodIntAnexo": str(codigo_lancamento),
                "cNomeArquivo": "comprovante.jpg",
                "cArquivo": base64_file,
            }
        ],
    }

    data = _post_omie(OMIE_ANEXO_URL, payload)
    return data
