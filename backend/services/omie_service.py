import logging
import os
import unicodedata
from typing import Any
from uuid import uuid4

import requests
from dotenv import load_dotenv


load_dotenv()
logger = logging.getLogger(__name__)

OMIE_CONTA_PAGAR_URL = "https://app.omie.com.br/api/v1/financas/contapagar/"
OMIE_ANEXO_URL = "https://app.omie.com.br/api/v1/geral/anexo/"
OMIE_CLIENTES_URL = "https://app.omie.com.br/api/v1/geral/clientes/"
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
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else "N/A"
        response_body = ""
        if exc.response is not None:
            response_body = (exc.response.text or "").strip()
        if response_body:
            response_body = response_body[:1000]
        logger.error(
            "Erro HTTP da Omie. status_code=%s url=%s response_body=%s",
            status_code,
            url,
            response_body or "<vazio>",
        )
        raise RuntimeError(
            f"Erro HTTP na integracao com Omie: status={status_code} body={response_body or '<vazio>'}"
        ) from exc
    except requests.RequestException as exc:
        logger.exception("Erro HTTP ao chamar Omie.")
        raise RuntimeError(f"Erro HTTP na integracao com Omie: {exc}") from exc
    except ValueError as exc:
        logger.exception("Resposta invalida da Omie (nao JSON).")
        raise RuntimeError("Resposta invalida da Omie (JSON esperado).") from exc

    if isinstance(data, dict) and data.get("faultstring"):
        raise RuntimeError(f"Erro Omie: {data['faultstring']}")

    return data


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return ascii_text.strip().lower()


def _extract_client_list(data: dict[str, Any]) -> list[dict[str, Any]]:
    for key in (
        "clientes_cadastro_resumido",
        "clientes_cadastro",
        "lista_clientes",
        "clientes",
    ):
        entries = data.get(key)
        if isinstance(entries, list):
            return [item for item in entries if isinstance(item, dict)]
    return []


def buscar_fornecedor_por_nome(funcionario: str) -> int:
    app_key, app_secret = _get_credentials()
    target_name = _normalize_text(funcionario)
    if not target_name:
        raise RuntimeError("Nome do funcionario vazio para busca de fornecedor.")

    page = 1
    while True:
        payload = {
            "call": "ListarClientesResumido",
            "app_key": app_key,
            "app_secret": app_secret,
            "param": [
                {
                    "pagina": page,
                    "registros_por_pagina": 50,
                }
            ],
        }
        data = _post_omie(OMIE_CLIENTES_URL, payload)
        clients = _extract_client_list(data)

        for client in clients:
            names = [
                str(client.get("nome_fantasia", "")).strip(),
                str(client.get("razao_social", "")).strip(),
                str(client.get("cNome", "")).strip(),
                str(client.get("nome", "")).strip(),
            ]
            if any(_normalize_text(name) == target_name for name in names if name):
                code = client.get("codigo_cliente_fornecedor")
                if code is None:
                    break
                try:
                    return int(code)
                except (TypeError, ValueError) as exc:
                    raise RuntimeError(
                        "Fornecedor encontrado sem codigo_cliente_fornecedor valido."
                    ) from exc

        total_pages = int(data.get("total_de_paginas", page) or page)
        if page >= total_pages or not clients:
            break
        page += 1

    raise RuntimeError(
        f"Fornecedor/cliente nao encontrado na Omie para o funcionario '{funcionario}'."
    )


def create_expense(funcionario: str, despesa: dict[str, Any]) -> dict[str, Any]:
    app_key, app_secret = _get_credentials()
    codigo_fornecedor = buscar_fornecedor_por_nome(funcionario)

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
                "codigo_cliente_fornecedor": codigo_fornecedor,
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
