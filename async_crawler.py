from argparse import ArgumentParser
import asyncio
import aiohttp
import logging
from collections import namedtuple
import re
import os
from html import unescape
from time import time
from http import HTTPStatus
import shutil
import functools

news_urls_str = "<td class=\"title\"><a href=\"(.*?)\".*?class=\"storylink\".*?>(.*?)<\/a>.*?<span class=\"age\"><a href=\"(item\?id=.*?)\">"
news_urls_pattern = re.compile(news_urls_str, re.DOTALL)

comment_str = "<span class=\"commtext c.*?\">(.*?)<div class='reply'>"
comment_pattern = re.compile(comment_str, re.DOTALL)

urls_in_comment_str = "<a href=\"(.*?)\""
urls_in_comment_pattern = re.compile(urls_in_comment_str)

NewsParams = namedtuple("NewsParams", "url title comment_url")

NEWS_FOLDER = "news"
WAIT = 30
MAX_NEWS = 30
BASE_URL = "https://news.ycombinator.com/"
MAX_CONNECTIONS = 1
CYCLES = None
HTTP_TIMEOUT = 30
FILE_EXT = ".html"
MAX_FILE_NAME = 50
FORBIDDEN_CHARS = ("/", )
SCHEME_TEMPLATE = "://"
TMP = ".tmp"


class DownloadError(Exception):
    def __init__(self, url, msg):
        self.url = url
        self.msg = msg


def move_from_tmp(from_folder, to_folder):
    if not os.path.exists(to_folder):
        os.mkdir(to_folder)

    for file in os.listdir(from_folder):
        if os.path.exists(os.path.join(to_folder, file)):
            os.remove(os.path.join(to_folder, file))
        shutil.move(os.path.join(from_folder, file), to_folder)

    os.rmdir(from_folder)


def remove_tmp(folder):
    if not os.path.exists(folder):
        return

    for file in os.listdir(folder):
        os.remove(os.path.join(folder, file))
    os.rmdir(folder)


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

    if "." in fn:
        ext = "." + fn.split(".")[-1]
    else:
        ext = FILE_EXT

    if fn.lower().endswith(ext.lower()):
        fn = fn[:-len(ext)]

    if len(fn) > MAX_FILE_NAME+len(ext):
        fn = fn[:MAX_FILE_NAME-len(ext)] + ext
    else:
        fn = fn + ext

    return fn


async def get_response(session, url, err_msg):
    response = await session.get(url)
    if response.status != HTTPStatus.OK:
        raise DownloadError(url, err_msg + f", response status {response.status}")
    return response


async def download_to_file(session, url, folder):
    fn = make_fn_from_url(url)
    fn = os.path.join(folder, fn)
    try:
        logging.debug(f"Start download from {url} to {fn}")
        response = await get_response(session, url, "Error download to file")
        async with response:
            with open(fn, "wb") as f:
                while True:
                    chunk = await response.content.read()
                    if not chunk:
                        break
                    f.write(chunk)
        logging.debug(f"End download from {url}to {fn}")

    except Exception as e:
        raise DownloadError(url, f"Error download from {url} to {fn}") from e

    return url


async def get_urls_in_comment(session, base_url, comment_url, conections_sem):

    async with conections_sem:
        response = await get_response(session, comment_url, f"Error load comment page {comment_url}")
        async with response:
            content = await response.text()

    urls = set()
    for comment in re.findall(comment_pattern, content):
        for url in re.findall(urls_in_comment_pattern, comment):
            url = unescape(url)
            if SCHEME_TEMPLATE not in url:
                url = base_url + url

            urls.add(url)

    return urls


async def get_news_params(session, url, n_news):
    response = await get_response(session, url, f"Error load main page {url}")
    async with response:
        content = await response.text()

    news_params = []
    for i, info in enumerate(re.findall(news_urls_pattern, content)):
        if i >= n_news:
            break
        params = NewsParams(info[0] if SCHEME_TEMPLATE in info[0] else url+info[0],
                            info[1],
                            info[2] if SCHEME_TEMPLATE in info[2] else url+info[2])
        news_params.append(params)

    return news_params


def get_unprocessed_news(processed_urls, news_params):
    unprocessed_news = []
    for params in news_params:
        if params.url not in processed_urls:
            unprocessed_news.append(params)

    return unprocessed_news


