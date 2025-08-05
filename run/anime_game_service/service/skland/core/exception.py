

class RequestException(Exception):
    """请求错误"""


class UnauthorizedException(Exception):
    """登录授权错误"""


class LoginException(Exception):
    """登录错误"""
