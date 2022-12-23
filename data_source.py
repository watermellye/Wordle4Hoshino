from enum import Enum
from io import BytesIO
from PIL import Image, ImageDraw
from PIL.Image import Image as IMG
from typing import Tuple, List, Optional

from .utils import legal_word, load_font, save_png

min_len = 4
max_len = 10


class GuessResult(Enum):
    WIN = 0  # 猜出正确单词
    LOSS = 1  # 达到最大可猜次数，未猜出正确单词
    DUPLICATE = 2  # 单词重复
    ILLEGAL = 3  # 单词不合法


class Wordle(object):
    def __init__(self, word: str, meaning: str):
        self.word: str = word  # 单词
        self.meaning: str = meaning  # 单词释义
        self.result = f"【单词】：{self.word}\n【释义】：{self.meaning}"
        self.word_lower: str = self.word.lower()
        self.length: int = len(word)  # 单词长度
        self.rows: int = max(self.length + 1, 11 - self.length)  # 可猜次数
        self.guessed_words: List[str] = []  # 记录已猜单词

        self.block_size = (40, 40)  # 文字块尺寸
        self.block_padding = (10, 10)  # 文字块之间间距
        self.padding = (20, 20)  # 边界间距
        self.border_width = 2  # 边框宽度
        self.font_size = 20  # 字体大小
        self.font = load_font("KarnakPro-Bold.ttf", self.font_size)

        self.correct_color = (134, 163, 115)  # 存在且位置正确时的颜色
        self.green_color = self.correct_color
        self.exist_color = (198, 182, 109)  # 存在但位置不正确时的颜色
        self.yellow_color = self.exist_color
        self.wrong_color = (123, 123, 124)  # 不存在时颜色
        self.grey_color = self.wrong_color
        self.border_color = (123, 123, 124)  # 边框颜色
        self.bg_color = (255, 255, 255)  # 背景颜色
        self.font_color = (255, 255, 255)  # 文字颜色
        self.unknown_color = (15, 190, 192)

    def guess(self, word: str) -> Optional[GuessResult]:
        word = word.lower()
        if not legal_word(word):
            if not legal_word(f'{word[0].upper()}{word[1:]}'):
                return GuessResult.ILLEGAL

        if word in self.guessed_words:
            return GuessResult.DUPLICATE
        self.guessed_words.append(word)
        if word == self.word_lower:
            return GuessResult.WIN
        if len(self.guessed_words) == self.rows:
            return GuessResult.LOSS

    def draw_block(self, color: Tuple[int, int, int], letter: str, font_color=None, border_color=None) -> IMG:
        block = Image.new("RGB", self.block_size, (border_color or self.border_color))
        inner_w = self.block_size[0] - self.border_width * 2
        inner_h = self.block_size[1] - self.border_width * 2
        inner = Image.new("RGB", (inner_w, inner_h), color)
        block.paste(inner, (self.border_width, self.border_width))
        if len(letter):
            letter = letter.upper()
            draw = ImageDraw.Draw(block)
            letter_size = self.font.getsize(letter)
            x = (self.block_size[0] - letter_size[0]) / 2
            y = (self.block_size[1] - letter_size[1]) / 2
            draw.text((x, y), letter, font=self.font, fill=(font_color or self.font_color))
        return block

    def get_color(self, origin_word, guess_word):
        colors = [self.wrong_color for _ in range(self.length)]
        char_dict = {}
        for i in range(self.length):
            oc = origin_word[i]
            gc = guess_word[i]
            if oc == gc:
                colors[i] = self.correct_color
            else:
                char_dict[oc] = char_dict.get(oc, 0) + 1
        for i in range(self.length):
            oc = origin_word[i]
            gc = guess_word[i]
            if oc != gc:
                if char_dict.get(gc, 0):
                    colors[i] = self.exist_color
                    char_dict[gc] -= 1

        return colors

    def generate_canvas(self, col, row):
        board_w = col * self.block_size[0]
        board_w += (col - 1) * self.block_padding[0] + 2 * self.padding[0]
        board_h = row * self.block_size[1]
        board_h += (row - 1) * self.block_padding[1] + 2 * self.padding[1]
        board_size = (board_w, board_h)
        board = Image.new("RGB", board_size, self.bg_color)
        return board, board_size

    def get_pos(self, col, row):
        x = self.padding[0] + (self.block_size[0] + self.block_padding[0]) * col
        y = self.padding[1] + (self.block_size[1] + self.block_padding[1]) * row
        return (x, y)

    def draw(self) -> BytesIO:
        board, board_size = self.generate_canvas(self.length, self.rows)

        for i in range(self.rows):
            if i < len(self.guessed_words):
                colors = self.get_color(self.word_lower, self.guessed_words[i])
                word = self.guessed_words[i]
            else:
                colors = [self.bg_color for _ in range(self.length)]
                word = ["" for _ in range(self.length)]

            for j in range(self.length):
                board.paste(self.draw_block(colors[j], word[j]), self.get_pos(j, i))

        # 接下来是为提升游戏性做的提示渲染
        hint_row_cnt = 0
        hint_col_cnt = max(min(self.length + 2, max_len), 5)

        # 根据所有已猜测结果，已确定位置的字母
        color_only_green = [self.bg_color for _ in range(self.length)]
        word_only_green = ["?" for _ in range(self.length)]
        for guess_word in self.guessed_words:
            colors = self.get_color(self.word_lower, guess_word)
            for j in range(self.length):
                if colors[j] == self.correct_color:
                    color_only_green[j] = self.correct_color
                    word_only_green[j] = guess_word[j]
        if word_only_green.count("?") != self.length:
            hint_row_cnt += 1

        # 已经被排除的字母
        word_wrong = []
        for guess_word in self.guessed_words:
            for cha in guess_word:
                if cha not in self.word_lower:
                    word_wrong.append(cha)
        word_wrong = list(sorted(set(word_wrong)))
        if len(word_wrong) > 15:
            word_wrong = [f'{len(word_wrong)}']
        if len(word_wrong):
            hint_row_cnt += (len(word_wrong) + 2 - 1) // hint_col_cnt + 1

        # 所有已猜测结果中均未出现的字母
        word_26 = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m", "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z"]
        word_appear = []
        for guess_word in self.guessed_words:
            for cha in guess_word:
                word_appear.append(cha)
        word_never_appear = list(sorted(set(word_26) - set(word_appear)))
        if len(word_never_appear) > 13:
            word_never_appear = [f'{len(word_never_appear)}']
        if len(word_never_appear):
            hint_row_cnt += (len(word_never_appear) + 2 - 1) // hint_col_cnt + 1

        # 根据所有已猜测结果，不确定位置但知道存在的字母
        word_yellow = {}
        for guess_word in self.guessed_words:
            word_yellow_g = {}
            colors = self.get_color(self.word_lower, guess_word)
            for j in range(self.length):
                if colors[j] != self.wrong_color:
                    word_yellow_g[guess_word[j]] = word_yellow_g.get(guess_word[j], 0) + 1
            for cha in word_yellow_g:
                word_yellow[cha] = max(word_yellow.get(cha, 0), word_yellow_g[cha])
        for cha in word_only_green:
            if cha in word_yellow:
                word_yellow[cha] -= 1
                if word_yellow[cha] == 0:
                    word_yellow.pop(cha)
        word_yellow_item = sorted(word_yellow.items())
        word_yellow = []
        for k, v in word_yellow_item:
            word_yellow += [k for _ in range(v)]
        if len(word_yellow):
            hint_row_cnt += (len(word_yellow) + 2 - 1) // hint_col_cnt + 1

        # print()
        # print(f'green= {word_only_green}')
        # print(f'yellow={word_yellow}')
        # print(f'blue=  {word_never_appear}')
        # print(f'length={self.length} row_cnt={hint_row_cnt}')
        # print()

        if hint_row_cnt == 0:
            return save_png(board)

        # 改为获取真实宽度
        hint_col_cnt = 0
        if word_only_green.count("?") != self.length:
            hint_col_cnt = max(hint_col_cnt, self.length)
        if len(word_yellow):
            hint_col_cnt = max(hint_col_cnt, len(word_yellow) + 2)
        if len(word_wrong):
            hint_col_cnt = max(hint_col_cnt, len(word_wrong) + 2)
        if len(word_never_appear):
            hint_col_cnt = max(hint_col_cnt, len(word_never_appear) + 2)
        hint_col_cnt = min(self.length + 2, max_len, hint_col_cnt)

        hint_board, hint_board_size = self.generate_canvas(hint_col_cnt, hint_row_cnt)
        hint_now_row = 0
        if word_only_green.count("?") != self.length:
            for j in range(self.length):
                hint_board.paste(self.draw_block(color_only_green[j], word_only_green[j]), self.get_pos(j, hint_now_row))
            hint_now_row += 1

        if len(word_yellow):
            hint_board.paste(self.draw_block(self.yellow_color, ""), self.get_pos(0, hint_now_row))
            hint_board.paste(self.draw_block(self.bg_color, "=", self.grey_color, self.bg_color), self.get_pos(1, hint_now_row))
            now_col = 1
            for cha in word_yellow:
                now_col += 1
                if now_col == hint_col_cnt:
                    now_col = 0
                    hint_now_row += 1
                hint_board.paste(self.draw_block(self.yellow_color, cha), self.get_pos(now_col, hint_now_row))
            hint_now_row += 1

        if len(word_wrong):
            hint_board.paste(self.draw_block(self.grey_color, ""), self.get_pos(0, hint_now_row))
            hint_board.paste(self.draw_block(self.bg_color, "=", self.grey_color, self.bg_color), self.get_pos(1, hint_now_row))
            now_col = 1
            for cha in word_wrong:
                now_col += 1
                if now_col == hint_col_cnt:
                    now_col = 0
                    hint_now_row += 1
                hint_board.paste(self.draw_block(self.grey_color, cha), self.get_pos(now_col, hint_now_row))
            hint_now_row += 1

        if len(word_never_appear):
            hint_board.paste(self.draw_block(self.unknown_color, "?"), self.get_pos(0, hint_now_row))
            hint_board.paste(self.draw_block(self.bg_color, "=", self.grey_color, self.bg_color), self.get_pos(1, hint_now_row))
            now_col = 1
            for cha in word_never_appear:
                now_col += 1
                if now_col == hint_col_cnt:
                    now_col = 0
                    hint_now_row += 1
                hint_board.paste(self.draw_block(self.unknown_color, cha), self.get_pos(now_col, hint_now_row))

        # all_board = Image.new("RGB", (max(board_size[0], hint_board_size[0]), hint_board_size[1] + board_size[1]), self.bg_color)
        # all_board.paste(board)
        # all_board.paste(hint_board, (0, board_size[1]))
        all_board = Image.new("RGB", (board_size[0] + hint_board_size[0], max(hint_board_size[1], board_size[1])), self.bg_color)
        all_board.paste(board)
        all_board.paste(hint_board, (board_size[0], 0))
        return save_png(all_board)

    def get_hint(self) -> str:
        letters = set()
        for word in self.guessed_words:
            for letter in word:
                if letter in self.word_lower:
                    letters.add(letter)
        return "".join([i if i in letters else "*" for i in self.word_lower])

    def draw_hint(self, hint: str) -> BytesIO:
        board_w = self.length * self.block_size[0]
        board_w += (self.length - 1) * self.block_padding[0] + 2 * self.padding[0]
        board_h = self.block_size[1] + 2 * self.padding[1]
        board = Image.new("RGB", (board_w, board_h), self.bg_color)

        for i in range(len(hint)):
            letter = hint[i].replace("*", "")
            color = self.correct_color if letter else self.bg_color
            x = self.padding[0] + (self.block_size[0] + self.block_padding[0]) * i
            y = self.padding[1]
            board.paste(self.draw_block(color, letter), (x, y))
        return save_png(board)
