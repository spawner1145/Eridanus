from PIL import Image, ImageDraw, ImageFont, ImageOps,ImageFilter
from .initialize import initialize_yaml_must_require
from framework_common.manshuo_draw.core.util import *

class TextModule:
    def __init__(self,layer_img_set,params):
        for key, value in vars(layer_img_set).items():#继承父类属性，主要是图片基本设置类
            setattr(self, key, value)

        default_keys_values, must_required_keys = initialize_yaml_must_require(params)
        self.must_required_keys = must_required_keys or []  # 必须的键，如果没有提供就默认是空列表
        self.default_keys_values = default_keys_values or {}  # 默认值字典
        self.params = params
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

    async def common(self):
        await init(self.__dict__)  # 对该模块进行初始化

        img_des_canvas_info = await basic_img_draw_text(self.pure_backdrop, self.content[0], self.__dict__,
                                                  box=(self.padding, 0),
                                                  limit_box=(self.pure_backdrop.width, self.img_height_limit_module))
        canvas_bottom=int(img_des_canvas_info['canvas_bottom'] )
        await final_img_deal(self.__dict__,'text')  # 处理最后的位置关系
        if self.json_img_left_module_flag:canvas_bottom=self.img_height_limit_module
        return {'canvas':self.pure_backdrop,'canvas_bottom':canvas_bottom,'upshift':0,'downshift':0,
                'json_img_left_module':self.json_img_left_module,'without_draw':self.without_draw_and_jump}



