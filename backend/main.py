import logging
import os
from datetime import datetime
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from services.file_service import download_file_as_base64
from services.omie_service import attach_file, create_expense


load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Reembolso Omie API", version="1.0.0")

# Front em outra origem (ex.: Vite/Lovable em localhost:5173) precisa de CORS.
# Defina FRONTEND_ORIGINS=http://localhost:5173,http://127.0.0.1:5173 no .env ou use o padrao abaixo.
_origins_raw = os.getenv(
    "FRONTEND_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000",
)
_allowed_origins = [o.strip() for o in _origins_raw.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class DespesaRequest(BaseModel):
    data: str
    valor: float = Field(..., gt=0)
    descricao: str = Field(..., min_length=1)
    comprovante: str | None = None

    @field_validator("data")
    @classmethod
    def validate_data(cls, value: str) -> str:
        try:
            datetime.strptime(value, "%d/%m/%Y")
        except ValueError as exc:
            raise ValueError("data deve estar no formato DD/MM/YYYY") from exc
        return value


class CreateExpenseRequest(BaseModel):
    funcionario: str = Field(..., min_length=1)
    despesas: list[DespesaRequest] = Field(..., min_length=1)


class ExpenseResult(BaseModel):
    status: str
    data: dict[str, Any]
    error: str | None


class CreateExpenseResponse(BaseModel):
    success: bool
    processed: int
    results: list[ExpenseResult]


@app.get("/health")
def health() -> dict[str, str]:
    """Health check para plataformas de hospedagem (ex.: Render)."""
    return {"status": "ok"}


@app.post("/api/omie/create-expense", response_model=CreateExpenseResponse)
def create_omie_expense(payload: CreateExpenseRequest) -> CreateExpenseResponse:
    results: list[ExpenseResult] = []

    for despesa in payload.despesas:
        try:
            logger.info("Processando despesa: %s", despesa.descricao)
            omie_expense = create_expense(
                funcionario=payload.funcionario,
                despesa=despesa.model_dump(),
            )

            response_data: dict[str, Any] = {
                "funcionario": payload.funcionario,
                "despesa": despesa.model_dump(),
                "codigo_lancamento": omie_expense["codigo_lancamento"],
                "omie_expense_response": omie_expense["omie_response"],
            }

            if despesa.comprovante:
                base64_file = download_file_as_base64(despesa.comprovante)
                anexo_response = attach_file(
                    codigo_lancamento=str(omie_expense["codigo_lancamento"]),
                    base64_file=base64_file,
                )
                response_data["omie_attachment_response"] = anexo_response

            results.append(
                ExpenseResult(
                    status="success",
                    data=response_data,
                    error=None,
                )
            )
        except Exception as exc:
            logger.exception("Falha ao processar despesa '%s'.", despesa.descricao)
            results.append(
                ExpenseResult(
                    status="error",
                    data={
                        "funcionario": payload.funcionario,
                        "despesa": despesa.model_dump(),
                    },
                    error=str(exc),
                )
            )

    success = all(result.status == "success" for result in results)
    return CreateExpenseResponse(
        success=success,
        processed=len(results),
        results=results,
    )


# Executar localmente:
# uvicorn main:app --reload
