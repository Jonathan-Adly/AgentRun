import asyncio
import os
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from agentrun import AgentRun


class CodeSchema(BaseModel):
    code: str


class OutputSchema(BaseModel):
    output: str


app = FastAPI()

# allow all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/v1/health/", response_model=dict)
async def health():
    return {
        "status": "ok",
    }


@app.get("/")
async def redirect_docs():
    return RedirectResponse(url="/docs")


@app.post("/v1/run/", response_model=OutputSchema)
async def run_code(code_schema: CodeSchema):
    runner = AgentRun(
        container_name=os.environ.get("CONTAINER_NAME", "agentrun-api-python-runner-1"),
        cached_dependencies=["requests", "yfinance"],
        default_timeout=60 * 5,
    )
    python_code = code_schema.code
    with ThreadPoolExecutor() as executor:
        future = executor.submit(runner.execute_code_in_container, python_code)
        output = await asyncio.wrap_future(future)
    return OutputSchema(output=output)
