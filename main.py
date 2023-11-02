import flask

import time

import typing

import playwright.sync_api

from playwright.sync_api import Page

from collections import Counter

import asyncio

from solver.core import *

app = flask.Flask(__name__)

def motion(page: Page) -> typing.Optional[str]:
    currentdir = os.getcwd()
    solver = AudioChallenger(dir_challenge_cache=currentdir, debug=True)
    solver.anti_recaptcha(page)
    return solver.response

BLOCK_RESOURCE_TYPES = [
  'beacon',
  'csp_report',
  'font',
  'image',
  'imageset',
  'media',
  'object',
  'texttrack'
# 'script',  
# 'xhr',
]


# we can also block popular 3rd party resources like tracking:
BLOCK_RESOURCE_NAMES = [
  'adzerk',
  'analytics',
  'cdn.api.twitter',
  'doubleclick',
  'exelator',
  'facebook',
  'fontawesome',
]

def intercept_route(route):
    """intercept all requests and abort blocked ones"""
    if route.request.resource_type in BLOCK_RESOURCE_TYPES:
        return route.abort()
    if any(key in route.request.url for key in BLOCK_RESOURCE_NAMES):
        return route.abort()
    return route.continue_()

@app.route("/")
def index():
    return flask.redirect("https://github.com/dragdotpng")

@app.route("/solve", methods=["POST"])
def solve():
    start = time.time()
    try:
        json_data = flask.request.json
        url = json_data["url"]
        with playwright.sync_api.sync_playwright() as p:
            browser = p.firefox.launch(headless=True)
            ctx = browser.new_context(locale="en-US")
            page = ctx.new_page()
            page.route("**/*", intercept_route)
            page.goto(url)
            result = motion(page)
            print(time.time() - start)
            if result:
                return make_response(result)
            else:
                return make_response("failed")
    except Exception as e:
        pass

def make_response(captcha_key):
    if captcha_key == "failed":
        return flask.jsonify({"status": "error", "token": "poopy fart accident"})
    return flask.jsonify({"status": "success", "token": captcha_key})

if __name__ == "__main__":
    app.run()
