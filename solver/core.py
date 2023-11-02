# -*- coding: utf-8 -*-
# Time       : 2022/2/24 22:29
# Author     : QIN2DIM
# Github     : https://github.com/QIN2DIM
# Description:
import os
import time
import typing
from contextlib import suppress
from urllib.parse import quote
from urllib.request import getproxies

import pydub
import requests
from loguru import logger
from playwright.sync_api import Page, Locator, expect, FrameLocator
from playwright.sync_api import TimeoutError
from speech_recognition import Recognizer, AudioFile

from .exceptions import (
    AntiBreakOffWarning,
    RiskControlSystemArmor,
    ChallengeTimeoutException,
    LabelNotFoundException,
)


class ChallengeStyle:
    AUDIO = "audio"
    VISUAL = "visual"


class ArmorUtils:
    """判断遇见 reCAPTCHA 的各种断言方法"""

    @staticmethod
    def fall_in_captcha_login(page: Page) -> typing.Optional[bool]:
        """检测在登录时遇到的 reCAPTCHA challenge"""

    @staticmethod
    def fall_in_captcha_runtime(page: Page) -> typing.Optional[bool]:
        """检测在运行时遇到的 reCAPTCHA challenge"""

    @staticmethod
    def face_the_checkbox(page: Page) -> typing.Optional[bool]:
        """遇见 reCAPTCHA checkbox"""
        with suppress(TimeoutError):
            page.frame_locator("//iframe[@title='reCAPTCHA']")
            return True
        return False


class ArmorKernel:
    """人机挑战的共用基础方法"""

    # <success> Challenge Passed by following the expected
    CHALLENGE_SUCCESS = "success"
    # <continue> Continue the challenge
    CHALLENGE_CONTINUE = "continue"
    # <crash> Failure of the challenge as expected
    CHALLENGE_CRASH = "crash"
    # <retry> Your proxy IP may have been flagged
    CHALLENGE_RETRY = "retry"
    # <refresh> Skip the specified label as expected
    CHALLENGE_REFRESH = "refresh"
    # <backcall> (New Challenge) Types of challenges not yet scheduled
    CHALLENGE_BACKCALL = "backcall"

    def __init__(self, dir_challenge_cache: str, style: str, debug=True, **kwargs):
        self.dir_challenge_cache = dir_challenge_cache
        self.style = style
        self.debug = debug
        self.action_name = f"{self.style.title()}Challenge"

        self.bframe = "//iframe[contains(@src,'bframe')]"
        self._response = ""

    @property
    def utils(self):
        return ArmorUtils

    @property
    def response(self):
        return self._response

    def captcha_screenshot(self, page: typing.Union[Page, Locator], name_screenshot: str = None):
        """
        保存挑战截图，需要在 get_label 之后执行

        :param page:
        :param name_screenshot: filename of the Challenge image
        :return:
        """
        if hasattr(self, "label_alias") and hasattr(self, "label"):
            _suffix = self.label_alias.get(self.label, self.label)
        else:
            _suffix = self.action_name
        _filename = (
            f"{int(time.time())}.{_suffix}.png" if name_screenshot is None else name_screenshot
        )
        _out_dir = os.path.join(os.path.dirname(self.dir_challenge_cache), "captcha_screenshot")
        _out_path = os.path.join(_out_dir, _filename)
        os.makedirs(_out_dir, exist_ok=True)

        # FullWindow screenshot or FocusElement screenshot
        page.screenshot(path=_out_path)
        return _out_path

    def log(self, message: str, **params) -> None:
        """格式化日志信息"""
        if not self.debug:
            return
        flag_ = message
        if params:
            flag_ += " - "
            flag_ += " ".join([f"{i[0]}={i[1]}" for i in params.items()])
        logger.debug(flag_)

    def _activate_recaptcha(self, page: Page):
        """处理 checkbox 激活 reCAPTCHA"""
        # --> reCAPTCHA iframe
        activator = page.frame_locator("//iframe[@title='reCAPTCHA']").locator(
            ".recaptcha-checkbox-border"
        )
        activator.click()
        self.log("Active reCAPTCHA")
        time.sleep(0.5)
        

        if self.is_correct(page) == self.CHALLENGE_SUCCESS:
            return self.CHALLENGE_SUCCESS
        

    def _switch_to_style(self, page: Page) -> typing.Optional[bool]:
        frame_locator = page.frame_locator(self.bframe)
        if self.style == ChallengeStyle.AUDIO:
            switcher = frame_locator.locator("#recaptcha-audio-button")
            expect(switcher).to_be_visible()
            switcher.click()
        self.log("Accept the challenge", style=self.style)
        return True

    def anti_recaptcha(self, page: Page):
        # [⚔] 激活 reCAPTCHA
        try:
            self._activate_recaptcha(page)
        except AntiBreakOffWarning as err:
            logger.info(err)
            return
        return self._switch_to_style(page)


