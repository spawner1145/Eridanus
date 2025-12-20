from PIL import Image
from .initialize import initialize_yaml_must_require
from .util import *
import pprint
import asyncio
import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed


class ImageModule:
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

    async def common(self):
        timestart = datetime.datetime.now().timestamp()
        await init(self.__dict__)#对该模块进行初始化
        #对每个图片进行单独处理
        for img in self.processed_img:
            if self.img_height_limit_module <= 0:break
            img = await per_img_limit_deal(self.__dict__,img)#处理每个图片,您的每张图片绘制自定义区域
            img=await label_process(self.__dict__,img,self.number_count,self.new_width)#加入label绘制
            self.pure_backdrop = await img_process(self.__dict__,self.pure_backdrop, img, self.x_offset, self.current_y, self.upshift)#对每个图像进行处理
            await per_img_deal(self.__dict__,img)  # 处理每个图片的位置关系
        await final_img_deal(self.__dict__)  # 处理最后的位置关系
        print(datetime.datetime.now().timestamp() - timestart)
        return {'canvas': self.pure_backdrop, 'canvas_bottom': self.current_y ,'upshift':self.upshift,'downshift':self.downshift,
                'json_img_left_module':self.json_img_left_module,'without_draw':self.without_draw_and_jump}

    async def common_test(self):
        timestart = datetime.datetime.now().timestamp()
        await init(self.__dict__)#对该模块进行初始化
        #函数内自定义函数，便于后续创建任务并发执行
        async def img_deal_current(count):
            img, number_count = self.processed_img[count], count
            img = await per_img_deal_gather(self.__dict__.copy(), img)  # 处理每个图片,您的每张图片绘制自定义区域
            img = await label_process(self.__dict__,img,number_count,self.new_width)#加入label绘制
            #img = await img_rounded_gather(self.__dict__.copy(),img)
            return {'img':img, 'info':{}}
        #使用gather创建任务并发处理
        tasks = [img_deal_current(count) for count in range(len(self.processed_img))]
        data_img_list = await asyncio.gather(*tasks)
        print(datetime.datetime.now().timestamp() - timestart)
        #对每个图片进行单独处理
        for img_info in data_img_list:
            img = img_info['img']
            if self.img_height_limit_module <= 0:break
            img = await per_img_limit_deal_gather(self.__dict__,img)#处理每个图片,您的每张图片绘制自定义区域
            img_info['img']= img
            img_info['info'] = {'x_offset': self.x_offset, 'current_y': self.current_y, 'upshift':self.upshift}
            img_info['params'] = self.__dict__
            await per_img_deal(self.__dict__,img)  # 处理每个图片的位置关系
        #生成所有子元素的透明底
        tasks = [img_process_gather(info) for info in data_img_list]
        temp_img_list = await asyncio.gather(*tasks)

        #with ProcessPoolExecutor() as executor:
        #    temp_img_list = list(executor.map(img_process_gather, data_img_list))

        print(datetime.datetime.now().timestamp() - timestart)
        #将所有子元素透明底合并到原透明底上
        if len(temp_img_list) != 0: self.pure_backdrop = await img_combine_alpha(temp_img_list)
        await final_img_deal(self.__dict__)  # 处理最后的位置关系
        return {'canvas': self.pure_backdrop, 'canvas_bottom': self.current_y ,'upshift':self.upshift,'downshift':self.downshift,
                'json_img_left_module':self.json_img_left_module,'without_draw':self.without_draw_and_jump}

    async def common_with_des(self):
        await init(self.__dict__)#对该模块进行初始化
        # 对每个图片进行单独处理
        for img in self.processed_img:
            if self.img_height_limit_module <= 0: break
            img = await per_img_limit_deal(self.__dict__,img)
            img_des_canvas = Image.new("RGBA", (img.width, img.height + self.max_des_length), eval(str(self.description_color)))
            img_des_canvas.paste(img, (0, 0),mask=img.convert("RGBA").split()[3])
            if self.max_des_length + img.height > self.img_height_limit_module:
                self.max_des_length = self.img_height_limit_module - img.height
                if self.max_des_length < 0: self.max_des_length = 0
            img_des_canvas_info=await basic_img_draw_text(img_des_canvas,self.content[self.number_count],self.__dict__,
                                                                     box=(self.padding , img.height + self.padding),
                                                                     limit_box=(self.new_width, self.max_des_length + img.height))
            des_length = self.max_des_length + img.height
            if int(img_des_canvas_info['canvas_bottom'] + self.padding_up) < des_length:
                des_length=int(img_des_canvas_info['canvas_bottom'] + self.padding_up)
            img=img_des_canvas_info['canvas'].crop((0, 0, img.width, des_length))

            #加入label绘制
            img=await label_process(self.__dict__,img,self.number_count,self.new_width)
            # 对每个图像进行处理
            self.pure_backdrop = await img_process(self.__dict__,self.pure_backdrop, img, self.x_offset, self.current_y, self.upshift)
            await per_img_deal(self.__dict__, img)  # 处理每个图片的位置关系
        await final_img_deal(self.__dict__)  # 处理最后的位置关系
        return {'canvas': self.pure_backdrop, 'canvas_bottom': self.current_y, 'upshift': self.upshift, 'downshift': self.downshift,
                'json_img_left_module':self.json_img_left_module,'without_draw':self.without_draw_and_jump}


    async def common_with_des_right(self):
        await init(self.__dict__)#对该模块进行初始化
        # 对每个图片进行单独处理
        for img in self.processed_img:
            if self.img_height_limit_module <= 0: break
            img = await per_img_limit_deal(self.__dict__,img)
            img_des_canvas = Image.new("RGBA", (self.new_width, img.height),eval(str(self.description_color)))
            img_des_canvas.paste(img, (0, 0),mask=img.convert("RGBA").split()[3])
            #进行文字绘制
            img = (await basic_img_draw_text(img_des_canvas, self.content[self.number_count], self.__dict__,
                                                      box=(int(self.new_width / self.magnification_img) + self.padding,  self.padding),
                                                      limit_box=(self.new_width, img.height)))['canvas']

            # 加入label绘制
            img = await label_process(self.__dict__,img, self.number_count, int(self.new_width / self.magnification_img))
            # 对每个图像进行处理
            self.pure_backdrop = await img_process(self.__dict__, self.pure_backdrop, img, self.x_offset, self.current_y, self.upshift)
            await per_img_deal(self.__dict__, img)  # 处理每个图片的位置关系
        await final_img_deal(self.__dict__)  # 处理最后的位置关系


        return {'canvas': self.pure_backdrop, 'canvas_bottom': self.current_y, 'upshift': self.upshift, 'downshift': self.downshift,
                'json_img_left_module':self.json_img_left_module,'without_draw':self.without_draw_and_jump}



