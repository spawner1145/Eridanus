from typing import List,Dict,Any,Tuple,Optional,Iterable,Union,TypeVar,Literal


def json_check(json_img: List[Any]) -> List[Dict[str, Any]]:
    """内存优化版本 - 解决内存泄漏问题"""
    if not isinstance(json_img, list):
        raise ValueError("input must be a list")

    json_check_reload = []

    # 预定义常量，避免重复字符串比较
    img_extensions = frozenset([".jpg", ".png", ".jpeg", ".webp"])  # 使用frozenset减少内存
    valid_types = frozenset(['avatar', 'img', 'text', 'games','math'])
    special_types = frozenset(['basic_set', 'backdrop'])

    for per_json_check in json_img:
        if isinstance(per_json_check, dict):
            item_type = per_json_check.get('type')  # 避免重复访问
            if item_type in valid_types:
                if 'subtype' not in per_json_check:
                    per_json_check['subtype'] = 'common'
                json_check_reload.append(per_json_check)
            elif item_type in special_types:
                json_check_reload.append(per_json_check)
            # 移除else continue，减少分支
        elif isinstance(per_json_check, (set, list)):
            collect_img = []
            collect_text = []

            for per_json_check_per in per_json_check:
                # 优化字符串检测，避免重复创建临时字符串
                if isinstance(per_json_check_per, str):
                    if per_json_check_per.startswith("http"):
                        collect_img.append(per_json_check_per)
                    else:
                        # 优化文件扩展名检测，避免splitext创建临时对象
                        dot_pos = per_json_check_per.rfind('.')
                        if dot_pos != -1:
                            ext = per_json_check_per[dot_pos:].lower()
                            if ext in img_extensions:
                                collect_img.append(per_json_check_per)
                            else:
                                collect_text.append(per_json_check_per)
                        else:
                            collect_text.append(per_json_check_per)
                else:
                    collect_text.append(per_json_check_per)

            # 批量添加，减少append调用
            if collect_img:
                json_check_reload.append({'type': 'img', 'subtype': 'common', 'img': collect_img})
            if collect_text:
                json_check_reload.append({'type': 'text', 'subtype': 'common', 'content': collect_text})
        else:
            # 简化单项处理逻辑
            if isinstance(per_json_check, str):
                if per_json_check.startswith("http"):
                    json_check_reload.append({'type': 'img', 'subtype': 'common', 'img': [per_json_check]})
                else:
                    # 同样优化扩展名检测
                    dot_pos = per_json_check.rfind('.')
                    if dot_pos != -1 and per_json_check[dot_pos:].lower() in img_extensions:
                        json_check_reload.append({'type': 'img', 'subtype': 'common', 'img': [per_json_check]})
                    else:
                        json_check_reload.append({'type': 'text', 'subtype': 'common', 'content': [per_json_check]})
            else:
                json_check_reload.append({'type': 'text', 'subtype': 'common', 'content': [str(per_json_check)]})

    # 优化类型检查 - 只遍历一次，使用更高效的方式
    has_basic_set = False
    has_backdrop = False

    for item in json_check_reload:
        item_type = item.get('type')
        if item_type == 'basic_set':
            has_basic_set = True
        elif item_type == 'backdrop':
            has_backdrop = True
        # 如果两个都找到了，提前退出
        if has_basic_set and has_backdrop:
            break

    if not has_basic_set:
        json_check_reload.append({'type': 'basic_set'})
    if not has_backdrop:
        json_check_reload.append({'type': 'backdrop', 'subtype': 'gradient'})

    # 轻量级绘图设置 - 优化YAML管理器的使用
    yaml_manager = None
    try:
        is_lightweight = False
        for item in json_check_reload:
            if item.get('type') == 'basic_set':
                if is_lightweight:
                    item['is_rounded_corners_front'] = False
                    item['is_stroke_front'] = False
                    item['is_shadow_front'] = False
                if 'config_path' not in item:
                    item['config_path'] = 'framework_common/manshuo_draw/data/config/manshuodraw_config.yaml'
    except Exception:
        pass
    finally:
        # 确保YAML管理器被正确清理
        if yaml_manager is not None:
            try:
                del yaml_manager
            except Exception:
                pass
        yaml_manager = None

    return json_check_reload