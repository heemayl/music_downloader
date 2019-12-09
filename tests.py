import argparse
import os
import re

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from urllib.parse import quote

import pytest
import requests

from bs4 import BeautifulSoup

from music_downloader import (
    BASE_URL,
    DOWNLOAD_URL,
    SONG_NAME_REPLACE_REGEX,
    get_argument_parser,
    get_parsed_args,
    get_album_url,
    get_song_download_url,
    get_album_dir,
    get_song_urls,
    get_response,
    get_soup,
    download_save_song,
    is_song_url,
)


_album_dir_path_mkdir_called_times = 0


def patched_mkdir(*args, **kwargs):
    global _album_dir_path_mkdir_called_times
    if kwargs.get('exist_ok') is False:
        if _album_dir_path_mkdir_called_times == 1:
            return None
        _album_dir_path_mkdir_called_times += 1
        raise FileExistsError


def patched_requests_get(*args, success=True, **kwargs):
    Response = type('Response', (object,), {})
    response = Response()
    if success:
        response.status_code = 200
        response.text = 'success'
        response.content = b'success'
    else:
        response.status_code = 400
        response.text = 'failure'
        response.content = b'failure'
    return response


def patched_requests_get_success(*args, **kwargs):
    return patched_requests_get(*args, success=True, **kwargs)


def patched_requests_get_failure(*args, **kwargs):
    return patched_requests_get(*args, success=False, **kwargs)


def patched_open(*args, **kwargs):
    Open = type('Open', (object,), {})
    Open.__enter__ = lambda self, *args, **kwargs: self
    Open.__exit__ = lambda self, *args, **kwargs: None
    # Returning `self` from __enter__` and setting `write`
    # on Open instead of on a file-like object, for easier
    # making mocking easier (so that we don't need something
    # like `io.StringIO`/`io.BytesIO`
    Open.write = Open.__exit__
    return Open()


