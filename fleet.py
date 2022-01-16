#!/usr/bin/env python

from argparse import ArgumentParser
from random import random
from threading import Thread
from time import sleep

import requests

inertia = 10


def user(column, row, target):
    sleep(10 * random())
    while True:
        response = requests.put(f"http://localhost:8000/api/image/column/{column}/row/{row}/state/toggle")
        state = int(response.text)
        multiplier = 6 if state == target else 1
        sleep(inertia * multiplier * random())
        if state == target and inertia > 40:
            break


def main():
    parser = ArgumentParser()
    parser.add_argument("--target", type=int)
    parser.add_argument("--columns", type=int)
    parser.add_argument("--rows", type=int)
    args = parser.parse_args()

    print(f"Trying to get to {args.target} with {args.columns*args.rows} users")

    for column in range(args.columns):
        for row in range(args.rows):
            Thread(target=user, args=(column, row, args.target), daemon=True).start()

    global inertia
    while True:
        inertia += 1
        sleep(1)


if __name__ == "__main__":
    main()
