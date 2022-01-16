#!/usr/bin/env python

from argparse import ArgumentParser
from random import random
from time import sleep

import requests


def main():
    parser = ArgumentParser()
    parser.add_argument("--column", type=int)
    parser.add_argument("--row", type=int)
    args = parser.parse_args()

    print(f"Toggling {args.column}/{args.row}")
    while True:
        requests.put(f"http://localhost:8000/api/image/column/{args.column}/row/{args.row}/state/toggle")
        sleep(15 * random())


if __name__ == "__main__":
    main()
