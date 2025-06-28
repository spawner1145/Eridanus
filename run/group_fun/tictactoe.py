import os
import time
import PIL.Image
from PIL import ImageDraw, ImageFont
from run.group_fun.service.TicTacToe import TicTacToeManager
from developTools.event.events import GroupMessageEvent
from developTools.message.message_components import Node, Text, Image, At
from framework_common.utils.utils import delay_recall

def _create_board_image(board_str):
    """
    Creates a PNG image of the Tic-Tac-Toe board from a string representation.
    Adds row and column numbers and uses a larger font for the pieces.
    """
    cell_size = 60  # Increased cell size for better spacing
    padding = 20    # Increased padding
    line_width = 3
    
    # Split the board string into rows
    rows = board_str.strip().split('\n')
    board_height = len(rows)
    board_width = len(rows[0].split(' '))
    
    # Calculate image dimensions, adding space for row/column numbers
    img_width = board_width * cell_size + 2 * padding + 30 # Extra space for row numbers
    img_height = board_height * cell_size + 2 * padding + 30 # Extra space for column numbers
    image = PIL.Image.new('RGB', (img_width, img_height), 'white')
    draw = ImageDraw.Draw(image)
    
    try:
        # Use a larger font for pieces and numbers
        font_piece = ImageFont.truetype("arial.ttf", size=40)
        font_num = ImageFont.truetype("arial.ttf", size=20)
    except IOError:
        font_piece = ImageFont.load_default()
        font_num = ImageFont.load_default()

    # Draw grid lines
    # Horizontal lines
    for i in range(board_height + 1):
        y_pos = padding + i * cell_size + 30
        draw.line([(padding + 30, y_pos), (img_width - padding, y_pos)], fill='black', width=line_width)
    # Vertical lines
    for j in range(board_width + 1):
        x_pos = padding + j * cell_size + 30
        draw.line([(x_pos, padding + 30), (x_pos, img_height - padding)], fill='black', width=line_width)

    # Draw row numbers on the left
    for r_idx in range(board_height):
        y_pos = padding + r_idx * cell_size + (cell_size // 2) + 30
        draw.text((padding, y_pos), str(r_idx + 1), fill='black', font=font_num)

    # Draw column numbers on the top
    for c_idx in range(board_width):
        x_pos = padding + c_idx * cell_size + (cell_size // 2) + 30
        draw.text((x_pos, padding), str(c_idx + 1), fill='black', font=font_num)

    # Draw pieces (X, O) on the board
    for r_idx, row in enumerate(rows):
        pieces = row.split(' ')
        for c_idx, piece in enumerate(pieces):
            if piece != 'O':  # Assuming 'O' is an empty cell in the string
                # Center the piece within the cell
                bbox = font_piece.getbbox(piece)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                
                # Adjust position to account for padding and numbering
                text_x = padding + c_idx * cell_size + (cell_size - text_width) // 2 + 30
                text_y = padding + r_idx * cell_size + (cell_size - text_height) // 2 + 30
                
                # Use a specific color for the piece for better visibility
                draw.text((text_x, text_y), piece, fill='red' if piece == 'X' else 'blue', font=font_piece)
                
    # Save the image to a temporary file
    temp_dir = 'data/pictures/cache'
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
    
    filename = f"board_{int(time.time())}.png"
    file_path = os.path.join(temp_dir, filename)
    image.save(file_path)
    
    return file_path

async def _parse_response_string(bot, response_str, use_at=True):
    components = []
    image_parts = response_str.split('||')
    
    for i, image_part in enumerate(image_parts):
        if i % 2 == 1:
            board_str = image_part.strip()
            image_path = _create_board_image(board_str)
            components.append(Image(file=image_path))
        else:
            text_parts = image_part.split('|')
            for j, text_part in enumerate(text_parts):
                if j % 2 == 1:
                    try:
                        user_id = int(text_part)
                        if use_at:
                            components.append(At(qq=user_id))
                        else:
                            try:
                                data = await bot.get_stranger_info(user_id=user_id)
                                name = data["data"]["nickname"]
                                components.append(Text(text=name))
                            except Exception as e:
                                print(f"Error fetching nickname for {user_id}: {e}")
                                components.append(Text(text=f'|{user_id}|'))
                    except ValueError:
                        components.append(Text(text=f'|{text_part}|'))
                else:
                    if text_part:
                        components.append(Text(text=text_part))
                    
    return components

def main(bot, config):
    game = TicTacToeManager()
    
    @bot.on(GroupMessageEvent)
    async def start_game(event: GroupMessageEvent):
        if "创建棋局" in event.pure_text:
            print("开始井字棋游戏")
            response_str = game.create_game(str(event.user_id), event.pure_text)
            msg = await bot.send(event, await _parse_response_string(bot, response_str, use_at=True))
            await delay_recall(bot, msg, 10)
            
    @bot.on(GroupMessageEvent)
    async def join_game(event: GroupMessageEvent):
        if event.pure_text.startswith("加入棋局 "):
            try:
                cmd = int(event.pure_text.replace("加入棋局 ", ""))
                response_str = game.join_game(str(event.user_id), cmd)
                msg = await bot.send(event, await _parse_response_string(bot, response_str, use_at=True))
                await delay_recall(bot, msg, 10)
            except ValueError:
                msg = await bot.send(event, [Text(text="错误：棋局ID必须是数字")])
                await delay_recall(bot, msg, 10)
    
    @bot.on(GroupMessageEvent)
    async def make_move(event: GroupMessageEvent):
        if event.pure_text.startswith("落子 "):
            cmd = event.pure_text.replace("落子 ", "")
            response_str = game.place_piece(str(event.user_id), cmd)
            msg = await bot.send(event, await _parse_response_string(bot, response_str, use_at=True))
            await delay_recall(bot, msg, 60)
            
    @bot.on(GroupMessageEvent)
    async def leave_game(event: GroupMessageEvent):
        if event.pure_text == "退出棋局":
            response_str = game.leave_game(str(event.user_id))
            msg = await bot.send(event, [Text(text=response_str)])
            await delay_recall(bot, msg, 10)
            
    @bot.on(GroupMessageEvent)
    async def game_status(event: GroupMessageEvent):
        if event.pure_text == "棋局信息":
            response_str = game.show_games()
            msg = await bot.send(event, await _parse_response_string(bot, response_str, use_at=False))
            await delay_recall(bot, msg, 10)
            
    @bot.on(GroupMessageEvent)
    async def del_game(event: GroupMessageEvent):
        if event.pure_text == "删除棋局":
            response_str = game.delete_game(str(event.user_id))
            msg = await bot.send(event, [Text(text=response_str)])
            await delay_recall(bot, msg, 10)
