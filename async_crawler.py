from argparse import ArgumentParser
import asyncio
import aiohttp
import async_timeout
import logging
from collections import namedtuple

NewsParams = namedtuple("NewsParams", "url title comment_url")


NEWS_FOLDER = "news"
WAIT = 30
MAX_NEWS = 5
BASE_URL = "https://news.ycombinator.com/"
CYCLES = 5


async def download_news_coro(folder, url, n_news, wait):
    i = 0
    while True:
        i += 1




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
