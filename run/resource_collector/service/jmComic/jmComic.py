# -*- coding:utf-8 -*-
import os.path
import shutil

import jmcomic
import yaml
import asyncio

from jmcomic import *
from PIL import Image
import os
import gc
from framework_common.utils.random_str import random_str
from run.ai_generated_art.service.antiSFW import process_folder, compress_gifs
from datetime import date
import zipfile

jm_save={}

class MyDownloader(jmcomic.JmDownloader):
    start = 0
    end = 0
    album_index = 1
    onlyFirstPhoto = False

    def do_filter(self, detail, start=start, end=end):
        start = self.start
        end = self.end
        if detail.is_album() and self.onlyFirstPhoto:
            album: jmcomic.JmAlbumDetail = detail
            if len(album) < self.album_index:
                self.album_index = len(album) - 1
            if self.album_index < 1:
                self.album_index = 1
            return [album[self.album_index - 1]]
        if detail.is_photo():
            photo: jmcomic.JmPhotoDetail = detail
            #print(len(photo))
            if end > len(photo):
                end = len(photo)
            if start > len(photo):
                start = len(photo)
            if start == end:
                start = 0
                end = len(photo)
            return photo[start:end]
        return detail


def queryJM(name, num=3):
    client = jmcomic.JmOption.default().new_jm_client()
    page: jmcomic.JmSearchPage = client.search_site(search_query=name, page=1)
    results = []
    for i in page.content:
        file = downloadComic(i[0], start=1, end=2)
        print([f"车牌号：{i[0]} \n name：{i[1]['name']}\nauthor：{i[1]['author']}", file[0]])
        results.append([f"车牌号：{i[0]} \n name：{i[1]['name']}\nauthor：{i[1]['author']} \n部分预览图：", file[0]])
        if len(results) > num:
            return results
        #print(results)


def JM_search(name):
    client = JmOption.default().new_jm_client()

    # 分页查询，search_site就是禁漫网页上的【站内搜索】
    page: JmSearchPage = client.search_site(search_query=f'{name}', page=1)
    # page默认的迭代方式是page.iter_id_title()，每次迭代返回 albun_id, title
    result = ''
    number = 0
    for album_id, title in page:
        # print(f'[{album_id}]: {title}')
        result += f'[{album_id}]: {title}\n'
        number += 1
        if number == 30: break
    return result


def JM_search_week():
    global jm_save
    op = JmOption.default()
    cl = op.new_jm_client()
    page: JmCategoryPage = cl.week_ranking(1)
    result = ''
    today = date.today()
    if f'{today}_week' in jm_save:
        return jm_save[f'{today}_week']
    for page in cl.categories_filter_gen(page=1,  # 起始页码
                                         # 下面是分类参数
                                         time=JmMagicConstants.TIME_WEEK,
                                         category=JmMagicConstants.CATEGORY_ALL,
                                         order_by=JmMagicConstants.ORDER_BY_VIEW,
                                         ):
        number = 0
        for aid, atitle in page:
            result += f'[{aid}]: {atitle}\n'
            # print(aid, atitle)
            number += 1
            if number == 20: break
        break
    jm_save[f'{today}_week'] = result
    return result

async def JM_search_id(id):
    client = JmOption.default().new_jm_client()
    page: JmSearchPage = client.search_site(search_query=f'{id}', page=1)
    result = ''
    for album_id, title in page:
        result += f'{title}'
        break
    return result




def JM_search_month():
    global jm_save
    op = JmOption.default()
    cl = op.new_jm_client()
    page: JmCategoryPage = cl.week_ranking(1)
    result = []
    today = date.today()
    if f'{today}_month' in jm_save:
        return jm_save[f'{today}_month']
    for page in cl.categories_filter_gen(page=1,  # 起始页码
                                         # 下面是分类参数
                                         time=JmMagicConstants.TIME_MONTH,
                                         category=JmMagicConstants.CATEGORY_ALL,
                                         order_by=JmMagicConstants.ORDER_BY_VIEW,
                                         ):

        for aid, atitle in page:
            result.append(aid)
        if len(result) > 50:break
    jm_save[f'{today}_month']=result
    return result


