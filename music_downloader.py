#!/usr/bin/env python3

import argparse
import asyncio
import os
import pathlib
import re
import secrets
import sys
import warnings

from concurrent.futures import ThreadPoolExecutor
from functools import partial, reduce
from itertools import chain
from typing import Tuple, List, Union, Optional, Iterator, Iterable
from urllib.parse import quote, urljoin

import requests

from bs4 import BeautifulSoup


BASE_URL = 'https://www.music.com.bd/download/browse'
DOWNLOAD_URL = 'https://download.music.com.bd/Music'

SONG_URL_PATH_REGEX = re.compile(r'(?i)^.*/([^/]+)(?<!\.zip)\.html$')
# Drop `music.com.bd` substring from song's name
SONG_NAME_REPLACE_REGEX = re.compile(r'(?:)\s*\(?\s*(?:www\.)?music\.com\.bd\s*\)?\s*')

requests.get = partial(requests.get, verify=False, allow_redirects=True)
# Silent requests for verify=False
warnings.warn = lambda *args, **kwargs: None


def get_argument_parser() -> argparse.ArgumentParser:
    """Parse passed command line arguments and returns a tuple
    containing passed artist, album, and download directory.
    """

    parser = argparse.ArgumentParser(
        description='Music album downloader from music.com.bd',
    )
    parser.add_argument(
        '--artist',
        required=True,
        dest='artist',
        help=(
            "Name of the artist. This must correspond to the name shown "
            "in the browser address bar i.e. the URL path. For example, "
            "if the address is shown as `https://www.music.com.bd/download/"
            "browse/A/Abbasuddin Ahmed/`, this argument must have the value "
            "'Abbasuddin Ahmed' (with the single quotes around to prevent "
            "the shell to pass names with whitespaces as two arguments "
            "instead of one)."
        ),
    )
    parser.add_argument(
        '--album',
        required=True,
        dest='album',
        help=(
            "Name of the album. This must correspond to the name shown "
            "in the browser address bar i.e. in the path. For example, "
            "if the URL shows `https://www.music.com.bd/download/browse/"
            "A/Arnob/Hok Kolorob/`, this argument must have the value "
            "'Hok Kolorob' (with the single quotes around). For downloading "
            "songs from the artist's directory e.g. from `https://www.music"
            ".com.bd/download/browse/A/Arnob/`, pass this value as an empty "
            "string i.e. ''."
        ),
    )
    parser.add_argument(
        '--destination',
        default=os.getcwd(),
        dest='destination',
        help=(
            "Directory/Folder where to save the downloaded album. If the "
            "path is missing on the filesystem, it is created (along with "
            "all the missing parent directories). If this option is not "
            "provided, the album is saved in the current directory (from "
            "where this script is invoked)."
        ),
    )

    return parser


def get_parsed_args(
        parser: argparse.ArgumentParser,
        args: Optional[List[str]] = None,
) -> Tuple[str, str, str]:

    if args:
        parsed_args = parser.parse_args(args)
    else:
        parsed_args = parser.parse_args()

    # Validation
    artist = parsed_args.artist.strip()
    if not artist:
        raise ValueError("Artist's name cannot be empty")

    destination = parsed_args.destination.strip()
    if not destination:
        raise ValueError("Destination directory cannot be empty")

    return artist, parsed_args.album.strip(), destination


def _get_joined_url(base: str, *parts: Iterable, append_slash: bool = False) -> str:
    """Takes a base url and returns a complete URL join-ing
    the parts after the base.
    """
    if not base.endswith('/'):
        base = base + '/'
    slashed_parts = (
        part + '/' if not part.endswith('/') else part
        for part in parts[:-1]
    )

    parts = chain(slashed_parts, parts[-1:])

    joined_url = reduce(urljoin, parts, base)
    return (
        (joined_url + '/' if not joined_url.endswith('/') else joined_url)
        if append_slash
        else joined_url.rstrip('/')
    )


def get_album_url(artist: str, album: str) -> str:

    namespace = artist[0].upper()
    return _get_joined_url(
        BASE_URL,
        namespace,
        quote(artist),
        quote(album),
        append_slash=True,
    )


