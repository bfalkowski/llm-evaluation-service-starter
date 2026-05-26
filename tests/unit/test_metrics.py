from app.core.metrics import metrics, record_queue_depth


def test_record_queue_depth_exports_gauge() -> None:
    record_queue_depth(3)
    rendered = metrics.render_prometheus()
    assert "evaluation_queue_depth" in rendered
    assert "evaluation_queue_depth 3" in rendered
