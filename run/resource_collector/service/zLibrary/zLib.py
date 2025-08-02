from framework_common.manshuo_draw import manshuo_draw
from run.resource_collector.service.zLibrary.canvas import create_book_image

# Create Zlibrary object and login


# Search for books

# Getting image content
async def search_book(Z,book,num):
    results = Z.search(message=book, order="bestmatch")

    return await parse_result(results,num)
async def parse_result(data,num):
    result=[]
    for book in data["books"][:num]:
        try:
            text=(f"[title]{book['title']}[/title]"
                  f"\n 作者：{book['author']}"
                  f"\n 年份：{book['year']}"
                  f"\n 出版商：{book['publisher']}"
                  f"\n 文件大小：{book['filesizeString']}  格式：{book['extension']}"
                  f"\n 简介：\n {book['description']}")
            r=await manshuo_draw([{ 'type': 'basic_set', 'img_width': 2000,'img_height': 2500,'max_num_of_columns': 3 ,'font_common_size': 34,'font_des_size': 25, 'font_title_size': 46,'spacing': 3,'padding_up': 30},
                            {'type': 'img', 'subtype': 'common_with_des_right', 'img': [book['cover']], 'content': [text.replace('<br>', '\n ')]}])
            result.append([f"book_id: {book['id']}\nhash: {book['hash']}",r])
        except:
            continue
    return result
def download_book(Z,book_id,hash):
    book={"id":str(book_id),"hash":hash}
    r=Z.downloadBook(book)
    filename, file_content = r
    path=f"data/text/books/{filename}"
    with open(path, "wb") as f:
        f.write(file_content)
    return path


