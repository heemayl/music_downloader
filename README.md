## Easy downloading of music albums from [music.com.bd][1]. This does the downloading asynchronously (using `asyncio`).

#### Requires Python 3.8+

---

### How to run the `music_downloader.py` to download albums:

1. Make sure you have Python 3.8+:

		python --version

2. Install the dependencies:

		pip -r requirements.txt

3. Run the command:

		python music_downloader.py --help


### Examples:

- Download the album **Shongbigno Pakhikul O Kalkata Bishoiyuk** by **Moheener Ghoraguli** (the name of the artist and album must match what's found on the URL; for example, this album is available on the URL [https://www.music.com.bd/download/browse/M/Moheener Ghoraguli/Shongbigno Pakhikul O Kalkata Bishoiyuk/][2]):

		python music_downloader.py --artist 'Moheener Ghoraguli' --album 'Shongbigno Pakhikul O Kalkata Bishoiyuk'

	Once the download is done, you'll be shown the directory where it's saved (by default in the current working directory i.e. from where the script is invoked).

- Download the album **Hok Kolorob** by **Arnob** in directory `foobar` :

		python music_downloader.py --artist 'Arnob' --album 'Hok Kolorob' --destination 'foobar'


- The `destination` directory can also be an absolute path:

		python music_downloader.py --artist 'Warfaze' --album 'Obaak Bhalobasha' --destination /where/to/save/

---

### Development:

Install the dependencies:

	pip install -r requirements_dev.txt

Run tests:

	pytest

Before sending PR, plase add relevant test(s) and make sure all test passes.


[1]: https://music.com.bd
[2]: https://www.music.com.bd/download/browse/M/Moheener%20Ghoraguli/Shongbigno%20Pakhikul%20O%20Kalkata%20Bishoiyuk/
