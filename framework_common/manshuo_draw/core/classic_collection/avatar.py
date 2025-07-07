from PIL import Image, ImageDraw, ImageFont, ImageOps,ImageFilter
from .initialize import initialize_yaml_must_require
from framework_common.manshuo_draw.core.util import *
import os
import base64
from io import BytesIO

class AvatarModule:
    def __init__(self,layer_img_set,params):
        for key, value in vars(layer_img_set).items():#继承父类属性，主要是图片基本设置类
            setattr(self, key, value)

        default_keys_values, must_required_keys = initialize_yaml_must_require(params)
        self.must_required_keys = must_required_keys or []  # 必须的键，如果没有提供就默认是空列表
        self.default_keys_values = default_keys_values or {}  # 默认值字典
        # 检测缺少的必需键
        missing_keys = [key for key in self.must_required_keys if key not in params]
        if missing_keys:
            raise ValueError(f"初始化中缺少必需的键: {missing_keys}，请检查传入的数据是否有误")
        # 设置默认值
        for key, value in self.default_keys_values.items():
            setattr(self, key, value)
        # 将字典中的键值转化为类的属性
        for key, value in params.items():
            setattr(self, key, value)
        #是否获取其绝对路径
        if self.is_abs_path_convert is True:
            for key, value in vars(self).items():
                setattr(self, key, get_abs_path(value))

        #接下来是对图片进行处理，将其全部转化为pillow的img对象，方便后续处理

        self.processed_img = process_img_download(self.img,self.is_abs_path_convert)
        self.processed_img = crop_to_square(self.processed_img)



    def common(self):
        icon_backdrop_check(self.__dict__)  # 进行背景模块的初始化
        init(self.__dict__)#对该模块进行初始化
        #对每个图片进行单独处理
        for img in self.processed_img:
            if self.img_height_limit_module <= 0: break
            #创建背景同时进行背景处理
            if self.judge_flag == 'list':
                avatar_canvas = Image.new("RGBA", (self.new_width, self.avatar_size+self.padding_up_bottom*2), (0, 0, 0, 0))
                avatar_canvas = icon_process(self.__dict__, avatar_canvas, (self.new_width - self.padding, avatar_canvas.height - self.padding_up_bottom))
                avatar_canvas = backdrop_process(self.__dict__, avatar_canvas,(avatar_canvas.width, avatar_canvas.height))
            elif self.judge_flag == 'common' :
                avatar_canvas = Image.new("RGBA", (self.new_width, self.avatar_size + self.padding_up_bottom * 2),(0, 0, 0, 0))
            else:
                avatar_canvas = Image.new("RGBA", (self.new_width, self.avatar_size + self.padding_up_bottom * 2),eval(self.avatar_backdrop_color))
            img = per_img_limit_deal(self.__dict__, img,type='avatar')
            avatar_canvas = img_process(self.__dict__, avatar_canvas, img, self.padding_with , self.padding_up_bottom,self.avatar_upshift,'avatar')
            # 进行文字绘制
            img = basic_img_draw_text(avatar_canvas, self.content[self.number_count], self.__dict__,
                                      box=(self.avatar_size*1.1 + self.padding_with + self.padding, self.padding_up_font + self.padding_up_bottom),
                                      limit_box=(avatar_canvas.width, avatar_canvas.height), is_shadow=self.is_shadow_font)['canvas']
            #加入label绘制
            img=label_process(self.__dict__,img,self.number_count,self.new_width)
            #对每个图像进行处理
            self.pure_backdrop = img_process(self.__dict__,self.pure_backdrop, img, self.x_offset, self.current_y, self.upshift)
            per_img_deal(self.__dict__, img)  # 处理每个图片的位置关系
        final_img_deal(self.__dict__)  # 处理最后的位置关系
        #兼容以前的图像模式，实现背景处理
        if self.judge_flag == 'common' :
            self.pure_backdrop = icon_process(self.__dict__, self.pure_backdrop,(self.img_width - self.padding , self.current_y - self.padding_up_bottom))
            self.pure_backdrop = backdrop_process(self.__dict__,self.pure_backdrop,(self.img_width, self.current_y))
        return {'canvas': self.pure_backdrop, 'canvas_bottom': self.current_y - self.upshift_extra,'upshift':self.upshift + self.upshift_extra,'downshift':self.downshift}