def downloadComic(comic_id, start=1, end=5,anti_nsfw="black_and_white",gif_compress=False):
    with open("run/resource_collector/jmcomic.yml", 'r', encoding='utf-8') as f: #不知道他这个options咋传的，我就修改配置文件得了。
        result = yaml.load(f.read(), Loader=yaml.FullLoader)
    result["dir_rule"]["base_dir"]=f"data/pictures/benzi/temp{comic_id}"
    #临时修改
    with open("run/resource_collector/jmcomic.yml", 'w', encoding="utf-8") as file:
        yaml.dump(result, file, allow_unicode=True)
    option = jmcomic.create_option_by_file('run/resource_collector/jmcomic.yml')

    if not os.path.exists(f'data/pictures/benzi/temp{comic_id}'):
        os.mkdir(f'data/pictures/benzi/temp{comic_id}')

    MyDownloader.start = start
    MyDownloader.end = end
    MyDownloader.onlyFirstPhoto = True
    jmcomic.JmModuleConfig.CLASS_DOWNLOADER = MyDownloader

    jmcomic.download_album(comic_id, option)

    folder_path = f'data/pictures/benzi/temp{comic_id}'
    if not os.path.exists(folder_path):
        os.mkdir(folder_path)
    file_names = os.listdir(folder_path)
    #print(file_names)
    new_files = []
    if anti_nsfw == "gif":
        asyncio.run(process_folder(input_folder=folder_path,output_folder=folder_path))
        for filename in sorted(os.listdir(folder_path)):
            if filename.lower().endswith('.gif'):
                new_filename = f"data/pictures/cache/{random_str()}.gif"
                shutil.move(os.path.join(folder_path, filename), new_filename)
                new_files.append(new_filename)
        if gif_compress:  # 根据gifcompress的值决定是否压缩
            asyncio.run(compress_gifs(new_files))
    elif anti_nsfw == "black_and_white":
        for i in file_names:
            # print(file_names)
            image_raw = Image.open(f"data/pictures/benzi/temp{comic_id}/" + i)
            
            # convert image to black and white
            image_black_white = image_raw.convert('1')
            newPath = f"data/pictures/cache/{random_str()}.png"
            new_files.append(newPath)
            image_black_white.save(newPath)
        # png_files = [os.path.join(folder_path, file) for file in file_names if file.lower().endswith('.png')]
        #print(new_files)
    elif anti_nsfw == "no_censor":
        for i in file_names:
            original_file = f"data/pictures/benzi/temp{comic_id}/" + i
            shutil.move(original_file, "data/pictures/cache/")
            new_files.append("data/pictures/cache/"+i)
    return new_files


def downloadALLAndToPdf(comic_id, savePath):
    with open("run/resource_collector/jmcomic.yml", 'r', encoding='utf-8') as f:  # 不知道他这个options咋传的，我就修改配置文件得了。
        result = yaml.load(f.read(), Loader=yaml.FullLoader)
    tempResult = copy.deepcopy(result)
    tempResult["dir_rule"]["base_dir"] = f"{savePath}/{comic_id}"

    if os.path.exists(f"{savePath}/{comic_id}"):
        shutil.rmtree(f"{savePath}/{comic_id}")
    if "plugins" not in tempResult:
        tempResult["plugins"] = {}
    if "after_photo" not in tempResult["plugins"]:
        tempResult["plugins"]["after_photo"] = []
    tempResult["plugins"]["after_photo"].append(
        {"plugin": "img2pdf", "kwargs": {"filename_rule": "Pid", "pdf_dir": str(savePath)}})
    with open("run/resource_collector/jmcomic.yml", 'w', encoding="utf-8") as file:
        yaml.dump(tempResult, file, allow_unicode=True)
    # 创建配置对象
    option = jmcomic.create_option_by_file('run/resource_collector/jmcomic.yml')
    with open("run/resource_collector/jmcomic.yml", 'w', encoding="utf-8") as file:
        yaml.dump(result, file, allow_unicode=True)
    # 这里需要再设置一下类变量，不然本子下载不全
    MyDownloader.start = 0
    MyDownloader.end = 0
    MyDownloader.onlyFirstPhoto = True
    jmcomic.JmModuleConfig.CLASS_DOWNLOADER = MyDownloader
    # 使用option对象来下载本子
    jmcomic.download_album(comic_id, option)
    return f"{savePath}/{comic_id}"

if __name__ == '__main__':
    pass
    option = JmOption.default()
    client = option.new_jm_client()

    aid_list = [1025640,432]
    aid_list = [
        9208,143092,214112,237004,247557,289824,297478,302767,315954,320226,369455,377954,378654,
        382558,389479,400387,403172,403224,405524,414406,415654,431296,441373,469555,495255,496298,507134,509898,521050,536770,558026,578492,579627,620808,1012961,1048493,1061591,1084888
    ]

    #download_album(aid_list, option)
    folder_path ='.'
    subfolders = []
    for item in os.listdir(folder_path):
        item_path = os.path.join(folder_path, item)
        if os.path.isdir(item_path):
            ctime = os.path.getctime(item_path)
            subfolders.append((item_path, ctime))

    # 按创建时间排序
    subfolders_sorted = sorted(subfolders, key=lambda x: x[1])
    print(f'文件夹读取完成，共 {len(subfolders_sorted)} 个')

    for i in range(len(subfolders_sorted)):
        dir_path = f'{subfolders_sorted[i][0]}'
        comic_name = subfolders_sorted[i][0].replace("./","")
        client = JmOption.default().new_jm_client()
        page: JmSearchPage = client.search_site(search_query=f'{comic_name}', page=1)
        aid = None
        for album_id, title in page:
            aid = album_id
            break
        if aid is None:
            aid = '未知id'
        print(aid,comic_name)
        if os.path.exists(dir_path):
            image_files = sorted([
                f for f in os.listdir(dir_path)
                if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp'))
            ])
            images = [Image.open(os.path.join(dir_path, img)).convert('RGB') for img in image_files]
            pdf_path = f'{aid}_{comic_name}.pdf'  # 输出的PDF文件名
            images[0].save(pdf_path, save_all=True, append_images=images[1:])
            for img in images:
                img.close()
            images.clear()
            gc.collect()
            shutil.rmtree(dir_path)
        else:
            print('文件夹不存在，跳过处理')

    print('开始进行压缩处理')
    zip_path = '/home/manshuo/manshuo/bot/Eridanus/run/resource_collector/service/jmComic/comic.zip'
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # 遍历文件夹中的所有文件和子文件夹
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                # 将文件写入zip，arcname用于保持相对路径结构
                arcname = os.path.relpath(file_path, start=folder_path)
                zipf.write(file_path, arcname)