class TestMusicAlbumDownloader:
    """Unit tests for the music_downloader."""

    artist = 'Foo Bar'
    album = 'Spam Egg'
    destination = '/baz/'

    def test_get_argument_parser(self):
        parser = get_argument_parser()
        assert isinstance(parser, argparse.ArgumentParser)

    def test_get_parsed_args_without_destination(self):
        parser = get_argument_parser()
        artist, album, destination = get_parsed_args(
            parser,
            [
                '--artist', self.artist,
                '--album', self.album,
            ],
        )
        assert artist == self.artist
        assert album == self.album
        assert destination == os.getcwd()

    def test_get_parsed_args_with_destination(self):
        parser = get_argument_parser()
        artist, album, destination = get_parsed_args(
            parser,
            [
                '--artist', self.artist,
                '--album', self.album,
                '--destination', self.destination,
            ],
        )
        assert artist == self.artist
        assert album == self.album
        assert destination == self.destination

    def test_get_parsed_args_missing_artist(self):
        parser = get_argument_parser()
        with pytest.raises(SystemExit):
            _ = get_parsed_args(
                parser,
                ['--album', self.album],
            )

    def test_get_parsed_args_missing_album(self):
        parser = get_argument_parser()
        with pytest.raises(SystemExit):
            _ = get_parsed_args(
                parser,
                ['--artist', self.artist],
            )

    def test_get_parsed_args_empty_artist(self):
        parser = get_argument_parser()
        with pytest.raises(ValueError):
            _ = get_parsed_args(
                parser,
                [
                    '--artist', '',
                    '--album', self.album,
                ],
            )

    def test_get_parsed_args_empty_album(self):
        parser = get_argument_parser()
        artist, album, destination = get_parsed_args(
            parser,
            [
                '--artist', self.artist,
                '--album', '',
            ],
        )
        assert album == ''

    def test_get_parsed_args_empty_destination(self):
        parser = get_argument_parser()
        with pytest.raises(ValueError):
            _ = get_parsed_args(
                parser,
                [
                    '--artist', self.artist,
                    '--album', self.album,
                    '--destination', '',
                ],
            )

    def test_get_album_url(self):
        artist_lower = self.artist.lower()
        assert get_album_url(self.artist, self.album) == (
            f'{BASE_URL}/{artist_lower[0].upper()}/{quote(self.artist)}/'
            f'{quote(self.album)}/'
        )

    def test_get_song_download_url(self):
        artist_lower = self.artist.lower()
        song_url_path = '07. Foo Bar.mp3'
        assert get_song_download_url(self.artist, self.album, song_url_path) == (
            f'{DOWNLOAD_URL}/{artist_lower[0].upper()}/{quote(self.artist)}/'
            f'{quote(self.album)}/{quote(song_url_path)}'
        )

    @patch('pathlib.Path.mkdir', return_value=None)
    def test_get_album_dir(self, patched_mkdir):
        assert get_album_dir(
            destination=self.destination,
            artist=self.artist,
            album=self.album,
        ) == f'{self.destination.rstrip("/")}/{self.album}_{self.artist}'

        assert patched_mkdir.call_count == 2

    @patch('pathlib.Path.mkdir', side_effect=patched_mkdir)
    def test_get_album_dir_file_exists_error(self, patched_mkdir):
        assert re.search(
            (
                rf'^{self.destination.rstrip("/")}/{self.album}_'
                rf'{self.artist}_[a-f\d]{{10}}$'
            ),
            get_album_dir(
                destination=self.destination,
                artist=self.artist,
                album=self.album,
            )
        )
        assert patched_mkdir.call_count == 3

    def test_get_song_urls(self):

        html = r'''
        <div class="col-md-9">
        <a name="anchor-content"></a>
        <div class="panel panel-default panel-green">
        <div class="panel-heading panel-heading-green">
        <h3 class="panel-title">
        Bangla Music &gt; A &gt; Aashor &gt;
        </h3>
        </div>
        <div class="panel-body">
        <div class="list-group">
        <a class="list-group-item" href="http://www.music.com.bd/download/browse/A/">
        <span class="icon-back-png"></span>&nbsp;&nbsp;
        Back to Parent Directory
        <span class="badge quote-list-badge">&nbsp;</span></a>
        <a class="list-group-item" href="//www.music.com.bd/download/Music/A/Aashor/07 - Aashor -  Maya (music.com.bd).mp3.html">
        <span class="icon-sound-png"></span>&nbsp;&nbsp;
        07 - Aashor -  Maya (music.com.bd).mp3
        <span class="badge quote-list-badge">4.2 MB</span></a>
        <a class="list-group-item" href="//www.music.com.bd/download/Music/A/Aashor/Aashor - Mohasrishtyr Gan (music.com.bd).mp3.html">
        <span class="icon-sound-png"></span>&nbsp;&nbsp;
        Aashor - Mohasrishtyr Gan (music.com.bd).mp3
        <span class="badge quote-list-badge">3.5 MB</span></a>
        </div>
        <ul class="list-group">
        <li class="list-group-item text-right">2 Files - 0 Folders | Total size: 7.7 MB</li>
        </ul>
        </div>
        '''

        soup = BeautifulSoup(html, 'html.parser')
        assert len(list(get_song_urls(soup))) == 2

    def test_get_song_urls_no_match(self):

        html = r'''
        <div class="col-md-9">
        <a name="anchor-content"></a>
        <div class="panel panel-default panel-green">
        <div class="panel-heading panel-heading-green">
        <h3 class="panel-title">
        Bangla Music &gt; A &gt; Aashor &gt;
        </h3>
        </div>
        <div class="panel-body">
        <div class="list-group">
        <a class="list-group-item" href="http://www.music.com.bd/download/browse/A/">
        <span class="icon-back-png"></span>&nbsp;&nbsp;
        Back to Parent Directory
        <span class="badge quote-list-badge">&nbsp;</span></a>
        <a class="list-group-item" href="//www.music.com.bd/download/Music/A/Aashor/07 - Aashor -  Maya (music.com.bd).zip">
        <span class="icon-sound-png"></span>&nbsp;&nbsp;
        07 - Aashor -  Maya (music.com.bd).mp3
        <span class="badge quote-list-badge">4.2 MB</span></a>
        <a class="list-group-item" href="//www.music.com.bd/download/Music/A/Aashor/Aashor - Mohasrishtyr Gan (music.com.bd).mp3">
        <span class="icon-sound-png"></span>&nbsp;&nbsp;
        Aashor - Mohasrishtyr Gan (music.com.bd).mp3
        <span class="badge quote-list-badge">3.5 MB</span></a>
        </div>
        <ul class="list-group">
        <li class="list-group-item text-right">2 Files - 0 Folders | Total size: 7.7 MB</li>
        </ul>
        </div>
        '''

        soup = BeautifulSoup(html, 'html.parser')
        assert len(list(get_song_urls(soup))) == 0

    @pytest.mark.asyncio
    @patch('requests.get', side_effect=patched_requests_get_success)
    async def test_get_response_success(self, patched_requests_get):
        success, response_content = await get_response(
            url='https://music.com.bd',
            executor=ThreadPoolExecutor(),
            get_bytes=True,
        )
        assert success
        assert response_content == b'success'

    @pytest.mark.asyncio
    @patch('requests.get', side_effect=patched_requests_get_failure)
    async def test_get_response_failure(self, patched_requests_get):
        success, response_content = await get_response(
            url='https://music.com.bd',
            executor=ThreadPoolExecutor(),
            get_bytes=False,
        )
        assert not success
        assert response_content == 'failure'

    @pytest.mark.asyncio
    @patch('requests.get', side_effect=patched_requests_get_success)
    async def test_get_soup(self, patched_requests_get):
        assert isinstance(
            await get_soup(
                album_url='https://music.com.bd/artist/A/album/',
                executor=ThreadPoolExecutor(),
            ),
            BeautifulSoup
        )

    @pytest.mark.asyncio
    @patch('requests.get', side_effect=requests.exceptions.ConnectionError)
    async def test_get_soup_system_exit(self, patched_requests_get):
        with pytest.raises(SystemExit):
            assert await get_soup(
                album_url='https://music.com.bd/artist/A/album/',
                executor=ThreadPoolExecutor(),
            )

    def test_song_name_replace_regex(self):
        assert SONG_NAME_REPLACE_REGEX.sub(
            '',
            '01. Foo - Bar (music.com.bd).mp3'
        ) == '01. Foo - Bar.mp3'

        assert SONG_NAME_REPLACE_REGEX.sub(
            '',
            '01. Foo - Bar(music.com.bd) .mp3'
        ) == '01. Foo - Bar.mp3'

        assert SONG_NAME_REPLACE_REGEX.sub(
            '',
            '01. Foo - Bar ( music.com.bd ) .mp3'
        ) == '01. Foo - Bar.mp3'

        assert SONG_NAME_REPLACE_REGEX.sub(
            '',
            '01. Foo - Bar(www.music.com.bd).mp3'
        ) == '01. Foo - Bar.mp3'

    @pytest.mark.asyncio
    @patch('requests.get', side_effect=patched_requests_get_success)
    @patch('builtins.open', side_effect=patched_open)
    async def test_download_save_song(self, patched_open, patched_requests_get):
        assert await download_save_song(
            song_url_path='https://music.com.bd',
            artist=self.artist,
            album=self.album,
            executor=ThreadPoolExecutor(),
            album_dir=self.destination,
        ) is None
        assert patched_open.call_count == 1

    def test_is_song_url(self):
        assert is_song_url('https://music.com.bd/foo/spam.mp3')
        assert not is_song_url('https://music.com.bd/foo/')
