"""Bộ kiểm tra tham số theo JSON Schema (bản rút gọn, chỉ dùng thư viện chuẩn của Python).

Vì sao tự viết: tham số do LLM gửi KHÔNG được tin. Trước khi chạy tool, code kiểm tra
tham số có đúng khuôn mà bản khai báo của tool đã mô tả hay không.

Hỗ trợ: type (object, string, integer, number, boolean, array), required, properties,
additionalProperties=false, enum, minLength, maxLength, minimum, maximum, items, minItems, maxItems.
"""


def validate(value, schema, path="args"):
    """Trả về danh sách lỗi (chuỗi). Danh sách rỗng nghĩa là hợp lệ."""
    errors = []
    expected = schema.get("type")

    if expected == "object":
        if not isinstance(value, dict):
            return [f"{path}: phải là object, nhận được {_name(value)}"]
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}: thiếu tham số bắt buộc '{key}'")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in props:
                    errors.append(f"{path}: tham số '{key}' không có trong khai báo (hợp lệ: {', '.join(props) or 'không có'})")
        for key, sub in props.items():
            if key in value:
                errors += validate(value[key], sub, f"{path}.{key}")

    elif expected == "string":
        if not isinstance(value, str):
            return [f"{path}: phải là chuỗi, nhận được {_name(value)}"]
        if len(value) < schema.get("minLength", 0):
            errors.append(f"{path}: quá ngắn (tối thiểu {schema['minLength']} ký tự)")
        if len(value) > schema.get("maxLength", 10**9):
            errors.append(f"{path}: quá dài (tối đa {schema['maxLength']} ký tự)")

    elif expected in ("integer", "number"):
        is_num = isinstance(value, (int, float)) and not isinstance(value, bool)
        if not is_num or (expected == "integer" and isinstance(value, float) and not value.is_integer()):
            return [f"{path}: phải là {'số nguyên' if expected == 'integer' else 'số'}, nhận được {_name(value)}"]
        if value < schema.get("minimum", float("-inf")):
            errors.append(f"{path}: nhỏ hơn mức tối thiểu {schema['minimum']}")
        if value > schema.get("maximum", float("inf")):
            errors.append(f"{path}: lớn hơn mức tối đa {schema['maximum']}")

    elif expected == "boolean":
        if not isinstance(value, bool):
            return [f"{path}: phải là true/false, nhận được {_name(value)}"]

    elif expected == "array":
        if not isinstance(value, list):
            return [f"{path}: phải là mảng, nhận được {_name(value)}"]
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{path}: cần ít nhất {schema['minItems']} phần tử")
        if len(value) > schema.get("maxItems", 10**9):
            errors.append(f"{path}: tối đa {schema['maxItems']} phần tử")
        if "items" in schema:
            for i, item in enumerate(value):
                errors += validate(item, schema["items"], f"{path}[{i}]")

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: giá trị phải thuộc {schema['enum']}")
    return errors


def _name(value):
    return {dict: "object", list: "mảng", str: "chuỗi", bool: "true/false",
            int: "số nguyên", float: "số", type(None): "null"}.get(type(value), type(value).__name__)
