"""
追漫阁 - 统一 API 响应格式
"""
from typing import Any, Optional
from flask import jsonify, Response


def success_response(data: Optional[Any] = None, message: str = "操作成功", status_code: int = 200) -> tuple[Response, int]:
    """
    统一成功响应格式

    Args:
        data: 返回的数据
        message: 响应消息
        status_code: HTTP 状态码

    Returns:
        (Flask Response, HTTP 状态码)
    """
    response_body = {
        "success": True,
        "message": message
    }
    if data is not None:
        response_body["data"] = data
    return jsonify(response_body), status_code


def error_response(error: str, code: Optional[str] = None, status_code: int = 400) -> tuple[Response, int]:
    """
    统一错误响应格式

    Args:
        error: 错误描述
        code: 错误代码（可选）
        status_code: HTTP 状态码

    Returns:
        (Flask Response, HTTP 状态码)
    """
    response_body = {
        "success": False,
        "error": error
    }
    if code is not None:
        response_body["code"] = code
    return jsonify(response_body), status_code


def paginated_response(data: list, total: int, page: int = 1, per_page: int = 20, message: str = "查询成功") -> tuple[Response, int]:
    """
    分页响应格式

    Args:
        data: 返回的数据列表
        total: 总记录数
        page: 当前页码
        per_page: 每页数量
        message: 响应消息

    Returns:
        (Flask Response, HTTP 状态码)
    """
    return success_response({
        "items": data,
        "pagination": {
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page if per_page > 0 else 0
        }
    }, message=message)
