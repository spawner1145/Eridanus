from PIL import Image
from .initialize import initialize_yaml_must_require
from .util import *
import ast

class basicimgset:
    def __init__(self, params):
        default_keys_values,must_required_keys=initialize_yaml_must_require(params)

        self.must_required_keys = must_required_keys or []  # 必须的键，如果没有提供就默认是空列表
        self.default_keys_values = default_keys_values or {}  # 默认值字典
        # 检测缺少的必需键
        missing_keys = [key for key in self.must_required_keys if key not in params]
        if missing_keys:
            raise ValueError(f"初始化中缺少必需的键: {missing_keys}，请检查传入的数据是否有误")
        # 将字典中的键值转化为类的属性
        for key, value in params.items():
            setattr(self, key, value)
        # 设置默认值
        for key, value in self.default_keys_values.items():
            if not hasattr(self, key):  # 如果属性不存在，则设置默认值
                setattr(self, key, value)
        if self.img_name_save:self.img_path_save=f'{self.img_path_save}/{self.img_name_save}'
        self.img_height_limit = self.img_height - self.padding_up_common * 2
        #self.img_height_limit = self.img_height
        #是否获取其绝对路径
        if self.is_abs_path_convert is True:
            for key, value in vars(self).items():
                setattr(self, key, get_abs_path(value))
        #检测其图片宽度是否为列表
        self.columns = 0
        if isinstance(self.img_width, str):
            if self.img_width.startswith('['):
                self.img_width = ast.literal_eval(self.img_width)
            else:
                self.img_width = [self.img_width]
        elif isinstance(self.img_width, int):
            self.img_width = [self.img_width]
        elif isinstance(self.img_width, list):
            pass


    async def creatbasicimgnobackdrop(self,img_list):
        """创建一个同名空白画布并返回。"""
        # 创建一个指定大小和颜色的画布
        width = self.padding_left_common
        for i in range(self.columns):
            if len(self.img_width) - 1 >= i:
                width += self.img_width[i] - self.padding_left_common
            else:
                width += self.img_width[len(self.img_width) - 1] - self.padding_left_common
        #width = len(img_list) * (self.img_width - self.padding_left_common) + self.padding_left_common
        canvas = Image.new("RGBA", (width, self.img_height), (0, 0, 0, 0))
        #canvas = Image.new("RGBA", (self.img_width, self.img_height), (255, 0, 0, 255))
        return canvas


    async def combine_layer_basic(self,basic_img,img_list):
        x_offest=0
        if len(img_list) == 1:
            layer_img_canvas=img_list[0]
            if layer_img_canvas.mode not in ("RGBA"): layer_img_canvas = layer_img_canvas.convert("RGBA")
            width, height = layer_img_canvas.size
            if height > self.img_height:
                height = self.img_height
                layer_img_canvas = layer_img_canvas.crop((0, 0, width, height + self.stroke_img_width / 2))
                basic_img.paste(layer_img_canvas, (0, -int(self.padding_up_common ) ,width,height - int(self.padding_up_common - self.stroke_img_width / 2)), mask=layer_img_canvas)
                basic_img = basic_img.crop((0, 0, self.img_width[0], height))
            else:
                basic_img.paste(layer_img_canvas, (0, -int(self.padding_up_common), width, height - int(self.padding_up_common)),mask=layer_img_canvas)
                basic_img = basic_img.crop((0, 0, width, height - int(self.padding_up_common) ))
        else:
            height_max = 0
            for layer_img_canvas in img_list:
                width, height = layer_img_canvas.size
                if height > height_max: height_max = height
                basic_img.paste(layer_img_canvas,(x_offest, -int(self.padding_up_common), width + x_offest, height - int(self.padding_up_common)),mask=layer_img_canvas)
                x_offest += (width - self.padding_left_common)
            basic_img = basic_img.crop((0, 0, basic_img.width, height_max - int(self.padding_up_common)))


        #basic_img=basic_img.crop((0, 0, self.img_width, height))

        return basic_img

