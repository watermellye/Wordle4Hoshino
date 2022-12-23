import re
import shlex
import asyncio
import base64
from io import BytesIO
from dataclasses import dataclass
from asyncio import TimerHandle
from tracemalloc import stop
from typing import Dict, List, Optional, NoReturn

import json
from fuzzywuzzy import process

import hoshino
from hoshino import Service
from hoshino.typing import CQEvent, HoshinoBot

from nonebot import MessageSegment

from .utils import dic_list, random_word, get_word_list
from .data_source import Wordle, GuessResult, min_len, max_len

HELP_MSG = f'''
指令列表（发送时不含尖括号）：

开始游戏指令：猜单词<字母数(默认为5)> <来源词库(默认为CET4)>
支持的词典：CET4 CET6 GMAT GRE IELTS SAT TOEFL 专八 专四 考研

猜单词指令：我猜<单词>
或直接发送<单词>，但仅响应字母位数正确的单词

提示指令：猜单词提示
终止游戏指令：猜单词结束

绿色块代表此单词中有此字母且位置正确；
黄色块代表此单词中有此字母，但该字母所处位置不对；
灰色块代表此单词中没有此字母；
特别的，若猜测单词中出现x个相同的字母，但只有y个颜色为灰色时，表示原单词中存在x-y个该字母。

提示中的灰色块表示肯定不会在原单词中出现的字母；
提示中的蓝色块表示在所有猜测单词中从未出现的字母。
'''.strip()

sv = hoshino.Service('猜单词', visible=True, enable_on_default=True, help_=HELP_MSG)


@sv.on_fullmatch('猜单词帮助')
async def wordleHelp(bot, ev: CQEvent):
    bot.finish(ev, HELP_MSG)

# parser = ArgumentParser("wordle", description="猜单词")
# parser.add_argument("-l", "--length", type=int, default=5, help="单词长度")
# parser.add_argument("-d", "--dic", default="CET4", help="词典")
# parser.add_argument("--hint", action="store_true", help="提示")
# parser.add_argument("--stop", action="store_true", help="结束游戏")
# parser.add_argument("word", nargs="?", help="单词")


@dataclass
class Options:
    length: int = 0
    dic: str = ""
    hint: bool = False
    stop: bool = False
    word: str = ""


games: Dict[str, Wordle] = {}
timers: Dict[str, TimerHandle] = {}

words_by_len = get_word_list()


def get_cid(event):
    return f"group_{event.group_id}" if event.group_id else f"private_{event.user_id}"


def game_running(event) -> bool:
    cid = get_cid(event)
    return bool(games.get(cid, None))


@sv.on_prefix('猜单词', 'wordle')
async def _(bot, ev: CQEvent):
    cid = get_cid(ev)
    if games.get(cid, None):
        await bot.send(ev, "已有游戏进行中\n如需终止，请发送“猜单词结束”")
    else:
        args = ev.message.extract_plain_text().split()
        args = [i.upper() for i in args]
        argv = []
        if len(args) == 0:
            # print('0参数')
            await handle_wordle(bot, ev, ["--length", "5", "--dic", "CET4"])
        elif len(args) == 1:
            # print('1参数')
            if args[0].isdigit():
                argv.append('--length')
                argv.append(args[0])
                argv.append('--dic')
                argv.append('CET4')
            elif args[0] in dic_list:
                argv.append('--dic')
                argv.append(args[0])
                argv.append('--length')
                argv.append('5')
            else:
                await bot.finish(ev, "无效的参数哦", at_sender=True)
            await handle_wordle(bot, ev, argv)
        elif len(args) == 2:
            # print('2参数')
            if args[0].isdigit():
                argv.append('--length')
                argv.append(args[0])
            else:
                await bot.finish(ev, f'第一个参数需要是[{min_len}, {max_len}]的整数', at_sender=True)
            if args[1] in dic_list:
                argv.append('--dic')
                argv.append(args[1])
            else:
                await bot.finish(ev, "第二个参数需要是支持的字典", at_sender=True)
            await handle_wordle(bot, ev, argv)
        else:
            # print('不行参数')
            await bot.finish(ev, "无效的猜单词指令哦", at_sender=True)


@sv.on_fullmatch('猜单词提示')
async def _(bot, ev):
    await handle_wordle(bot, ev, ["--hint"])


@sv.on_fullmatch('猜单词结束')
async def _(bot, ev):
    await handle_wordle(bot, ev, ["--stop"])


@sv.on_prefix("我猜")
async def _(bot, ev):
    text = str(ev.message).strip()
    if text:
        await handle_wordle(bot, ev, [text])


@sv.on_message()
async def _(bot, ev):
    text = str(ev.message).strip()
    if min_len <= len(text) <= max_len:
        if re.fullmatch(r"^[a-zA-Z]+$", text) is not None:
            await handle_wordle(bot, ev, [text], no_response=True)


