from PIL import Image
from .initialize import initialize_yaml_must_require
from .util import *
from datetime import datetime
import calendar
import weakref
import time

class GamesModule:
    def __init__(self,layer_img_set,params):
        for key, value in vars(layer_img_set).items():#继承父类属性，主要是图片基本设置类
            setattr(self, key, value)
        default_keys_values, must_required_keys = initialize_yaml_must_require(params)
        self.must_required_keys = must_required_keys or []  # 必须的键，如果没有提供就默认是空列表
        self.default_keys_values = default_keys_values or {}  # 默认值字典
        self.params=params
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




    async def LuRecordMake(self):
        await init(self.__dict__)#对该模块进行初始化
        #构建图像阵列
        self.processed_img,self.content=[],[]
        first_day_of_week = datetime(datetime.now().year, datetime.now().month, 1).weekday() + 1
        if first_day_of_week == 7: first_day_of_week=0
        _, days_total = calendar.monthrange(datetime.now().year, datetime.now().month)
        background_make=(await process_img_download(self.background,self.is_abs_path_convert))[0]
        background_make_L = Image.new("RGBA", background_make.size, (255,255,255,255))
        background_make_L.putalpha(background_make.convert('L'))
        for i in range(days_total):
            if f'{i}' in self.content_list :
                if self.content_list[f'{i}']['type'] == 'lu':self.processed_img.append(background_make)
                elif self.content_list[f'{i}']['type'] == 'nolu': self.processed_img.append(background_make)
            else:self.processed_img.append(background_make_L)
        weeky=['周日','周一','周二','周三','周四','周五','周六','周日']
        x_offset_week=self.padding
        for i in range(int(self.number_per_row)):
            week_img_canves = Image.new("RGBA", background_make.size, (255, 255, 255, 255)).resize(
                (self.new_width, int(self.new_width * background_make.height / background_make.width)))
            img_week = (await basic_img_draw_text(week_img_canves, f"[title]{weeky[i]}[/title]", self.__dict__,box=(int(self.padding*1.2), week_img_canves.height//2 - self.font_title_size//2 - 3), ))['canvas']
            self.pure_backdrop = await img_process(self.__dict__, self.pure_backdrop, img_week, x_offset_week, self.current_y, self.upshift)
            x_offset_week += self.new_width + self.padding_with
        self.current_y += img_week.height + self.padding_with
        #对每个图片进行单独处理
        week_list=[]
        for i in range(first_day_of_week):
            week_list.append(Image.new("RGBA", background_make.size, (0, 0, 0, 0)))
        self.processed_img=add_append_img(week_list,self.processed_img)

        for img in self.processed_img:
            if self.img_height_limit_module <= 0:break
            img = await per_img_limit_deal(self.__dict__,img)#处理每个图片,您的每张图片绘制自定义区域

            if f'{self.number_count - first_day_of_week}' in self.content_list:
                if self.content_list[f'{self.number_count - first_day_of_week}']['type'] == 'lu' and int(
                        self.content_list[f'{self.number_count - first_day_of_week}']['times']) not in {0, 1}:
                    img = (await basic_img_draw_text(img, f"[lu]×{self.content_list[f'{self.number_count - first_day_of_week}']['times']}[/lu]", self.__dict__,
                                              box=(self.padding, img.height - self.font_lu_size - self.padding), ))['canvas']
                elif self.content_list[f'{self.number_count - first_day_of_week}']['type'] == 'nolu':
                    img = (await basic_img_draw_text(img, f"[date]戒🦌[/date]", self.__dict__,
                                              box=(self.padding, img.height - self.font_date_size - self.padding), ))[
                        'canvas']
            else:
                if self.number_count - first_day_of_week + 1 > 0:
                    img = (await basic_img_draw_text(img, f"[date]{self.number_count - first_day_of_week + 1}[/date]", self.__dict__,
                                          box=(self.padding * 1.6, img.height//2 - self.font_date_size//2 - 3), ))['canvas']

            img=await label_process(self.__dict__,img,self.number_count,self.new_width)#加入label绘制
            self.pure_backdrop = await img_process(self.__dict__,self.pure_backdrop, img, self.x_offset, self.current_y, self.upshift)#对每个图像进行处理
            await per_img_deal(self.__dict__,img)  # 处理每个图片的位置关系
        await final_img_deal(self.__dict__)  # 处理最后的位置关系
        return {'canvas': self.pure_backdrop, 'canvas_bottom': self.current_y, 'upshift': self.upshift, 'downshift': self.downshift,
                'json_img_left_module':self.json_img_left_module,'without_draw':self.without_draw_and_jump}