class AudioChallenger(ArmorKernel):
    def __init__(self, dir_challenge_cache: str, debug: typing.Optional[bool] = True, **kwargs):
        super().__init__(
            dir_challenge_cache=dir_challenge_cache,
            style=ChallengeStyle.AUDIO,
            debug=debug,
            kwargs=kwargs,
        )
        self.recognizer = Recognizer()

    def get_audio_download_link(self, fl: FrameLocator) -> typing.Optional[str]:
        """Returns the download address of the sound source file."""
        for _ in range(5):
            with suppress(TimeoutError):
                self.log("Play challenge audio")
                fl.locator("//button[@aria-labelledby]").click(timeout=0)
                break
            with suppress(TimeoutError):
                header_text = fl.locator(".rc-doscaptcha-header-text").text_content(timeout=0)
                if "Try again later" in header_text:
                    raise ConnectionError(
                        "Your computer or network may be sending automated queries."
                    )

        # Locate the sound source file url
        try:
            audio_url = fl.locator("#audio-source").get_attribute("src")
        except TimeoutError:
            raise RiskControlSystemArmor("Trapped in an inescapable risk control context")
        return audio_url

    def handle_audio(self, audio_url: str) -> str:
            """
            Location, download and transcoding of audio files
            :param audio_url: reCAPTCHA Audio Link address
            :return:
            """
            # Splice audio cache file path
            timestamp_ = int(time.time())
            path_audio_mp3 = os.path.join(self.dir_challenge_cache, f"audio_{timestamp_}.mp3")
            path_audio_wav = os.path.join(self.dir_challenge_cache, f"audio_{timestamp_}.wav")
            # Download the sound source file to the local
            self.log("Downloading challenge audio")
            _request_asset(audio_url, path_audio_mp3)
            # Convert audio format mp3 --> wav
            self.log("Audio transcoding MP3 --> WAV")
            pydub.AudioSegment.from_mp3(path_audio_mp3).export(path_audio_wav, format="wav")
            self.log("Transcoding complete", path_audio_wav=path_audio_wav)
            os.remove(path_audio_mp3)
            return path_audio_wav

    def parse_audio_to_text(self, path_audio_wav: str) -> str:
        language = "en-US"

        audio_file = AudioFile(path_audio_wav)
        with audio_file as stream:
            audio = self.recognizer.record(stream)

        self.log("Parsing audio file ... ")
        audio_answer = self.recognizer.recognize_google(audio, language=language)
        self.log("Analysis completed", audio_answer=audio_answer)

        return audio_answer

    def submit_text(self, fl: FrameLocator, text: str) -> typing.Optional[bool]:
        """
        Submit reCAPTCHA man-machine verification

        The answer text information needs to be passed in,
        and the action needs to stay in the submittable frame-page.

        :param fl:
        :param text:
        :return:
        """
        with suppress(NameError, TimeoutError):
            input_field = fl.locator("#audio-response")
            input_field.fill("")
            input_field.fill(text.lower())
            self.log("Submit the challenge")
            input_field.press("Enter")
            return True
        return False

    def is_correct(self, page: Page) -> typing.Optional[str]:
        """Check if the challenge passes"""
        with suppress(TimeoutError):
            err_resp = page.locator(".rc-audiochallenge-error-message")
            if msg := err_resp.text_content(timeout=200):
                self.log("Challenge failed", err_message=msg)
            return self.CHALLENGE_RETRY
        if page.evaluate("grecaptcha.getResponse()") == "":
            return self.CHALLENGE_CONTINUE
        self.log("Challenge success")
        self._response = page.evaluate("grecaptcha.getResponse()")
        # delete wav file
        for file in os.listdir(self.dir_challenge_cache):
            if file.endswith(".wav"):
                os.remove(os.path.join(self.dir_challenge_cache, file))
        return self.CHALLENGE_SUCCESS

    def anti_recaptcha(self, page: Page):
        if super().anti_recaptcha(page) is not True:
            return
        
        # [⚔] Register Challenge Framework
        frame_locator = page.frame_locator(self.bframe)
        response = self.is_correct(page)
        if response == self.CHALLENGE_SUCCESS:
            return self.CHALLENGE_SUCCESS
        # [⚔] Get the audio file download link
        audio_url: str = self.get_audio_download_link(frame_locator)
        # [⚔] Audio transcoding（MP3 --> WAV）increase recognition accuracy
        path_audio_wav: str = self.handle_audio(audio_url=audio_url)
        # [⚔] Speech to text
        audio_answer: str = self.parse_audio_to_text(path_audio_wav)
        # [⚔] Locate the input box and fill in the text
        if self.submit_text(frame_locator, text=audio_answer) is not True:
            self.log("reCAPTCHA Challenge submission failed")
            raise ChallengeTimeoutException
        # Judging whether the challenge is successful or not
        # Get response of the reCAPTCHA
        return self.is_correct(page)





def _request_asset(asset_download_url: str, asset_path: str):
    headers = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/105.0.0.0 Safari/537.36 Edg/105.0.1343.27"
    }

    # FIXME: PTC-W6004
    #  Audit required: External control of file name or path
    with open(asset_path, "wb") as file, requests.get(
        asset_download_url, headers=headers, stream=True, proxies=getproxies()
    ) as response:
        for chunk in response.iter_content(chunk_size=1024):
            if chunk:
                file.write(chunk)


def new_challenger(
    style: str,
    dir_challenge_cache: str,
    dir_model: typing.Optional[str] = None,
    onnx_prefix: typing.Optional[str] = None,
    debug: typing.Optional[bool] = True,
):
    # Check cache dir of challenge
    if not os.path.isdir(dir_challenge_cache):
        raise FileNotFoundError("dir_challenge_cache should be an existing file directory.")
    dir_payload = os.path.join(dir_challenge_cache, style)
    os.makedirs(dir_payload, exist_ok=True)

    # Check challenge style
    if style in [ChallengeStyle.AUDIO]:
        return AudioChallenger(dir_challenge_cache=dir_payload, debug=debug)
    else:
        raise TypeError(
            f"style({style}) should be {ChallengeStyle.AUDIO} or {ChallengeStyle.VISUAL}"
        )