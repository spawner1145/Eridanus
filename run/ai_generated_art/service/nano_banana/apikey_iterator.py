class RoundRobinSelector:
    def __init__(self, items):
        self.items = items if isinstance(items, list) else [items]
        self.index = 0

    def get_next(self):
        if not self.items:
            raise ValueError("轮询列表为空")
        item = self.items[self.index]
        self.index = (self.index + 1) % len(self.items)
        return item
