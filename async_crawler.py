from argparse import ArgumentParser
import asyncio
import aiohttp
import async_timeout
import logging
from collections import namedtuple
import re
import os


news_urls_str = r'<td class="title"><a href="(.*?)".*?class="storylink".*?>(.*?)<\/a>.*?<span class="age"><a href="(item\?id=.*?)">'
news_urls_pattern = re.compile(news_urls_str, re.DOTALL)

comment_str = ""
comment_pattern = re.compile(comment_str)

urls_in_comment_str = ""
urls_in_comment_pattern = re.compile(urls_in_comment_str)

NewsParams = namedtuple("NewsParams", "url title comment_url")

NEWS_FOLDER = "news"
WAIT = 5
MAX_NEWS = 5
BASE_URL = "https://news.ycombinator.com/"
CYCLES = 5
HTTP_TIMEOUT = 10
FILE_EXT = ".html"
MAX_FILE_NAME = 50
FORBIDDEN_CHARS = ("/", )
SCHEME_TEMPLATE = "://"


class DownloadError(Exception):
    def __init__(self, url, msg):
        self.url = url
        self.msg = msg


def make_fn_from_url(url):
        fn = url
        if SCHEME_TEMPLATE in fn:
            fn = fn.split(SCHEME_TEMPLATE)[-1]

        if fn.endswith("/"):
            fn = fn[:-1]

        if "/" in fn:
            fn = fn.split("/")[-1]

        for c in FORBIDDEN_CHARS:
            fn = fn.replace(c, "_")

        if fn.lower().endswith(FILE_EXT.lower()):
            fn = fn[:-len(FILE_EXT)]

        if len(fn) > MAX_FILE_NAME+len(FILE_EXT):
            fn = fn[:MAX_FILE_NAME-len(FILE_EXT)] + FILE_EXT

        return fn


async def download_to_file(session, url, folder):
    fn = make_fn_from_url(url)
    fn = os.path.join(folder, fn)
    try:
        logging.debug(f"Start download from {url}")
        with async_timeout.timeout(HTTP_TIMEOUT):
            async with session.get(url) as response:
                # TODO HTTP response code

                with open(fn, "wb") as f:
                    while True:
                        chunk = await response.content.read()
                        if not chunk:
                            break
                        f.write(chunk)
        logging.debug(f"End download from {url}")
    except Exception as e:
        raise DownloadError(url, f"Error download from {url} to {fn}") from e
    return url


async def get_urls_in_comment(session, comment_url):
    with async_timeout.timeout(HTTP_TIMEOUT):
        async with session.get(comment_url) as response:
            #TODO response code
            content = await response.text()

    urls = set()
    for comment in re.findall(comment_pattern, content):
        for url in re.findall(urls_in_comment_pattern, comment):
            urls.add(url)


async def get_news_params(session, url, n_news):
    with async_timeout.timeout(HTTP_TIMEOUT):
        async with session.get(url) as response:
            content = await response.text()

    news_params = []
    for i, info in enumerate(re.findall(news_urls_pattern, content)):
        if i >= n_news:
            break
        params = NewsParams(info[0] if SCHEME_TEMPLATE in info[0] else url+info[0],
                            info[1],
                            info[2])
        news_params.append(params)

    return news_params


def get_unprocessed_news(proccesed_urls, news_params):
    unprocessed_news = []
    for params in news_params:
        if not params.url in proccesed_urls:
            unprocessed_news.append(params)

    return unprocessed_news


async def download_one_news(session, url, title, comment_url, folder):
    def main_callback(future):
        try:
            url = future.result()
            logging.debug(f"Download main news '{title}' by url {url} complete")
        except DownloadError as e:
            logging.error(f"Error download main news '{title}' by url {e.url}")
            raise
        except Exception as e:
            logging.error(f"Unexpected error download main news '{title}'")
            raise

    def additional_callback(future):
        try:
            url = future.result()
            logging.debug(f"Download additional news for '{title}' by url {url} complete")
        except DownloadError as e:
            logging.error(f"Error download additional news for '{title}' by url {e.url}")
            raise
        except Exception as e:
            logging.error(f"Unexpected error download additional news for '{title}'")
            raise

    news_folder = title
    for c in FORBIDDEN_CHARS:
        news_folder = news_folder.replace(c, "_")
    news_folder = os.path.join(folder, news_folder)
    if not os.path.exists(news_folder):
        os.mkdir(news_folder)

    main_future = asyncio.ensure_future(download_to_file(session, url, news_folder))
    main_future.add_done_callback(main_callback)

    result = await asyncio.gather(main_future)


    return url


async def download_news_coro(folder, url, n_news, wait):
    proccesed_urls = set()

    i = 0
    while True:
        i += 1
        if CYCLES and i > CYCLES:
            break

        logging.info(f"Downloading begin, cycle {i}")

        proccesed = 0
        errors = 0

        async with aiohttp.ClientSession() as session:
            news_params = await get_news_params(session, url, n_news)

            news_params = get_unprocessed_news(proccesed_urls, news_params)
            logging.info(f"Got {len(news_params)} news")

            to_do = [download_one_news(session, params.url, params.title, params.comment_url, folder) for params in news_params]
            for future in asyncio.as_completed(to_do):
                try:
                    url = await future
                    proccesed += 1
                    proccesed_urls.add(url)
                    logging.info(f"Download news by url {url}")
                except DownloadError as e:
                    errors += 1
                    logging.exception(f"Error process news by url {e.url} - {e.msg}: ")
                except Exception as e:
                    errors += 1
                    logging.exception("Unexpected error: ")

        logging.info(f"Downloading complete, {proccesed} news proccesd, {errors} errors")
        logging.info(f"Wait {wait} seconds")
        await asyncio.sleep(wait)


def download_news(folder, url, n_news, wait):
    if not os.path.exists(folder):
        os.mkdir(folder)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(download_news_coro(folder, url, n_news, wait))
    loop.close()


def main():
    ap = ArgumentParser()
    ap.add_argument("--log", action="store", default=None)
    ap.add_argument("--news", action="store", default=MAX_NEWS)
    ap.add_argument("--folder", action="store", default=NEWS_FOLDER)
    ap.add_argument("--wait", action="store", default=WAIT)
    ap.add_argument("--url", action="store", default=BASE_URL)
    ap.add_argument("--debug", action="store_true", default=False)
    options = ap.parse_args()

    logging.basicConfig(filename=options.log, level=logging.INFO if not options.debug else logging.DEBUG,
                        format='[%(asctime)s] %(levelname).1s %(message)s', datefmt='%Y.%m.%d %H:%M:%S')

    try:
        download_news(options.folder, options.url, options.news, options.wait)
    except KeyboardInterrupt:
        logging.info("Stop")
    except Exception as e:
        logging.exception("Unexpected error: ")


if __name__ == "__main__":
    main()