def get_song_download_url(artist: str, album: str, song_url_path: str) -> str:

    namespace = artist[0].upper()
    return _get_joined_url(
        DOWNLOAD_URL,
        namespace,
        quote(artist),
        quote(album),
        quote(song_url_path),
        append_slash=False,
    )


def is_song_url(url: str) -> bool:
    """Takes a URL and returns whether that is a song URL or not."""

    # Song URLs do not contain trailing slash
    return not url.endswith('/')


async def get_response(
        url: str,
        executor: ThreadPoolExecutor,
        get_bytes: bool = True,
) -> Tuple[bool, Union[bytes, str]]:
    """Takes the URL to send GET request to and returns a
    tuple containing whether we get a successful response
    and the content.
    """

    return_when_error = (False, b'' if get_bytes else '')

    event_loop = asyncio.get_event_loop()

    try:
        response = await event_loop.run_in_executor(executor, requests.get, url)
    except requests.exceptions.ConnectionError:
        print(f'Network error while connecting to URL "{url}"', file=sys.stderr)
        if not is_song_url(url):
            sys.exit(2)
        return return_when_error
    except Exception:
        return return_when_error

    success = response.status_code == 200
    return (
        success,
        response.content if get_bytes else response.text
    )


async def get_soup(
        album_url: str,
        executor: ThreadPoolExecutor
) -> Optional[BeautifulSoup]:
    """Returns a BeautifulSoup object from the response
    sent to the `album_url`.
    """

    success, response = await get_response(
        url=album_url,
        executor=executor,
        get_bytes=False
    )
    return BeautifulSoup(response, 'html.parser') if success else None


def get_album_dir(destination: str, artist: str, album: str) -> str:
    """Returns absolute path to the album directory
    where songs will be saved.
    """

    destination_path = pathlib.Path(destination)
    destination_path.mkdir(mode=0o755, parents=True, exist_ok=True)
    album_dir_name = f'{album}_{artist}' if album else f'{artist}'

    append = ''
    while True:
        _album_dir_name = f'{album_dir_name}{append}'
        album_dir_path = destination_path / _album_dir_name

        try:
            album_dir_path.mkdir(mode=0o755, parents=False, exist_ok=False)
            return str(album_dir_path.resolve())
        except FileExistsError:
            append = f'_{secrets.token_hex(5)}'


def get_song_urls(soup: BeautifulSoup) -> Iterator[str]:
    """Takes the album page soup object and returns an
    iterator containing the song URL path (without any
    prefix, only the last portion).
    """

    songs = soup.select('div.list-group a.list-group-item')
    for song in songs:
        if matched_url_path := SONG_URL_PATH_REGEX.search(song['href']):
            yield matched_url_path.group(1)


async def download_save_song(
        song_url_path: str,
        artist: str,
        album: str,
        executor: ThreadPoolExecutor,
        album_dir: str,
) -> None:
    """Send GET to the song URL to get the content and save
    as as a file in the `album_dir`.
    """

    song_name = SONG_NAME_REPLACE_REGEX.sub('', song_url_path)
    print(f'Downloading song "{song_name}"')

    song_url = get_song_download_url(artist, album, song_url_path)

    success, downloaded_song = await get_response(song_url, executor)
    if not success:
        print(f'Song not found: "{song_name}"')
        return None

    with open(f'{album_dir}/{song_name}', 'wb') as f:
        f.write(downloaded_song)

    return None


async def main() -> None:
    """The `main` function."""

    parser = get_argument_parser()
    artist, album, destination = get_parsed_args(parser)
    album_url = get_album_url(artist, album)
    executor = ThreadPoolExecutor()

    soup = await get_soup(album_url, executor)
    if not soup:
        print('Album not found!', file=sys.stderr)
        executor.shutdown()
        sys.exit(1)

    song_urls = get_song_urls(soup)
    try:
        first_song_url = next(song_urls)
    except StopIteration:
        print('No songs found on the album!', file=sys.stderr)
        executor.shutdown()
        sys.exit(0)

    album_dir = get_album_dir(destination, artist, album)
    song_urls = chain([first_song_url], song_urls)
    await asyncio.gather(*[
        download_save_song(song_url, artist, album, executor, album_dir)
        for song_url in song_urls
    ])

    executor.shutdown()
    print(f'\nAll songs saved in "{album_dir}"', end='\n\n')


if __name__ == '__main__':
    asyncio.run(main())
