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
        pure_backdrop = Image.new("RGBA", (self.img_width, self.img_height), (0, 0, 0, 0))
        number_count,upshift,downshift,current_y,x_offset = 0,0,0,self.padding_up_bottom,self.padding
        #若有描边，则将初始粘贴位置增加一个描边宽度
        if self.is_stroke_front and self.is_stroke_avatar:current_y += self.stroke_avatar_width / 2
        if self.is_shadow_front and self.is_shadow_avatar:upshift +=self.shadow_offset_avatar*2
        new_width=(((self.img_width - self.padding*2 ) - (self.number_per_row - 1) * self.padding_with) // self.number_per_row)
        self.icon_backdrop_check()


        for img in self.processed_img:
            img.thumbnail((self.avatar_size, self.avatar_size))
            # 对每个图像进行处理
            pure_backdrop = img_process(self.__dict__,pure_backdrop, img, x_offset, current_y, upshift,'avatar')
            # 绘制名字和时间等其他信息
            draw_content = f"{self.content[number_count]}"
            if self.is_name:
                pure_backdrop=basic_img_draw_text(pure_backdrop,draw_content,self.__dict__,
                                                                     box=(x_offset + self.avatar_size*1.1 + self.padding_with, current_y + self.padding_up_font),
                                                                     limit_box=(x_offset + new_width  , current_y  + self.avatar_size ),is_shadow=self.is_shadow_font)['canvas']
            x_offset += new_width + self.padding_with
            number_count += 1
            if number_count == self.number_per_row:
                number_count,x_offset = 0,self.padding
                current_y += img.height + self.padding_with
        if number_count != 0:
            current_y += new_width * img.height / img.width
        else:
            current_y -= self.padding_with

        pure_backdrop = icon_process(self.__dict__, pure_backdrop,(self.img_width - self.padding , current_y ))
        pure_backdrop = backdrop_process(self.__dict__,pure_backdrop,(self.img_width, current_y + self.padding_up_bottom))
        upshift+=self.upshift_extra
        return {'canvas': pure_backdrop, 'canvas_bottom': current_y + self.padding_up_bottom - self.upshift_extra ,'upshift':upshift,'downshift':0}

    def list(self):
        self.init()#对该模块进行初始化
        self.icon_backdrop_check()#进行背景模块的初始化
        #对每个图片进行单独处理
        for img in self.processed_img:
            #创建背景同时进行背景处理
            if self.background  or self.right_icon:

                avatar_canvas = Image.new("RGBA", (self.new_width, self.avatar_size+self.padding_up_bottom*2), (0, 0, 0, 0))
                avatar_canvas = icon_process(self.__dict__, avatar_canvas, (self.new_width - self.padding, avatar_canvas.height - self.padding_up_bottom))
                avatar_canvas = backdrop_process(self.__dict__, avatar_canvas,(avatar_canvas.width, avatar_canvas.height))
            else:
                avatar_canvas = Image.new("RGBA", (self.new_width, self.avatar_size + self.padding_up_bottom * 2),eval(self.avatar_backdrop_color))
            img = img.resize((self.avatar_size, self.avatar_size))
            avatar_canvas = img_process(self.__dict__, avatar_canvas, img, self.padding_with , self.padding_up_bottom,self.avatar_upshift,'avatar')
            # 进行文字绘制
            img = basic_img_draw_text(avatar_canvas, self.content[self.number_count], self.__dict__,
                                      box=(self.avatar_size*1.1 + self.padding_with + self.padding, self.padding_up_font + self.padding_up_bottom),
                                      limit_box=(avatar_canvas.width, avatar_canvas.height), is_shadow=self.is_shadow_font)['canvas']
            #加入label绘制
            img=self.label_process(img,self.number_count,self.new_width)
            #对每个图像进行处理
            self.pure_backdrop = img_process(self.__dict__,self.pure_backdrop, img, self.x_offset, self.current_y, self.upshift)
            self.per_img_deal(img)  # 处理每个图片的位置关系
        self.final_img_deal()  # 处理最后的位置关系
        return {'canvas': self.pure_backdrop, 'canvas_bottom': self.current_y ,'upshift':self.upshift,'downshift':self.downshift}


    #头像右侧标签以及背景处理
    def icon_backdrop_check(self):
        if self.type_software is None and self.background is None and self.right_icon is None : return
        for content_check in self.software_list:
            if content_check['right_icon'] and self.type_software == content_check['type'] :
                if self.right_icon is None:
                    self.right_icon = content_check['right_icon']
                if content_check['background'] and self.background is None:
                    self.background = content_check['background']
        if self.background:
            self.font_name_color,self.font_time_color = '(255,255,255)', '(255,255,255)'
            self.is_shadow_font = True


    #右上角标签处理
    def label_process(self,img,number_count,new_width):
        font_label = ImageFont.truetype(self.font_label, self.font_label_size)
        label_width, label_height,upshift = self.padding * 4, self.padding + self.font_label_size,0
        if number_count  >= len(self.label) or self.label[number_count] == '':
            return img
        label_content = self.label[number_count]
        #计算标签的实际长度
        for per_label_font in label_content:
            label_width += font_label.getbbox(per_label_font)[2] - font_label.getbbox(per_label_font)[0]
        if label_width > new_width: label_width = new_width
        label_canvas = Image.new("RGBA", (int(label_width), int(label_height)), eval(self.label_color))
        #调用方法绘制文字并判断是否需要描边和圆角
        #print(label_width,label_height)
        label_canvas = basic_img_draw_text(label_canvas, f'[label] {label_content} [/label]', self.__dict__,
                                                                        box=(self.padding*1.3, self.padding*0.8),
                                                                        limit_box=(label_width,label_height),ellipsis=False)['canvas']
        img = img_process(self.__dict__, img, label_canvas, int(new_width - label_width), 0, upshift,'label')
        return img

    #以下函数为模块内关系处理函数，请不要乱动
    def init(self):#对模块的参数进行初始化
        self.pure_backdrop = Image.new("RGBA", (self.img_width, self.img_height), (0, 0, 0, 0))
        self.new_width = (((self.img_width - self.padding * 2) - (self.number_per_row - 1) * self.padding_with) // self.number_per_row)
        self.per_number_count, self.number_count, self.upshift, self.downshift, self.current_y, self.x_offset, self.max_height,self.avatar_upshift = 0, 0, 0, 0, 0, self.padding, 0 , 0
        # 若有描边，则将初始粘贴位置增加一个描边宽度
        if self.is_stroke_front and self.is_stroke_img: self.current_y += self.stroke_img_width / 2
        if self.is_shadow_front and self.is_shadow_img: self.upshift += self.shadow_offset_img * 2
        if self.is_shadow_front and self.is_shadow_avatar:self.avatar_upshift +=self.shadow_offset_avatar*2

    def per_img_deal(self,img):#绘制完该模块后处理下一个模块的关系
        if img.height > self.max_height: self.max_height = img.height
        self.x_offset += self.new_width + self.padding_with
        self.per_number_count += 1
        self.number_count += 1
        if self.per_number_count == self.number_per_row:
            self.current_y += self.max_height + self.padding_with
            self.per_number_count, self.x_offset, self.max_height = 0, self.padding, 0

    def final_img_deal(self):#判断是否需要增减
        if self.per_number_count != 0:
            self.current_y += self.max_height
        else:
            self.current_y -= self.padding_with