async def download_one_news(session, url, title, comment_url, folder, connections_sem):
    def callback(future, is_main=True):
        try:
            processed_url = future.result()
            if is_main:
                logging.debug(f"Download main news '{title}' by url {processed_url} complete")
            else:
                logging.debug(f"Download additional news for '{title}' by url {processed_url} complete")
        except DownloadError as e:
            if is_main:
                logging.exception(f"Error download main news '{title}' by url {e.url}")
            else:
                logging.exception(f"Error download additional news for '{title}' by url {e.url}")
            raise
        except Exception:
            if is_main:
                logging.exception(f"Unexpected error download main news '{title}'")
            else:
                logging.exception(f"Unexpected error download additional news for '{title}'")
            raise

    news_folder = title
    for c in FORBIDDEN_CHARS:
        news_folder = news_folder.replace(c, "_")
    news_folder_tmp = os.path.join(folder, TMP + news_folder)
    news_folder = os.path.join(folder, news_folder)
    if not os.path.exists(news_folder_tmp):
        os.mkdir(news_folder_tmp)

    try:
        main_task = asyncio.create_task(download_to_file(session, url, news_folder_tmp))
        main_task.add_done_callback(callback)
        await main_task

        urls_in_comment = await get_urls_in_comment(session, url, comment_url, connections_sem)

        additional_tasks = []
        for url_in_comment in urls_in_comment:
            additional_task = asyncio.create_task(download_to_file(session, url_in_comment, news_folder_tmp))
            additional_task.add_done_callback(functools.partial(callback, is_main=False))
            additional_tasks.append(additional_task)

        additional_gather = asyncio.gather(*additional_tasks, return_exceptions=True)
        additional_results = await additional_gather

        for res in additional_results:
            if isinstance(res, Exception):
                logging.info(f"Not all additional news for '{title}' downloaded")
                break

        move_from_tmp(news_folder_tmp, news_folder)
    except Exception:
        remove_tmp(news_folder_tmp)
        raise

    return url, title


async def download_news_coro(folder, url, n_news, wait, main_url_connections):
    processed_urls = set()
    connections_sem = asyncio.Semaphore(main_url_connections)

    i = 0
    while True:
        t = time()
        i += 1
        if CYCLES and i > CYCLES:
            break

        logging.info(f"Downloading begin, cycle {i}")

        processed = 0
        errors = 0

        timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            news_params = await get_news_params(session, url, n_news)

            news_params = get_unprocessed_news(processed_urls, news_params)
            logging.info(f"Got {len(news_params)} news")

            to_do = [download_one_news(session, params.url, params.title, params.comment_url, folder, connections_sem) for params in news_params]
            for task in asyncio.as_completed(to_do):
                try:
                    processed_url, processed_title = await task
                    processed += 1
                    processed_urls.add(processed_url)
                    logging.info(f"Download complete for news '{processed_title}' by url {processed_url}")
                except DownloadError as e:
                    errors += 1
                    logging.exception(f"Error process news by url {e.url} - {e.msg}: ")
                except Exception:
                    errors += 1
                    logging.exception("Unexpected error: ")

        work_time = time()-t
        wait_time = int(wait - work_time if work_time < wait else 0)
        logging.info(f"Downloading complete for {work_time:.2f} seconds, {processed} news proccesd, {errors} errors")

        logging.info(f"Wait {wait_time} seconds")
        await asyncio.sleep(wait_time)


def download_news(folder, url, n_news, wait, main_url_connections):
    if not os.path.exists(folder):
        os.mkdir(folder)

    asyncio.run(download_news_coro(folder, url, n_news, wait, main_url_connections))


def main():
    ap = ArgumentParser()
    ap.add_argument("--log", action="store", default=None)
    ap.add_argument("--news", action="store", default=MAX_NEWS)
    ap.add_argument("--folder", action="store", default=NEWS_FOLDER)
    ap.add_argument("--wait", action="store", default=WAIT)
    ap.add_argument("--url", action="store", default=BASE_URL)
    ap.add_argument("--connections", action="store", default=MAX_CONNECTIONS)
    ap.add_argument("--debug", action="store_true", default=False)
    options = ap.parse_args()

    logging.basicConfig(filename=options.log, level=logging.INFO if not options.debug else logging.DEBUG,
                        format='[%(asctime)s] %(levelname).1s %(message)s', datefmt='%Y.%m.%d %H:%M:%S')

    try:
        download_news(options.folder, options.url, options.news, options.wait, options.connections)
    except KeyboardInterrupt:
        logging.info("Stop")
    except Exception:
        logging.exception("Unexpected error: ")


if __name__ == "__main__":
    main()
