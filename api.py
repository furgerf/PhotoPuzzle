import asyncio
import io
import logging
import os
from base64 import b64encode
from glob import glob
from random import random
from threading import Thread
from time import sleep, time
from typing import Optional, Tuple

import numpy as np
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image
from websockets.exceptions import ConnectionClosedOK

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(funcName)s:%(lineno)d: %(message)s"
)
logger = logging.getLogger("api")

app = FastAPI()
api = FastAPI()
app.mount("/static", StaticFiles(directory="static", html=True), name="static")
app.mount("/api", api)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
)

templates = Jinja2Templates(directory="templates")


@app.middleware("http")
async def log_process_time(request: Request, call_next):
    start_time = time()
    response = await call_next(request)
    logger.info("Request to %s handled in %.1fms", request.url, 1000 * (time() - start_time))
    return response


resize = int(os.environ["RESIZE"])

images = []
for image_file in glob(os.path.join("data", "*")):
    logger.info("Loading %s", image_file)
    with Image.open(image_file) as img:
        new_size = (img.size[0] // resize, img.size[1] // resize)
        logger.info("Resizing by %d (from %s to %s)", resize, img.size, new_size)
        image = img.resize(new_size)
        images.append(np.swapaxes(image, 0, 1))

columns = int(os.environ["COLUMNS"])
rows = int(os.environ["ROWS"])
target = int(os.environ["TARGET"])
if target < 0:
    target = np.random.randint(len(images))
image_states = np.random.randint(len(images), size=(columns, rows)).astype(np.uint8)
tile_assignments = np.ones_like(image_states).astype(bool)
image_changes = asyncio.Queue()

inertia = 10
loop = asyncio.get_event_loop()


def run_fake_user(column, row):
    if not tile_assignments[column, row]:
        logger.info("%d/%d has been taken over by a user", column, row)
        return

    def handle_toggle(task):
        state = task.result()
        if state == target and inertia > 30:
            logger.info("%d/%d has been completed", column, row)
            return

        multiplier = 6 if state == target else 0.5
        loop.call_later(inertia * multiplier * random(), run_fake_user, column, row)

    loop.create_task(toggle_image_tile(column, row)).add_done_callback(handle_toggle)


for column in range(columns):
    for row in range(rows):
        loop.call_later(1 + 10 * random(), run_fake_user, column, row)


def increase_inertia():
    global inertia
    inertia += 1
    loop.call_later(1, increase_inertia)


increase_inertia()


def _get_image_tile(column: int, row: int):
    image = images[image_states[column, row]]
    column_width = image.shape[0] // columns
    row_height = image.shape[1] // rows
    return image[column * column_width : (column + 1) * column_width, row * row_height : (row + 1) * row_height]


def _get_full_image():
    image_array = np.empty_like(images[0])
    column_width = image_array.shape[0] // columns
    row_height = image_array.shape[1] // rows
    for column in range(columns):
        for row in range(rows):
            image_array[
                column * column_width : (column + 1) * column_width, row * row_height : (row + 1) * row_height
            ] = _get_image_tile(column, row)
    return image_array


def encode_image(image_array):
    image = Image.fromarray(np.swapaxes(image_array, 0, 1), mode="RGB")
    output = io.BytesIO()
    image.save(output, format="PNG")
    output.seek(0)
    return output


def image_response(output):
    return StreamingResponse(output, media_type="image/png")


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "columns": columns, "rows": rows})


@app.get("/client", response_class=HTMLResponse)
def client(request: Request):
    return templates.TemplateResponse("client.html", {"request": request, "columns": columns, "rows": rows})


@api.get("/tile-assignment")
def get_tile_assignment(_: Request) -> dict:
    tile = _get_tile_assignment()
    return {"column": tile[0], "row": tile[1]}


def _get_tile_assignment() -> Tuple[int, int]:
    available_tiles = np.stack(np.where(tile_assignments))
    tile = available_tiles[:, np.random.randint(available_tiles.shape[1])].tolist()
    tile_assignments[tuple(tile)] = False
    logger.info("Assigned %d/%d to (human) client", tile[0], tile[1])
    return tile


def _free_tile_assignment(column: int, row: int) -> None:
    tile_assignments[column, row] = True
    loop.call_later(1 + 10 * random(), run_fake_user, column, row)
    logger.info("Replaced %d/%d with bot", column, row)


@api.put("/image/column/{column}/row/{row}/state/toggle")
async def toggle_image_tile(column: int, row: int) -> int:
    image_states[column, row] = (image_states[column, row] + 1) % len(images)
    await image_changes.put((column, row))
    logger.info("Set %d/%d to %d", column, row, image_states[column, row])
    return image_states[column, row].item()


@api.get("/image/column/{column}/row/{row}")
def get_image_tile(column: int, row: int) -> StreamingResponse:
    return image_response(encode_image(_get_image_tile(column, row)))


@app.websocket("/ws")
async def subscribe(websocket: WebSocket) -> None:
    await websocket.accept()
    logger.info("WS connected")
    while not image_changes.empty():
        image_changes.get_nowait()
    for column in range(columns):
        for row in range(rows):
            await image_changes.put((column, row))

    while True:
        try:
            column, row = await asyncio.wait_for(image_changes.get(), timeout=2)
        except asyncio.TimeoutError:
            # there's nothing to send - check if we're still connected
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
                logger.error("Unexpectedly received something on WS")
            except asyncio.TimeoutError:
                # still connected
                pass
            except (WebSocketDisconnect, ConnectionClosedOK):
                logger.warning("WS disconnected")
                break
            continue

        logger.debug("Updating %d/%d with %d", column, row, image_states[column, row])
        try:
            await websocket.send_json(
                {
                    "column": column,
                    "row": row,
                    "state": image_states[column, row].item(),
                    "image": b64encode(encode_image(_get_image_tile(column, row)).read()).decode("utf-8"),
                }
            )
        except (WebSocketDisconnect, ConnectionClosedOK):
            # we probably received an update that's meant for the new connection, re-queue
            logger.warning("WS disconnected, requeueing %d/%d", column, row)
            await image_changes.put((column, row))
            break


@app.websocket("/ws-client")
async def subscribe_client(websocket: WebSocket) -> None:
    await websocket.accept()
    logger.info("WS-client connected")
    column, row = _get_tile_assignment()

    try:
        while True:
            command = await websocket.receive_text()
            if command == "toggle":
                await toggle_image_tile(column, row)
            elif command == "change-tile":
                logger.info("Client requested new tile")
                _free_tile_assignment(column, row)
                column, row = _get_tile_assignment()
            else:
                logger.warning("Received unknown command %s", command)
    except (WebSocketDisconnect, ConnectionClosedOK):
        logger.warning("WS disconnected")
        _free_tile_assignment(column, row)


@api.get("/image/full")
def get_full_image() -> StreamingResponse:
    return image_response(encode_image(_get_full_image()))
