import base64
import logging
from urllib.parse import urlparse

import requests


logger = logging.getLogger(__name__)


def download_file_as_base64(url: str) -> str:
    """
    Download a file from a URL and return it encoded in base64.
    Raises exceptions if download fails.
    """
    if not url:
        raise ValueError("URL do comprovante nao informada.")

    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("URL do comprovante invalida.")

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.exception("Erro ao baixar arquivo de comprovante.")
        raise RuntimeError(f"Falha ao baixar comprovante: {exc}") from exc

    if not response.content:
        raise RuntimeError("Arquivo de comprovante vazio.")

    encoded = base64.b64encode(response.content).decode("utf-8")
    return encoded
