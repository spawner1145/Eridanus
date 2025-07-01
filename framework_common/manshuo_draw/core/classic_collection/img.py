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
        self.init()#对该模块进行初始化
        #对每个图片进行单独处理
        for img in self.processed_img:
            img = img.resize((self.new_width, int(self.new_width * img.height / img.width)))
            #加入label绘制
            img=self.label_process(img,self.number_count,self.new_width)
            #对每个图像进行处理
            self.pure_backdrop = img_process(self.__dict__,self.pure_backdrop, img, self.x_offset, self.current_y, self.upshift)
            self.per_img_deal(img)  # 处理每个图片的位置关系
        self.final_img_deal()  # 处理最后的位置关系
        return {'canvas': self.pure_backdrop, 'canvas_bottom': self.current_y ,'upshift':self.upshift,'downshift':self.downshift}

    def common_with_des(self):
        self.init()#对该模块进行初始化
        # 对每个图片进行单独处理
        for img in self.processed_img:
            img = img.resize((self.new_width, int(self.new_width * img.height / img.width)))
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
            img=self.label_process(img,self.number_count,self.new_width)
            # 对每个图像进行处理
            self.pure_backdrop = img_process(self.__dict__,self.pure_backdrop, img, self.x_offset, self.current_y, self.upshift)
            self.per_img_deal(img)  # 处理每个图片的位置关系
        self.final_img_deal()  # 处理最后的位置关系
        return {'canvas': self.pure_backdrop, 'canvas_bottom': self.current_y, 'upshift': self.upshift, 'downshift': self.downshift}


    def common_with_des_right(self):
        self.init()#对该模块进行初始化
        # 对每个图片进行单独处理
        for img in self.processed_img:
            if img.height/img.width < 9/16:img_width,img_height=int(self.new_width / 2),int((self.new_width / 2.5) * img.height / img.width)
            else:img_width,img_height=int(self.new_width / 2.5),int((self.new_width / 2.5) * img.height / img.width)
            img = img.resize((img_width, img_height))
            img_des_canvas = Image.new("RGBA", (self.new_width, img_height),eval(self.description_color))
            img_des_canvas.paste(img, (0, 0))
            #进行文字绘制
            img = basic_img_draw_text(img_des_canvas, self.content[self.number_count], self.__dict__,
                                                      box=(img_width + self.padding,  self.padding),
                                                      limit_box=(self.new_width, img_height))['canvas']

            # 加入label绘制
            img = self.label_process(img, self.number_count, img_width)
            # 对每个图像进行处理
            self.pure_backdrop = img_process(self.__dict__, self.pure_backdrop, img, self.x_offset, self.current_y, self.upshift)
            self.per_img_deal(img)#处理每个图片的位置关系
        self.final_img_deal() #处理最后的位置关系


        return {'canvas': self.pure_backdrop, 'canvas_bottom': self.current_y, 'upshift': self.upshift, 'downshift': self.downshift}





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
        self.per_number_count, self.number_count, self.upshift, self.downshift, self.current_y, self.x_offset, self.max_height = 0, 0, 0, 0, 0, self.padding, 0
        # 若有描边，则将初始粘贴位置增加一个描边宽度
        if self.is_stroke_front and self.is_stroke_img: self.current_y += self.stroke_img_width / 2
        if self.is_shadow_front and self.is_shadow_img: self.upshift += self.shadow_offset_img * 2

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