from PIL import Image
from .initialize import initialize_yaml_must_require
from .util import *
import math

class MathModule:
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


    async def bar_chart(self):#条形腿
        #对每个图片进行单独处理
        await self.data_deal()
        await init(self.__dict__)#对该模块进行初始化
        for percent in self.content:
            img = Image.new("RGBA", (self.new_width,int(self.chart_height)), eval(str(self.backdrop_color)))
            img = await per_img_limit_deal(self.__dict__,img, type='math')#处理每个图片,您的每张图片绘制自定义区域
            if self.json_img_left_module_flag: break  # 修改模块的跳出条件，使得模块能够完整绘出
            chart_img = Image.new("RGBA", (self.new_width,int(self.chart_height)), eval(str(self.chart_color))).crop((0, 0, int(img.width * percent), img.height))
            img = await img_process(self.__dict__, img, chart_img, 0,0, 0, 'math')  # 对每个图像进行处理
            img=await label_process(self.__dict__,img,self.number_count,self.new_width)#加入label绘制
            self.pure_backdrop = await img_process(self.__dict__,self.pure_backdrop, img, self.x_offset, self.current_y, self.upshift)#对每个图像进行处理
            await per_img_deal(self.__dict__,img)  # 处理每个图片的位置关系
        await final_img_deal(self.__dict__, type='math')  # 处理最后的位置关系
        return {'canvas': self.pure_backdrop, 'canvas_bottom': self.current_y ,'upshift':self.upshift,'downshift':self.downshift,
                'json_img_left_module':self.json_img_left_module,'without_draw':self.without_draw_and_jump}

    async def bar_chart_vertical(self):#竖状条形腿
        #对每个图片进行单独处理
        await self.data_deal(type='bar_chart_vertical')
        await init(self.__dict__)#对该模块进行初始化
        for img_num_list in self.content:
            img = Image.new("RGBA", (self.new_width,int(self.chart_height + 2*self.padding_up)), eval(str(self.backdrop_color)))
            img = await per_img_limit_deal(self.__dict__,img, type='math')#处理每个图片,您的每张图片绘制自定义区域
            if self.json_img_left_module_flag: break  # 修改模块的跳出条件，使得模块能够完整绘出
            #在一个模块内依次粘贴绘制好的条形图
            x_offset_list,x_count_list=self.padding,0
            for percent in img_num_list:
                crop_height = int(self.chart_height * (1-percent))
                chart_img = Image.new("RGBA", (int(self.chart_width),int(self.chart_height)), eval(str(self.chart_color))).crop((0, crop_height, int(self.chart_width), int(self.chart_height)))
                img = await img_process(self.__dict__, img, chart_img, x_offset_list,crop_height + self.padding_up, 0, 'math')  # 对每个图像进行处理
                if ((x_count_list+1) % int(self.num_interline_draw) == 0 or x_count_list == 0) and self.x_des is not None:
                    img = (await basic_img_draw_text(img, f'|[des]{self.x_des[self.number_count][x_count_list]}[/des]', self.__dict__,ellipsis=False,
                                                 box=(x_offset_list,self.chart_height + self.padding_up)))['canvas']
                x_offset_list += (self.padding_with + self.chart_width)
                x_count_list+=1
            img=await label_process(self.__dict__,img,self.number_count,self.new_width)#加入label绘制
            self.pure_backdrop = await img_process(self.__dict__,self.pure_backdrop, img, self.x_offset, self.current_y, self.upshift)#对每个图像进行处理
            await per_img_deal(self.__dict__,img)  # 处理每个图片的位置关系
        await final_img_deal(self.__dict__, type='math')  # 处理最后的位置关系
        return {'canvas': self.pure_backdrop, 'canvas_bottom': self.current_y ,'upshift':self.upshift,'downshift':self.downshift,
                'json_img_left_module':self.json_img_left_module,'without_draw':self.without_draw_and_jump}



    async def data_deal(self,type=None):
        processed_content=[]
        if type in ['bar_chart_vertical']:
            if all(not isinstance(item, list) for item in self.content):
                self.content =[self.content]
                if self.x_des is not None: self.x_des =[self.x_des]
        for item in self.content:
            if isinstance(item, (set, list)):
                processed_content2 = []
                for item_check in item:
                    try:item_check = float(item_check)
                    except ValueError:
                        if item_check.endswith('%'): item_check = float(item_check[:-1].repalce(' ','')) / 100
                    if self.max is not False and item_check >= 0:processed_content2.append(item_check / float(self.max))
                    elif 1 >= item_check >= 0:processed_content2.append(item_check)
                    elif item_check >= 1:processed_content2.append(1 / (1 + math.exp(-item_check)) - 0.5)
                    else:processed_content2.append(0)
                processed_content.append(processed_content2)
                continue
            try:
                item=float(item)
            except ValueError:
                if item.endswith('%'):item = float(item[:-1].repalce(' ','')) / 100
            if self.max is not False and item >= 0:processed_content.append(item / float(self.max))
            elif 1 >= item >= 0:processed_content.append(item)
            elif item >= 1:processed_content.append(1 / (1 + math.exp(-item)) - 0.5)
            else:processed_content.append(0)
        self.content = processed_content
