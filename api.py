import io
import logging
import os
from glob import glob
from time import time

import numpy as np
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
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
image_states = np.random.randint(len(images), size=(columns, rows))


def _get_image_tile(column: int, row: int):
    logger.info("Getting tile %d/%d", column, row)
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
    logger.info("Encoding image")
    output = io.BytesIO()
    image.save(output, format="PNG")
    output.seek(0)
    return StreamingResponse(output, media_type="image/png")


@app.get("/")
def home():
    return RedirectResponse("/static/index.html")


@api.get("/image/column/{column}/row/{row}")
def get_image_tile(column: int, row: int) -> StreamingResponse:
    return encode_image(_get_image_tile(column, row))


@api.get("/image/full")
def get_full_image() -> StreamingResponse:
    return encode_image(_get_full_image())
