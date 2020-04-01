## Async crawler for https://news.ycombinator.com/

Download news from links from the main page https://news.ycombinator.com/, as well as from all links from comments

### Requirements
Python 3.7+

aiohttp 3.3+

#### Installing required packages

pip install -r requirements.txt 

### Run

python async_crawler.py


optional arguments:

--log - log file

--news - max news for downloading

--folder - folder for downloading

--wait - waiting before next run

--url - Hacker News url

--connections -  max connection to ycombinator

--debug - debug level for logging