async def stop_game(bot, ev, cid: str):
    timers.pop(cid, None)
    if games.get(cid, None):
        game = games.pop(cid)
        msg = "猜单词超时，游戏结束"
        if len(game.guessed_words) >= 1:
            msg += f"\n{game.result}"
        await bot.finish(ev, msg)


def set_timeout(bot, ev, cid: str, timeout: float = 300):
    timer = timers.get(cid, None)
    if timer:
        timer.cancel()
    loop = asyncio.get_running_loop()
    timer = loop.call_later(
        timeout, lambda: asyncio.ensure_future(stop_game(bot, ev, cid))
    )
    timers[cid] = timer


async def handle_wordle(bot: HoshinoBot, ev, argv: List[str], no_response=False):
    # print("读取", argv)

    async def send(message: Optional[str] = None, image: Optional[BytesIO] = None) -> NoReturn:
        if no_response:
            await bot.finish(ev, "")
        msg = []
        if image:
            byte_data = image.getvalue()
            base64_str = base64.b64encode(byte_data).decode()
            image = 'base64://' + base64_str
            msg.append(f'{MessageSegment.image(image)}')
        if message:
            msg.append(f'{message}')
        msg = "\n".join(msg)
        await bot.finish(ev, msg.strip())  # 如果消息为空不会执行发送，仅利用bot.finish的机制将当前会话结束。

    args = {'length': 0, 'dic': "", 'hint': False, 'stop': False, 'word': ""}
    N = len(argv)
    if N == 1:
        if (argv[0] == '--hint'):
            args['hint'] = True
        elif argv[0] == '--stop':
            args['stop'] = True
        else:
            args["word"] = argv[0]
    else:
        for i in range(0, N):
            if (argv[i] == '--hint'):
                args["hint"] = True
            if (argv[i] == '--stop'):
                args["stop"] = True
            if (argv[i] == '--length'):
                args["length"] = int(argv[i + 1])
            if (argv[i] == '--dic'):
                args["dic"] = argv[i + 1]
    # print("解析", args)
    options = Options(**args)

    cid = get_cid(ev)
    if not games.get(cid, None):
        if options.word or options.stop or options.hint:
            await send("没有正在进行的游戏")

        if not (options.length and options.dic):
            await send("请指定单词长度和词典")

        if options.length < min_len or options.length > max_len:
            await send(f'仅接受{min_len}-{max_len}个字母的单词')

        if options.dic not in dic_list:
            await send("支持的词典：" + ", ".join(dic_list))

        word, meaning = random_word(options.dic, options.length)
        print(f'\n\n\n正确答案为：{word}\n正确答案为：{word}\n正确答案为：{word}\n\n\n')
        game = Wordle(word, meaning)
        games[cid] = game
        set_timeout(bot, ev, cid)

        await send(f"你有{game.rows}次机会猜出单词，单词长度为{game.length}，请发送单词", game.draw())
    if options.stop:
        game = games.pop(cid)
        msg = "游戏已结束"
        if len(game.guessed_words) >= 1:
            msg += f"\n{game.result}"
        await send(msg)

    game = games[cid]
    set_timeout(bot, ev, cid)

    if options.hint:
        hint = game.get_hint()
        if not hint.replace("*", ""):
            await send("你还没有猜对过一个字母哦~再猜猜吧~")
        await send(image=game.draw_hint(hint))

    word = options.word

    if not (re.fullmatch(r"^[a-zA-Z]+$", word) is not None and min_len <= len(word) <= max_len):
        await send(f'仅接受{min_len}-{max_len}个字母的单词')

    if len(word) != game.length:
        await send(f'请发送长度为{game.length}的单词 len({word})={len(word)}')

    no_response = False
    result = game.guess(word)
    if result in [GuessResult.WIN, GuessResult.LOSS]:
        games.pop(cid)
        await send(
            ("恭喜你猜出了单词！" if result == GuessResult.WIN else "很遗憾，没有人猜出来呢")
            + f"\n{game.result}",
            game.draw(),
        )
    elif result == GuessResult.DUPLICATE:
        await send("你已经猜过这个单词了呢")
    elif result == GuessResult.ILLEGAL:
        le = str(len(word))
        if le in words_by_len:
            guess_word, score = process.extractOne(word.lower(), words_by_len[le].keys(), processor=my_lower)
            await send(f'{word}不被接受\n您有{score}%可能说的是{guess_word}\n({words_by_len[le][guess_word].strip()})')
        await send(f"你确定{word}是一个合法的单词吗？")
    else:

        await send(image=game.draw())


def my_lower(string) -> str:
    return string.lower()
