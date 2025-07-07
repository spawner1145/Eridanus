from PIL import Image, ImageDraw, ImageFont, ImageOps,ImageFilter
from .initialize import initialize_yaml_must_require
from framework_common.manshuo_draw.core.util import *

class ImageModule:
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
        #判断图片的排版方式
        if self.number_per_row == 'default' :
            if len(self.processed_img) == 1:
                self.number_per_row=1
                self.is_crop = False
            elif len(self.processed_img) in [2,4] : self.number_per_row=2
            else: self.number_per_row=3

        #接下来处理是否裁剪部分
        if self.is_crop == 'default':
            if self.number_per_row==1: self.is_crop = False
            else: self.is_crop = True
        if self.is_crop is True:self.processed_img=crop_to_square(self.processed_img)


    def common(self):
        init(self.__dict__)#对该模块进行初始化
        #对每个图片进行单独处理
        for img in self.processed_img:
            if self.img_height_limit_module <= 0:break
            img = per_img_limit_deal(self.__dict__,img)
            #加入label绘制
            img=label_process(self.__dict__,img,self.number_count,self.new_width)
            #对每个图像进行处理
            self.pure_backdrop = img_process(self.__dict__,self.pure_backdrop, img, self.x_offset, self.current_y, self.upshift)
            per_img_deal(self.__dict__,img)  # 处理每个图片的位置关系
        final_img_deal(self.__dict__)  # 处理最后的位置关系
        return {'canvas': self.pure_backdrop, 'canvas_bottom': self.current_y ,'upshift':self.upshift,'downshift':self.downshift}

    def common_with_des(self):
        init(self.__dict__)#对该模块进行初始化
        # 对每个图片进行单独处理
        for img in self.processed_img:
            if self.img_height_limit_module <= 0: break
            img = per_img_limit_deal(self.__dict__,img)
            img_des_canvas = Image.new("RGBA", (img.width, img.height + self.max_des_length), eval(self.description_color))
            img_des_canvas.paste(img, (0, 0))
            img_des_canvas_info=basic_img_draw_text(img_des_canvas,self.content[self.number_count],self.__dict__,
                                                                     box=(self.padding , img.height + self.padding),
                                                                     limit_box=(self.new_width, self.max_des_length + img.height))
            des_length = self.max_des_length + img.height
            if int(img_des_canvas_info['canvas_bottom'] + self.padding_up) < des_length:
                des_length=int(img_des_canvas_info['canvas_bottom'] + self.padding_up)
            img=img_des_canvas_info['canvas'].crop((0, 0, img.width, des_length))

            #加入label绘制
            img=label_process(self.__dict__,img,self.number_count,self.new_width)
            # 对每个图像进行处理
            self.pure_backdrop = img_process(self.__dict__,self.pure_backdrop, img, self.x_offset, self.current_y, self.upshift)
            per_img_deal(self.__dict__, img)  # 处理每个图片的位置关系
        final_img_deal(self.__dict__)  # 处理最后的位置关系
        return {'canvas': self.pure_backdrop, 'canvas_bottom': self.current_y, 'upshift': self.upshift, 'downshift': self.downshift}


    def common_with_des_right(self):
        init(self.__dict__)#对该模块进行初始化
        # 对每个图片进行单独处理
        for img in self.processed_img:
            if self.img_height_limit_module <= 0: break
            if img.height/img.width < 9/16:magnification_img=2
            else:magnification_img=2.5
            img = per_img_limit_deal(self.__dict__,img,magnification_img)
            img_des_canvas = Image.new("RGBA", (self.new_width, img.height),eval(self.description_color))
            img_des_canvas.paste(img, (0, 0))
            #进行文字绘制
            img = basic_img_draw_text(img_des_canvas, self.content[self.number_count], self.__dict__,
                                                      box=(int(self.new_width / magnification_img) + self.padding,  self.padding),
                                                      limit_box=(self.new_width, img.height))['canvas']

            # 加入label绘制
            img = label_process(self.__dict__,img, self.number_count, int(self.new_width / magnification_img))
            # 对每个图像进行处理
            self.pure_backdrop = img_process(self.__dict__, self.pure_backdrop, img, self.x_offset, self.current_y, self.upshift)
            per_img_deal(self.__dict__, img)  # 处理每个图片的位置关系
        final_img_deal(self.__dict__)  # 处理最后的位置关系


        return {'canvas': self.pure_backdrop, 'canvas_bottom': self.current_y, 'upshift': self.upshift, 'downshift': self.downshift}



