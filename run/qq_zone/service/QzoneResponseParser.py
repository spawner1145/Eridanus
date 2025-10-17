import json
import re


class QzoneResponseParser:
    @staticmethod
    def parse_upload_response(html_response: str) -> dict:
        """
        解析 QQ 空间上传图片的响应
        :param html_response: HTML 格式的响应文本
        :return: 解析后的数据字典
        """
        # 方法1: 使用正则提取 JSON
        pattern = r'frameElement\.callback\((.*?)\);'
        match = re.search(pattern, html_response, re.DOTALL)

        if match:
            json_str = match.group(1)
            data = json.loads(json_str)
            return data

        return {}

    @staticmethod
    def extract_richval(upload_data: dict) -> str:
        """
        从上传响应中提取 richval 参数
        格式: ,albumid,lloc,sloc,type,height,width,,height,width
        """
        data = upload_data.get('data', {})

        albumid = data.get('albumid', '')
        lloc = data.get('lloc', '')
        sloc = data.get('sloc', '')
        img_type = data.get('type', '')
        height = data.get('height', '')
        width = data.get('width', '')

        # 构造 richval
        richval = f",{albumid},{lloc},{sloc},{img_type},{height},{width},,{height},{width}"

        return richval

    @staticmethod
    def extract_pic_bo(upload_data: dict) -> str:
        """
        从上传响应中提取 pic_bo 参数
        从 URL 中的 bo= 参数提取
        """
        data = upload_data.get('data', {})
        url = data.get('url', '')

        # 从 URL 中提取 bo 参数
        # 例如: bo=AAQABgAAAAAWECI!
        pattern = r'bo=([^&]+)'
        match = re.search(pattern, url)

        if match:
            bo_value = match.group(1)
            # pic_bo 格式是两个相同的值，空格分隔
            return f"{bo_value} {bo_value}"

        return ""