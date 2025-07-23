import os
import gc
from .classic_collection import *
from .util import *


async def layer_deal(basic_img_info,json_img,json_img_left,layer=1):
    layer_img_info = LayerSet(basic_img_info)

    #重写之前的处理逻辑，实现边绘制边修改自身设置
    canvas_dict, count_number, i = {}, 0, 0
    while i < len(json_img):
        per_json_img = json_img[i]

        #先照搬之前的处理逻辑，修修bug
        if 'layer' not in per_json_img:layer_check=1
        else:layer_check=int(per_json_img['layer'])

        if layer_check == layer:
            json_img.pop(json_img.index(per_json_img))
            count_number += 1
            if layer_img_info.img_height <= 0:
                if layer == layer_check and per_json_img['type'] not in ['layer_processed','backdrop']: json_img_left.append(per_json_img)
                return {'content':None}
            if layer_img_info.img_height_limit_flag:
                if per_json_img['type'] not in ['layer_processed','backdrop']:json_img_left.append(per_json_img)
                continue
            if per_json_img['type'] not in ['layer_processed', 'backdrop']: printf(per_json_img)
            #print(layer_img_info.img_height_limit)
            match per_json_img['type']:
                case 'text':    json_check = await getattr(TextModule(layer_img_info, per_json_img), per_json_img['subtype'])()
                case 'img':     json_check = await getattr(ImageModule(layer_img_info, per_json_img), per_json_img['subtype'])()
                case 'avatar':  json_check = await getattr(AvatarModule(layer_img_info, per_json_img), per_json_img['subtype'])()
                case 'games':   json_check = await getattr(GamesModule(layer_img_info, per_json_img), per_json_img['subtype'])()
                case 'layer_processed':json_check = per_json_img['content']
                case _:         json_check=None
            if json_check:
                canvas_dict[count_number]=json_check
                layer_img_info.img_height_limit -= (json_check['canvas_bottom'] + layer_img_info.padding_up_layer)
                #视情况设定对应限制标记，对应图像的高度限制
                if layer_img_info.img_height_limit <= 0 or json_check['without_draw']:
                    layer_img_info.img_height_limit, layer_img_info.img_height_limit_flag = 0, True
                #若模块返回相应值未绘制值，则添加
                if json_check['json_img_left_module']: json_img_left.append(json_check['json_img_left_module'])
                #print(json_check['canvas_bottom'] + layer_img_info.padding_up_layer, layer_img_info.img_height_limit, json_check['canvas_bottom'] + layer_img_info.padding_up_layer+layer_img_info.img_height_limit)
        elif layer_check > layer:
            json_check=await layer_deal(layer_img_info,json_img,json_img_left,layer=layer+1)
            json_img=add_append_img([{'type':'layer_processed','content':json_check['content'],'layer':layer}],json_img)
        elif layer_check < layer:
            break

    layer_img_canvas=await layer_img_info.paste_img(canvas_dict)
    #layer_img_canvas.show()
    upshift,downshift=0,0
    return {'layer_img_canvas':layer_img_canvas,
            'content':{'canvas':layer_img_canvas, 'canvas_bottom': layer_img_canvas.height - layer_img_info.padding_up_common * 3  ,
                       'upshift':layer_img_info.padding_up_common * 2 ,'downshift':downshift,'without_draw':False,'json_img_left_module':[]}}




async def deal_img(json_img): #此函数将逐个解析json文件中的每个字典并与之对应的类相结合
    printf_check(json_img)
    printf('开始处理图片')



    basic_json_set= json_img.copy()
    for per_json_img in basic_json_set:               #优先将图片的基本信息创建好，以免出错
        if 'basic_set' in per_json_img['type']:
            basic_img_info = basicimgset(per_json_img)
            break

    if basic_img_info.is_abs_path_convert is True:
        basic_img_info.img_path_save = get_abs_path(basic_img_info.img_path_save,is_ignore_judge=True)
    if basic_img_info.img_name_save is not None :
        img_path = basic_img_info.img_path_save
        if os.path.isfile(img_path):return img_path
    else:
        img_path = basic_img_info.img_path_save+"/" + random_str() + ".png"


    canves_layer_list=[]
    for item in range(basic_img_info.max_num_of_columns):
        printf(item)
        if item == 0 : json_img_deal = json_img
        else: json_img_deal = json_img_left
        json_img_left=[]
        layer_img_canvas=(await layer_deal(basic_img_info,json_img_deal,json_img_left))['layer_img_canvas']
        #layer_img_canvas.show()
        canves_layer_list.append(layer_img_canvas)
        if not json_img_left:break

    printf('\n')
    for item in json_img_left:printf(item)
    #layer_img_canvas.show()
    #将之前的模块粘贴到实现绘制的无色中间层上
    basic_img = await basic_img_info.creatbasicimgnobackdrop(canves_layer_list)
    basic_img = await basic_img_info.combine_layer_basic(basic_img,canves_layer_list)

    for per_json_img in basic_json_set:               #处理背景相关
        if 'backdrop' in per_json_img['type']:
            backdrop_class=Backdrop(basic_img_info, per_json_img)
            basic_img=await getattr(backdrop_class, per_json_img['subtype'])(basic_img)





    basic_img.save(img_path, "PNG")
    if basic_img_info.debug is True:
        pass
        basic_img.show()

    try:#做好对应资源关闭并释放，以免卡顿
        basic_img.close()
        del basic_img
        gc.collect()
        printf('图片缓存成功释放')
    except:
        printf('绘图资源释放失败，长期可能会导致缓存无法清理引起卡顿')

    return img_path