import asyncio


async def do():
    print("1")
    await asyncio.sleep(4)
    print("2")
    raise ValueError("123")


async def to_do():
    to_do_list = [asyncio.ensure_future(do()) for i in range(5)]
    try:
        res = await asyncio.gather(*to_do_list)
    except Exception as e:
        print(f"error {e}")
        for future in to_do_list:
            print(future.done())


loop = asyncio.get_event_loop()
loop.run_until_complete(to_do())
loop.close()