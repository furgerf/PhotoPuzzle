import io
import logging
import os
from glob import glob
from time import time

import numpy as np
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from PIL import Image

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(funcName)s:%(lineno)d: %(message)s"
)
logger = logging.getLogger("api")

app = FastAPI()


@app.middleware("http")
async def log_process_time(request: Request, call_next):
    start_time = time()
    response = await call_next(request)
    logger.info("Request to %s handled in %.1fms", request.url, 1000 * (time() - start_time))
    return response


rows = int(os.environ["ROWS"])
columns = int(os.environ["COLUMNS"])
image_states = np.full((rows, columns), 0)

resize = int(os.environ["RESIZE"])


images = []
for image_file in glob(os.path.join("data", "*.png")):
    logger.info("Loading %s", image_file)
    with Image.open(image_file) as img:
        new_size = (img.size[0] // resize, img.size[1] // resize)
        logger.info("Resizing by %d (from %s to %s)", resize, img.size, new_size)
        image = img.resize(new_size)
        images.append(np.array(image))


def construct_image():
    logger.info("Constructing current image")
    result = images[0]
    logger.info("%s %s", result.dtype, result.shape)
    return result


@app.get("/image/full")
def get_full_image() -> StreamingResponse:
    image = Image.fromarray(construct_image(), mode="RGB")
    logger.info("Encoding image")
    output = io.BytesIO()
    image.save(output, format="PNG")
    output.seek(0)
    return StreamingResponse(output, media_type="image/png")
