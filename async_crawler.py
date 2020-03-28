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
urls_in_comment_str_pattern = re.compile(urls_in_comment_str)



NewsParams = namedtuple("NewsParams", "url title comment_url")


NEWS_FOLDER = "news"
WAIT = 5
MAX_NEWS = 5
BASE_URL = "https://news.ycombinator.com/"
CYCLES = 5
HTTP_TIMEOUT = 10


class DownloadError(Exception):
    def __init__(self, url, msg):
        self.url = url
        self.msg = msg


async def get_news_params(session, url, n_news):
    scheme_template = "://"
    with async_timeout.timeout(HTTP_TIMEOUT):
        async with session.get(url) as response:
            content = await response.text()

    news_params = []
    for i, info in enumerate(re.findall(news_urls_pattern, content)):
        if i >= n_news:
            break
        params = NewsParams(info[0] if scheme_template in info[0] else url+info[0],
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
    return url


async def download_news_coro(folder, url, n_news, wait):
    proccesed_urls = set()

    i = 0
    while True:
        i += 1
        proccesed = 0
        errors = 0

        async with aiohttp.ClientSession() as session:
            news_params = await get_news_params(session, url, n_news)

            news_params = get_unprocessed_news(proccesed_urls, news_params)
            logging.info(f"Got {len(news_params)} news")

            to_do = [download_one_news(session, params.url, params.title, params.comment_url, folder) for params in news_params]
            for future in asyncio.as_completed(to_do):
                try:
                    url = future.result()
                    proccesed += 1

                except Exception as e:
                    errors += 1
                    logging.exception("Unexpected error: ")


        await asyncio.sleep(wait)




def download_news(folder, url, n_news, wait):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(download_news_coro(folder, url, n_news, wait))
    loop.close()

    pass


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
