# PhotoPuzzle

This is a simple application for playing a "photo puzzle" with a few people. The idea is that a
puzzle is built out of a set of photos (of equal resolution) that are split into individual tiles
(pieces). Clients can then control a (randomly-assigned) tile and toggle which of the original
images are used for the tile, with the objective of collectively reconstructing a "target" image.

![Example](https://github.com/furgerf/PhotoPuzzle/raw/master/example.gif "Example")

## Application Overview

A fastapi server loads all images in the `data/` directory - those are the images that make up the
puzzle. It then starts a number of bot "players", one per tile, which randomly toggle their tile but
converge towards the target image. The bots aren't intended to accurately simulate human players,
but rather, to make it more interesting when not there are fewer players than tiles.

The current puzzle can be viewed on `<address>:8000`, which is updated through a websocket whenever
one of the tiles is toggled.

The clients can visit `<address>:8000/client`, where they see three buttons:

- Red: toggles current tile
- Blue: requests a new tile to control (the old one gets taken over by a bot)
- Green: unused

# Installation

Clone the repository and run `make build`. Done 🙂

# Usage

Copy the images to use to `data/` and configure the application by copying `.env.example` to `.env`
and adjust as desired. Currently, the following things can be configured:

```bash
# the number of rows/columns to split the images into
COLUMNS=8
ROWS=6

# the factor by which to resize the images (so that they fit on the page)
RESIZE=4

# the (alphabetical) file index of the target image that the bots will converge towards
# set a negative value to select a target image randomly
TARGET=-1
```

Run the application with `make run`.

