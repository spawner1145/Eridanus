import sys

class TicTacToeGame:

    def __init__(self, a=3, b=3, n=3, l=2):
        """
        初始化游戏
        a (int): 棋盘的行数
        b (int): 棋盘的列数
        n (int): 获胜所需的连子数
        l (int): 最大玩家数
        """
        self.board = [['O' for _ in range(b)] for _ in range(a)]
        self.players = {}  # {player_id: piece_num}
        self.max_players = l
        self.win_length = n
        self.current_turn_index = 0  # 使用索引来追踪当前玩家
        self.game_over = False
        self.winner = None

    def add_player(self, player_id):
        if len(self.players) >= self.max_players:
            return "错误：该游戏已满"
        if player_id in self.players:
            return "错误：该玩家已加入此游戏"

        piece = len(self.players) + 1
        self.players[player_id] = str(piece) # 棋子编号存储为字符串
        return f"玩家|{player_id}|成功加入游戏，使用棋子{piece}"

    def remove_player(self, player_id):
        if player_id not in self.players:
            return False

        player_list = list(self.players.keys())
        try:
            removed_player_index = player_list.index(player_id)
        except ValueError:
            return False # Should not happen

        del self.players[player_id]

        new_players = {}
        piece_counter = 1
        sorted_pids = sorted(self.players.keys())
        for pid in sorted_pids:
            new_players[pid] = str(piece_counter)
            piece_counter += 1
        self.players = new_players

        if len(self.players) > 0:
            if removed_player_index == self.current_turn_index:
                self.current_turn_index = self.current_turn_index % len(self.players)
            elif removed_player_index < self.current_turn_index:
                self.current_turn_index = (self.current_turn_index - 1) % len(self.players)
            if self.current_turn_index >= len(self.players):
                self.current_turn_index = 0
        else:
            self.current_turn_index = 0
        
        return True

    def make_move(self, player_id, position):
        """
        玩家落子
        :param player_id: 玩家ID
        :param position: 落子位置，格式为 "行,列"（例如 "1,2"）
        :return: 落子结果信息
        """
        if player_id not in self.players:
            return "错误：玩家未加入此游戏"

        if len(self.players) < self.max_players:
            return f"错误：玩家人数未满，当前玩家数: {len(self.players)}/{self.max_players}"

        player_list = list(self.players.keys())
        if not player_list:
            return "错误：游戏中没有玩家"

        if player_list[self.current_turn_index] != player_id:
            current_player_id = player_list[self.current_turn_index]
            return f"错误：现在是玩家|{current_player_id}|的回合，请稍候"

        try:
            x_str, y_str = position.split(',')
            x, y = int(x_str) - 1, int(y_str) - 1
            if not (0 <= x < len(self.board) and 0 <= y < len(self.board[0])):
                return f"错误：无效的坐标。请使用 1 到 {len(self.board)} 的行号和 1 到 {len(self.board[0])} 的列号。"
        except ValueError:
            return "错误：位置格式错误，请使用行,列形式（例如：1,2）"

        if self.board[x][y] != 'O':
            return "错误：该位置已有棋子"

        piece_num = self.players[player_id]
        self.board[x][y] = piece_num
        
        if self.check_win(x, y, piece_num):
            self.game_over = True
            self.winner = player_id
            return f"玩家{player_id}获胜！"

        if self.is_board_full():
            self.game_over = True
            self.winner = "平局"
            return f"棋盘已满，平局！"

        self.current_turn_index = (self.current_turn_index + 1) % len(self.players)
        
        next_player_id = list(self.players.keys())[self.current_turn_index]
        return f"落子成功，当前棋盘：\n||{self.get_board_str()}||\n现在轮到玩家|{next_player_id}|落子"

    def check_win(self, x, y, piece):
        board_height = len(self.board)
        board_width = len(self.board[0])
        directions = [(0, 1), (1, 0), (1, 1), (1, -1)]

        for dx, dy in directions:
            count = 1
            i, j = x + dx, y + dy
            while 0 <= i < board_height and 0 <= j < board_width and self.board[i][j] == piece:
                count += 1
                i += dx
                j += dy
            
            i, j = x - dx, y - dy
            while 0 <= i < board_height and 0 <= j < board_width and self.board[i][j] == piece:
                count += 1
                i -= dx
                j -= dy
            
            if count >= self.win_length:
                return True
        return False
    
    def is_board_full(self):
        for row in self.board:
            if 'O' in row:
                return False
        return True

    def get_board_str(self):
        return "\n".join([" ".join(row) for row in self.board])

