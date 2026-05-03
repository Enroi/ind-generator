import asyncio
import os
from asyncio import Semaphore

import aiohttp
from fastapi import APIRouter, Query
import fastapi_structured_logging
from typing import Annotated, Any


router = APIRouter()
logger = fastapi_structured_logging.get_logger()


@router.post("/api/generate_processes")
async def generate(
        generate_processes_count: Annotated[int, Query(description = "Количество генерируемых процессов", ge = 1)] = 1,
):
    logger.info(f"Начинаем создание: {generate_processes_count} процессов")
    semaphore = Semaphore(int(os.getenv("THREADS_COUNT", "20")))
    tasks = []
    async with aiohttp.ClientSession() as session:
        for i in range(generate_processes_count):
            tasks.append(send_one_process(semaphore, i, session))
        await asyncio.gather(*tasks)
    logger.info("Задачи на создание процессов отправлены")

async def send_one_process(semaphore: Semaphore, id, session):
    async with semaphore:
        await session.post(
                url = os.getenv("URL_FOR_GENERATE_PROCESSES"),
                json = {
                    "resource": "ресурс 1",
                    "request-id": id,
                    "status": "INITIAL"
                }
        )