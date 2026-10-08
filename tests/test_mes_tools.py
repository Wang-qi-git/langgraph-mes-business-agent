"""MES 工具测试（mock HTTP 请求）"""
import pytest
from unittest.mock import patch, Mock


def _mock_response(status_code=200, json_data=None):
    """构造 mock 的 requests.Response"""
    m = Mock()
    m.status_code = status_code
    m.json.return_value = json_data or {}
    return m


@patch("mes_tools.requests.get")
def test_query_work_order_success(mock_get):
    mock_get.return_value = _mock_response(200, {
        "order_id": "WO-001",
        "product": "测试产品",
        "quantity": 100,
        "status": "生产中",
        "current_process": "装配",
        "progress": 50,
        "yield_rate": 98.5,
        "planned_end": "2026-10-10",
        "priority": "高",
    })
    import mes_tools
    result = mes_tools.query_work_order("WO-001")
    assert "WO-001" in result
    assert "生产中" in result
    assert "50" in result


@patch("mes_tools.requests.get")
def test_query_work_order_not_found(mock_get):
    mock_get.return_value = _mock_response(404, {"detail": "not found"})
    import mes_tools
    result = mes_tools.query_work_order("WO-999")
    assert "不存在" in result


@patch("mes_tools.requests.get")
def test_query_work_order_connection_error(mock_get):
    mock_get.side_effect = Exception("connection refused")
    import mes_tools
    result = mes_tools.query_work_order("WO-001")
    assert "MES 查询失败" in result


@patch("mes_tools.requests.get")
def test_query_inventory_below_safety(mock_get):
    mock_get.return_value = _mock_response(200, {
        "sku": "SKU-A100-01",
        "name": "定子",
        "quantity": 50,
        "safety_stock": 100,
        "unit": "个",
        "location": "A-01",
        "below_safety": True,
    })
    import mes_tools
    result = mes_tools.query_inventory("SKU-A100-01")
    assert "低于安全库存" in result


def test_mes_tools_registry():
    import mes_tools
    assert "mes_work_order" in mes_tools.MES_TOOLS
    assert "mes_inventory" in mes_tools.MES_TOOLS
    assert "mes_equipment" in mes_tools.MES_TOOLS
    assert "mes_low_stock" in mes_tools.MES_TOOLS
    assert len(mes_tools.MES_TOOLS) == 6