class TicTacToeManager:
    def __init__(self):
        self.games = {}  # {game_id: TicTacToeGame实例}
        self.player_to_game = {}  # {player_id: game_id}
        self.creator_to_game = {}  # {creator_id: game_id}
        self.next_game_id = 1

    def parse_input(self, command):
        if not command.startswith("创建棋局"):
            return "错误：无效的命令"

        args = command[3:].strip().split()
        a, b, n, l = 3, 3, 3, 2

        has_x = False
        has_n = False
        for arg in args:
            if 'x' in arg:
                try:
                    a_str, b_str = arg.split('x')
                    a = int(a_str)
                    b = int(b_str)
                    has_x = True
                except ValueError:
                    return "错误：棋盘尺寸格式错误，请使用axb形式"
            elif arg.isdigit():
                num = int(arg)
                if not has_n:
                    n = num
                    has_n = True
                else:
                    l = num

        if n > a and n > b:
            return f"错误：获胜连子数{n}不能大于棋盘尺寸{a}x{b}"

        return a, b, n, l

    def create_game(self, creator_id, command):
        if creator_id in self.creator_to_game:
            return "错误：您已创建了一个棋局"

        result = self.parse_input(command)
        if isinstance(result, str):
            return result

        a, b, n, l = result
        game = TicTacToeGame(a, b, n, l)
        
        game_id = 1
        while game_id in self.games:
            game_id += 1
        
        if game_id >= self.next_game_id:
            self.next_game_id = game_id + 1

        self.games[game_id] = game
        self.creator_to_game[creator_id] = game_id

        game.add_player(creator_id)
        self.player_to_game[creator_id] = game_id

        return f"棋局#{game_id}创建成功，棋盘尺寸{a}x{b}，{n}连子获胜，最多{l}名玩家"

    def join_game(self, player_id, game_id):
        if player_id in self.player_to_game:
            return "错误：您已加入了一个棋局"
        if game_id not in self.games:
            return "错误：未找到该棋局"

        game = self.games[game_id]
        result = game.add_player(player_id)

        if "成功" in result:
            self.player_to_game[player_id] = game_id
            if len(game.players) == game.max_players:
                current_turn_player = list(game.players.keys())[game.current_turn_index]
                return f"{result}\n当前棋盘：\n||{game.get_board_str()}||\n玩家已满，现在轮到玩家|{current_turn_player}|落子"
            else:
                return f"{result}\n棋局#{game_id}等待更多玩家加入... ({len(game.players)}/{game.max_players})"
        else:
            return result

    def leave_game(self, player_id):
        if player_id not in self.player_to_game:
            return "错误：您未加入任何棋局"
        
        game_id = self.player_to_game[player_id]
        game = self.games.get(game_id)
        
        if not game:
            del self.player_to_game[player_id] 
            return "错误：未找到您所在的棋局"

        if game.remove_player(player_id):
            del self.player_to_game[player_id]
            return "成功离开棋局"
        return "错误：移除玩家失败"

    def delete_game(self, creator_id):
        if creator_id not in self.creator_to_game:
            return "错误：您未创建任何棋局"

        game_id = self.creator_to_game[creator_id]

        to_remove = [pid for pid, gid in self.player_to_game.items() if gid == game_id]
        for pid in to_remove:
            if pid in self.player_to_game:
                del self.player_to_game[pid]

        if game_id in self.games:
            del self.games[game_id]
        if creator_id in self.creator_to_game:
            del self.creator_to_game[creator_id]
            
        return "棋局已删除"

    def show_games(self):
        if not self.games:
            return "当前没有正在进行的棋局"
        lines = []
        for game_id in sorted(self.games.keys()):
            game = self.games[game_id]
            creator = "未知"
            for k, v in self.creator_to_game.items():
                if v == game_id:
                    creator = k
                    break
            current_players = len(game.players)
            total_players = game.max_players
            game_status = "进行中"
            if game.game_over:
                game_status = f"已结束 ({game.winner} 获胜)" if game.winner != "平局" else "已结束 (平局)"
            elif current_players < total_players:
                game_status = "等待玩家"
            lines.append(f"[{game_id}] 创建者:|{creator}| ({current_players}/{total_players}) 状态: {game_status}")
        return "\n".join(lines)

    def place_piece(self, player_id, position):
        if player_id not in self.player_to_game:
            return "错误：您未加入任何棋局"
        game_id = self.player_to_game[player_id]
        game = self.games.get(game_id)
        if not game:
            return "错误：该棋局已被删除"

        result = game.make_move(player_id, position)

        if game.game_over:
            creator_id_to_delete = None
            for creator_id, gid in self.creator_to_game.items():
                if gid == game_id:
                    creator_id_to_delete = creator_id
                    break
            if creator_id_to_delete:
                self.delete_game(creator_id_to_delete)
            else:
                to_remove = [pid for pid, gid in self.player_to_game.items() if gid == game_id]
                for pid in to_remove:
                    if pid in self.player_to_game:
                        del self.player_to_game[pid]
                
                if game_id in self.games:
                    del self.games[game_id]

        return result

