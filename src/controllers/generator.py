import asyncio
import base64
from asyncio import Semaphore
import os
import time

import aiohttp
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives._serialization import Encoding, PublicFormat
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from dotenv import load_dotenv

from lxml import etree
import aiofiles
import aiofiles.os
from typing import Annotated, Any
import yaml

from fastapi import APIRouter, Query
import fastapi_structured_logging

load_dotenv()

logger = fastapi_structured_logging.get_logger()

router = APIRouter()


@router.post("/api/generate")
async def generate(
        generate_files_count: Annotated[int, Query(description = "Количество генерируемых файлов", ge = 1)] = 1,
) -> list[str]:
    logger.info("Отправка сертификата для будущих проверок. Эмуляция добавления сертификата в доверенное хранилище сертификатов")
    await send_certificate_for_auth()
    logger.info(f"Начинаем создание: {generate_files_count} файлов")
    results = []
    await work_with_generation(generate_files_count, results)
    await work_with_sending(results)
    return results


async def send_certificate_for_auth():
    async with aiofiles.open(file = os.getenv("PUBLIC_KEY_FILE"), mode = 'rb') as file:
        pem_file_content = await file.read(),
        public_key = serialization.load_pem_public_key(
            pem_file_content[0],
        )
    if not isinstance(public_key, rsa.RSAPublicKey):
        raise RuntimeError(f"Файл {os.getenv("PUBLIC_KEY_FILE")} не может быть распознан как хранилище открытого ключа")
    certificate = public_key.public_bytes(
        Encoding.PEM,
        PublicFormat.SubjectPublicKeyInfo
    )
    async with aiohttp.ClientSession() as session:
        async with session.post(
                url = os.getenv("URL_FOR_SEND_CERTIFICATE"),
                data = certificate,
        ) as resp:
            resp.raise_for_status()


async def work_with_sending(results: list[Any]):
    started = time.perf_counter()
    sent_files = await send_files()
    finished = time.perf_counter()
    message_sent = f"Отправлено: {sent_files} файлов. Затрачено времени {finished - started:.6f}"
    results.append(message_sent)
    logger.info(message_sent)


async def work_with_generation(generate_files_count: int, results: list[Any]):
    started = time.perf_counter()
    current_generated_file_index = await generate_files(generate_files_count)
    finished = time.perf_counter()
    message_created = f"Создано {current_generated_file_index} файлов. Затрачено времени {finished - started:.6f}"
    results.append(message_created)
    logger.info(message_created)


async def send_files():
    files_dirty = await aiofiles.os.scandir("temps")
    files = [file for file in files_dirty if
             file.name.lower().endswith(".xml") and file.name.lower().startswith("accounts_oner_")]
    files_dirty.close()
    semaphore = Semaphore(int(os.getenv("THREADS_COUNT", "10")))
    async with aiohttp.ClientSession() as session:
        tasks = [
            send_one_file(semaphore, session, file)
            for file in files
        ]
        results = await asyncio.gather(*tasks)
        return len(results)


async def send_one_file(semaphore: Semaphore, session: aiohttp.client.ClientSession, file):
    async with semaphore:
        async with aiofiles.open(file, 'rb') as file:
            file_content = await file.read()
        async with aiofiles.open(file = os.getenv("PRIVATE_KEY_FILE"), mode = 'rb') as file:
            pem_file_content = await file.read(),
            private_key = serialization.load_pem_private_key(
                pem_file_content[0],
                password = None,
            )
        if not isinstance(private_key, rsa.RSAPrivateKey):
            raise RuntimeError(f"Файл {os.getenv("PRIVATE_KEY_FILE")} не может быть распознан как хранилище закрытого ключа")
        async with aiofiles.open(file = os.getenv("PUBLIC_KEY_FILE"), mode = 'rb') as file:
            pem_file_content = await file.read(),
            public_key = serialization.load_pem_public_key(
                pem_file_content[0],
            )
        if not isinstance(public_key, rsa.RSAPublicKey):
            raise RuntimeError(f"Файл {os.getenv("PUBLIC_KEY_FILE")} не может быть распознан как хранилище открытого ключа")
        signature = private_key.sign(
            file_content,
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        certificate_in_header = public_key.public_bytes(
            Encoding.PEM,
            PublicFormat.SubjectPublicKeyInfo
        )
        i: int = 0
        while i < 3:
            async with session.post(
                    url = os.getenv("URL_FOR_SEND_FILE"),
                    data = file_content,
                    headers = {
                        "Certificate": base64.b64encode(certificate_in_header).decode('ascii'),
                        "Message-hash": base64.b64encode(signature).decode('ascii'),
                    }
            ) as resp:
                resp.raise_for_status()
                match resp.status:
                    case 403:
                        raise RuntimeError("Ошибка авторизации")
                    case 200:
                        answer = await resp.read()
                        logger.info(f"Ответ: {answer}")
                        i = 9_999_999
                    case 202:
                        logger.info("Запрос в процессе обработки")
                        await asyncio.sleep(1)
                        i += 1


async def generate_files(generate_files_count: int) -> int:
    xml_request_root, yaml_accounts = await prepare_configs()
    results = await generation_worker(generate_files_count, xml_request_root, yaml_accounts)
    return len(results)


async def prepare_configs() -> tuple[Any, Any]:
    async def load_xml():
        async with aiofiles.open('data/statement-request-one.xml', 'r', encoding = 'utf-8') as f:
            return await f.read()

    async def load_yaml():
        async with aiofiles.open('data/accounts.yml', 'r', encoding = 'utf-8') as f:
            return await f.read()

    xml_content, accounts_content = await asyncio.gather(load_xml(), load_yaml())
    xml_request_root = etree.fromstring(xml_content.encode('utf-8'))
    yaml_accounts = yaml.safe_load(accounts_content)
    return xml_request_root, yaml_accounts


async def generation_worker(generate_files_count: int, xml_request_root, yaml_accounts) -> list[Any]:
    current_generated_file_index: int = 0
    semaphore = Semaphore(int(os.getenv("THREADS_COUNT", "10")))
    tasks = []
    while current_generated_file_index < generate_files_count:
        for account_code in yaml_accounts:
            for node in xml_request_root:
                if current_generated_file_index >= generate_files_count:
                    break
                node.set("number", account_code)
            if current_generated_file_index >= generate_files_count:
                break
            current_generated_file_index += 1
            xml_string = etree.tostring(xml_request_root, encoding = 'utf-8', pretty_print = True).decode('utf-8')
            tasks.append(save_one_file(current_generated_file_index, xml_string, semaphore))
    results = await asyncio.gather(*tasks)
    return results


async def save_one_file(current_generated_file_index: int, xml_string: str, semaphore: Semaphore):
    async with semaphore:
        filename = f'temps/accounts_oner_{current_generated_file_index}.xml'
        async with aiofiles.open(filename, 'w', encoding = 'utf-8') as out_file:
            await out_file.write(xml_string)
