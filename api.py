import asyncio
import io
import logging
import os
from base64 import b64encode
from glob import glob
from time import time

import numpy as np
from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image

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
for image_file in glob(os.path.join("data", "*.png")):
    logger.info("Loading %s", image_file)
    with Image.open(image_file) as img:
        new_size = (img.size[0] // resize, img.size[1] // resize)
        logger.info("Resizing by %d (from %s to %s)", resize, img.size, new_size)
        image = img.resize(new_size)
        images.append(np.swapaxes(image, 0, 1))

columns = int(os.environ["COLUMNS"])
rows = int(os.environ["ROWS"])
image_states = np.random.randint(len(images), size=(columns, rows)).astype(np.uint8)
image_changes = asyncio.Queue()


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


@api.get("/image/column/{column}/row/{row}/state/toggle")
async def toggle_image_tile(column: int, row: int) -> str:
    image_states[column, row] = (image_states[column, row] + 1) % len(images)
    await image_changes.put((column, row))
    logger.info("Set %d/%d to %d", column, row, image_states[column, row])
    return "ok"


@api.get("/image/column/{column}/row/{row}")
def get_image_tile(column: int, row: int) -> StreamingResponse:
    return image_response(encode_image(_get_image_tile(column, row)))


@app.websocket("/ws")
async def subscribe(websocket: WebSocket) -> StreamingResponse:
    await websocket.accept()
    for column in range(columns):
        for row in range(rows):
            await image_changes.put((column, row))
    while True:
        column, row = await image_changes.get()
        logger.info("Updating %d/%d with %d", column, row, image_states[column, row])
        await websocket.send_json(
            {
                "column": column,
                "row": row,
                "state": image_states[column, row].item(),
                "image": b64encode(encode_image(_get_image_tile(column, row)).read()).decode("utf-8"),
            }
        )


@api.get("/image/full")
def get_full_image() -> StreamingResponse:
    return image_response(encode_image(_get_full_image()))