if __name__ == "__main__":
    manager = TicTacToeManager()

    # 测试1: 基础双人游戏 (3x3, 3连子) - 平局
    print("\n" + "=" * 40)
    print("测试1: 基础双人游戏 (3x3, 3连子) - 平局")
    print(manager.create_game("user1", "创建棋局")) # 创建棋局#1
    print(manager.join_game("user2", 1))

    moves_for_draw = [
        ("user1", "1,1"), ("user2", "2,2"),
        ("user1", "1,2"), ("user2", "1,3"),
        ("user1", "3,1"), ("user2", "2,1"),
        ("user1", "2,3"), ("user2", "3,2"),
        ("user1", "3,3")
    ]
    for player_id, pos in moves_for_draw:
        print(f"-> 玩家 {player_id} 落子: {pos}")
        print(manager.place_piece(player_id, pos))
    
    print("\n平局后查看棋局状态")
    print(manager.show_games()) # 棋局 #1 应该已被删除


    # 测试2: 可配置游戏 (5x5, 4连子, 3人) - 获胜
    print("\n" + "=" * 40)
    print("测试2: 可配置游戏 (5x5, 4连子, 3人) - 获胜")
    print(manager.create_game("userA", "创建棋局 5x5 4 3")) # 创建棋局#2
    print(manager.join_game("userB", 1))
    print(manager.join_game("userC", 1))

    moves_for_win = [
        ("userA", "1,1"), ("userB", "2,2"), ("userC", "3,3"),
        ("userA", "2,1"), ("userB", "2,3"), ("userC", "3,4"),
        ("userA", "3,1"), ("userB", "2,4"), ("userC", "3,5"),
        ("userA", "4,1")
    ]
    for player_id, pos in moves_for_win:
        print(f"-> 玩家 {player_id} 落子: {pos}")
        print(manager.place_piece(player_id, pos))
    
    print("\n获胜后查看棋局状态")
    print(manager.show_games()) # 棋局 #2 应该已被删除


    # 测试3: ID 回收功能验证 (First-Fit 策略)
    print("\n" + "=" * 40)
    print("测试3: ID 回收功能验证 (First-Fit 策略)")
    print("3.1 创建新棋局并删除，观察ID重用")
    print(f"当前 next_game_id: {manager.next_game_id}")
    print(manager.create_game("creator_rec1", "创建棋局"))
    print(manager.create_game("creator_rec2", "创建棋局"))
    print(manager.show_games())
    print(f"创建后 next_game_id: {manager.next_game_id}")

    print("\n3.2 删除棋局，腾出ID")
    print(manager.delete_game("creator_rec1"))
    print(manager.delete_game("creator_rec2"))
    print(manager.show_games())
    print(f"删除后 next_game_id: {manager.next_game_id}")

    print("\n3.3 再次创建新棋局，验证ID是否被重用")
    print(manager.create_game("creator_rec3", "创建棋局"))
    print(manager.create_game("creator_rec4", "创建棋局"))
    print(manager.create_game("creator_rec5", "创建棋局"))
    print(manager.show_games())
    print(f"重用后 next_game_id: {manager.next_game_id}")


    # 测试4: 玩家管理和异常处理 (用新管理器实例)
    print("\n" + "=" * 40)
    print("测试4: 玩家管理和异常处理 (新实例)")
    print("4.1 创建一个新棋局")
    manager2 = TicTacToeManager()
    print(manager2.create_game("creator_X", "创建棋局 4x4 3 4")) # 棋局#1
    print(manager2.join_game("player_Y", 1))
    print(manager2.join_game("player_Z", 1))
    print(manager2.show_games())

    print("\n4.2 玩家离开游戏并重用ID")
    print(manager2.join_game("new_player", 1))
    print(manager2.leave_game("player_Z"))
    print(manager2.show_games())
    print(manager2.join_game("player_A", 1)) # 再次加入，棋局满员
    
    print("\n4.3 验证已删除棋局的玩家无法落子/离开")
    print(manager2.delete_game("creator_X")) # 删除棋局 #1
    print(manager2.leave_game("player_A"))
    print(manager2.place_piece("player_Y", "3,3"))
    
    print("\n全面功能测试结束")
