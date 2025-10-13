class ModelFallbackManager:
    """模型降级管理器"""

    def __init__(self, models: list[str]):
        if not models:
            raise ValueError("模型列表不能为空")
        self.models = models
        self.current_index = 0

    def get_current_model(self) -> str:
        return self.models[self.current_index]

    def fallback(self) -> bool:
        if self.current_index < len(self.models) - 1:
            self.current_index += 1
            return True
        return False

    def reset(self):
        self.current_index = 0