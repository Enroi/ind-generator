import os

import uvicorn
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
import fastapi_structured_logging

from controllers import generator as generator_controller


log_level = os.getenv("LOG_LEVEL","INFO")
fastapi_structured_logging.setup_logging(json_logs = False, log_level = log_level)
logger = fastapi_structured_logging.get_logger()

app = FastAPI(
    swagger_ui_parameters = {
        "filter": True,
        "operationsSorter": "alpha",
        "tagsSorter": "alpha",
        "displayRequestDuration": True,
    },
    description = """
        Генератор тестовы данных
        """,
    version = "1.0",
    title = "Ind Generator",
    summary = "Генератор тестовы данных",
    debug = os.getenv("FASTAPI_DEBUG", "false") == "true",
)
app.add_middleware(fastapi_structured_logging.AccessLogMiddleware)

@app.get(path = "/", response_class = RedirectResponse)
async def root():
    return "/docs"

app.include_router(generator_controller.router)

if __name__ == '__main__':
    port = os.getenv("FAST_API_PORT", 8000)
    logger.info(f"Будет запущен FastAPI сервер на порту {port}")
    uvicorn.run(app, port = port)
