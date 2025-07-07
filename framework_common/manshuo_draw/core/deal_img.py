import os
import gc
from framework_common.manshuo_draw.core.classic_collection import *
from framework_common.manshuo_draw.core.util import *


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

            printf(per_json_img)
            count_number += 1
            if layer_img_info.img_height <= 0:
                print(json_img)
                if layer == layer_check :
                    if per_json_img['type'] not in ['layer_processed','backdrop']: json_img_left.append(per_json_img)
                return {'content':None}
            if layer_img_info.img_height_limit_flag:
                if per_json_img['type'] not in ['layer_processed','backdrop']:json_img_left.append(per_json_img)
                continue
            match per_json_img['type']:
                case 'text':    json_check = getattr(TextModule(layer_img_info, per_json_img), per_json_img['subtype'])()
                case 'img':     json_check = getattr(ImageModule(layer_img_info, per_json_img), per_json_img['subtype'])()
                case 'avatar':  json_check = getattr(AvatarModule(layer_img_info, per_json_img), per_json_img['subtype'])()
                case 'games':   json_check = getattr(GamesModule(layer_img_info, per_json_img), per_json_img['subtype'])()
                case 'layer_processed':json_check = per_json_img['content']
                case _:         json_check=None
            if json_check:
                canvas_dict[count_number]=json_check
                layer_img_info.img_height_limit -= (json_check['canvas_bottom'] + layer_img_info.padding_up_layer)
                if layer_img_info.img_height_limit <= 0 : layer_img_info.img_height_limit, layer_img_info.img_height_limit_flag = 0, True
                #print(json_check['canvas_bottom'] + layer_img_info.padding_up_layer,layer_img_info.img_height_limit,json_check['canvas_bottom'] + layer_img_info.padding_up_layer+layer_img_info.img_height_limit)
        elif layer_check > layer:
            json_check=await layer_deal(layer_img_info,json_img,json_img_left,layer=layer+1)
            json_img=add_append_img([{'type':'layer_processed','content':json_check['content'],'layer':layer}],json_img)
        elif layer_check < layer:
            break

    layer_img_canvas=layer_img_info.paste_img(canvas_dict)
    #layer_img_canvas.show()
    upshift,downshift=0,0
    return {'layer_img_canvas':layer_img_canvas,
            'content':{'canvas':layer_img_canvas, 'canvas_bottom': layer_img_canvas.height - layer_img_info.padding_up_common * 3  ,
                       'upshift':layer_img_info.padding_up_common * 2 ,'downshift':downshift}}




async def deal_img(json_img): #此函数将逐个解析json文件中的每个字典并与之对应的类相结合
    printf_check(json_img)
    printf('开始处理图片')



    basic_json_set= json_img.copy()
    for per_json_img in basic_json_set:               #优先将图片的基本信息创建好，以免出错
        if 'basic_set' in per_json_img['type']:
            basic_img_info = basicimgset(per_json_img)
            basic_img = basic_img_info.creatbasicimgnobackdrop()
            break

    if basic_img_info.is_abs_path_convert is True:
        basic_img_info.img_path_save = get_abs_path(basic_img_info.img_path_save,is_ignore_judge=True)
    if basic_img_info.img_name_save is not None :
        img_path = basic_img_info.img_path_save
        if os.path.isfile(img_path):return img_path
    else:
        img_path = basic_img_info.img_path_save+"/" + random_str() + ".png"

    json_img_left=[]
    json_check=await layer_deal(basic_img_info,json_img,json_img_left)
    layer_img_canvas=json_check['layer_img_canvas']
    print('\n')
    for item in json_check['json_img_left']:
        printf(item)
    #layer_img_canvas.show()
    #将之前的模块粘贴到实现绘制的无色中间层上
    basic_img=basic_img_info.combine_layer_basic(basic_img,layer_img_canvas)

    for per_json_img in basic_json_set:               #处理背景相关
        if 'backdrop' in per_json_img['type']:
            backdrop_class=Backdrop(basic_img_info, per_json_img)
            basic_img=getattr(backdrop_class, per_json_img['subtype'])(basic_img)





    basic_img.save(img_path, "PNG")
    if basic_img_info.debug is True:
        basic_img.show()

    try:#做好对应资源关闭并释放，以免卡顿
        basic_img.close()
        del basic_img
        gc.collect()
        printf('图片缓存成功释放')
    except:
        printf('绘图资源释放失败，长期可能会导致缓存无法清理引起卡顿')

    return img_path